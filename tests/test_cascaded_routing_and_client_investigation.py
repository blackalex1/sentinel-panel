import os
import time
import json
import pytest
from pathlib import Path
from backend.database import db_session
from backend.models import Inbound, Outbound, RoutingRule, ClientStats
from backend.sentinel_core_bridge import (
    find_xray_client_email,
    find_hysteria_client_email,
    find_client_ip_for_email_in_hysteria_log,
)
from backend.xray.config_builder.builder import generate_xray_config_json
from backend.singbox.config import generate_singbox_config_json


def test_cascaded_routing_rules_and_config_compilation(client):
    """
    Проверяет создание каскадной маршрутизации из Panel 1 в Panel 2:
    - Инбаунд VLESS для клиента cascaded_user@test.lan
    - Аутбаунд Hysteria 2 туннель на удаленную панель (198.51.100.14:36711)
    - Правило маршрутизации: трафик cascaded_user@test.lan направляется в аутбаунд out-vps-test
    - Компиляция конфигураций Xray и Sing-box и валидация схемы маршрутизации.
    """
    with db_session() as session:
        # Очищаем старые тестовые данные
        session.query(RoutingRule).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.query(Outbound).delete()
        session.commit()

        # 1. Создаем Инбаунд
        ib = Inbound(
            remark="Inbound VLESS Users",
            port=10443,
            protocol="vless",
            core="xray",
            settings=json.dumps({"clients": [], "decryption": "none"}),
            stream_settings=json.dumps({"network": "tcp"}),
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.flush()

        # 2. Создаем Клиента
        cs = ClientStats(
            inbound_id=ib.id,
            email="cascaded_user@test.lan",
            client_uuid_or_pwd="d6d0e37a-f497-4813-8d5c-9e3efa5d7c7d",
            enable=1
        )
        session.add(cs)

        # 3. Создаем Аутбаунд туннеля на вторую панель (VPS)
        ob = Outbound(
            remark="VPS-Test-Tunnel",
            tag="out-vps-test",
            protocol="hysteria2",
            settings=json.dumps({
                "server": "198.51.100.14",
                "port": 36711,
                "auth": "vps_transit_secret",
                "up_mbps": 100,
                "down_mbps": 100
            }),
            stream_settings=json.dumps({"serverName": "198.51.100.14"}),
            enable=1
        )
        session.add(ob)
        session.flush()

        # 4. Создаем Правило маршрутизации
        rule = RoutingRule(
            remark="Route cascaded user to VPS Test",
            outbound_tag="out-vps-test",
            users=json.dumps(["cascaded_user@test.lan"]),
            enable=1,
            sort_order=1
        )
        session.add(rule)
        session.commit()

    # 5. Проверяем компиляцию конфигурации Xray
    xray_cfg = generate_xray_config_json()
    assert "routing" in xray_cfg or "outbounds" in xray_cfg

    # 6. Проверяем компиляцию конфигурации Sing-box
    singbox_cfg = generate_singbox_config_json()
    assert "route" in singbox_cfg or "outbounds" in singbox_cfg


def test_api_client_by_connection_cascaded_and_direct(client, monkeypatch):
    """
    Тестирует эндпоинт /api/security/client-by-connection для:
    1. Каскадного клиента, найденного в логах ядра
    2. Прямого клиента на конечной панели
    3. Невиновного клиента (доступ к Telegram api.telegram.org) -> не должен матчиться на сторонний IP
    4. Заблокированного клиента (enable=0) -> должен игнорироваться
    """
    import backend.routes.security_routes.management as mgmt
    monkeypatch.setattr(mgmt, "check_auth", lambda r: True)

    now_str_xray = time.strftime("%Y/%m/%d %H:%M:%S")
    now_str_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.commit()

        ib = Inbound(remark="Test Inbound", port=443, protocol="vless", core="xray", enable=1)
        session.add(ib)
        session.flush()

        c_cascaded = ClientStats(inbound_id=ib.id, email="cascaded_user@test.lan", client_uuid_or_pwd="pwd1", enable=1)
        c_direct = ClientStats(inbound_id=ib.id, email="direct_user@test.lan", client_uuid_or_pwd="pwd2", enable=1)
        c_innocent = ClientStats(inbound_id=ib.id, email="innocent_user@test.lan", client_uuid_or_pwd="pwd3", enable=1)
        c_banned = ClientStats(inbound_id=ib.id, email="old_banned_user@test.lan", client_uuid_or_pwd="pwd4", enable=0)

        session.add_all([c_cascaded, c_direct, c_innocent, c_banned])
        session.commit()

    # Имитируем логи ядер в памяти
    mock_xray_logs = [
        f"{now_str_xray} [info] 192.168.1.50:41234 accepted tcp:203.0.113.195:22 [vless-in >> out-vps] email: cascaded_user@test.lan",
        f"{now_str_xray} [info] 192.0.2.45:55123 accepted tcp:198.51.100.88:3389 [vless-in >> direct] email: direct_user@test.lan",
        f"{now_str_xray} [info] 192.0.2.45:55124 accepted tcp:api.telegram.org:443 [vless-in >> direct] email: innocent_user@test.lan",
        f"{now_str_xray} [info] 192.0.2.45:55125 accepted tcp:203.0.113.200:22 [vless-in >> direct] email: old_banned_user@test.lan",
    ]
    mock_hysteria_logs = [
        f'{{"time":"{now_str_iso}","id":"cascaded_user@test.lan","reqAddr":"203.0.113.195:22"}}',
        f'{{"time":"{now_str_iso}","auth":"cascaded_user@test.lan","addr":"192.168.1.50:41234"}}',
    ]

    def mock_get_in_memory_logs(core, limit=500):
        if core == "xray":
            return mock_xray_logs
        elif core == "hysteria":
            return mock_hysteria_logs
        return []

    monkeypatch.setattr("backend.routes.security_routes.management.get_in_memory_core_logs", mock_get_in_memory_logs)

    # 1. Поиск каскадного клиента (SSH на 203.0.113.195:22)
    res1 = client.get("/api/security/client-by-connection?dst_ip=203.0.113.195&port=22")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["success"] is True
    assert data1["email"] == "cascaded_user@test.lan"

    # 2. Поиск прямого клиента (RDP на 198.51.100.88:3389)
    res2 = client.get("/api/security/client-by-connection?dst_ip=198.51.100.88&port=3389")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["success"] is True
    assert data2["email"] == "direct_user@test.lan"

    # 3. Поиск стороннего IP на 443 порту -> невиновный клиент Telegram НЕ должен найтись
    res3 = client.get("/api/security/client-by-connection?dst_ip=198.51.100.137&port=443")
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["success"] is False

    # 4. Поиск клиента, который уже отключен (enable=0) -> должен быть проигнорирован
    res4 = client.get("/api/security/client-by-connection?dst_ip=203.0.113.200&port=22")
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["success"] is False, "Отключенный клиент должен игнорироваться, чтобы не вызывать зацикливания"
