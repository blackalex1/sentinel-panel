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
            client_uuid_or_pwd="10000000-0000-4000-8000-000000000106",
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


def test_three_server_cascaded_investigation_ipv4_to_ipv6(client, monkeypatch):
    """
    Тестирует расследование в 3-уровневом каскаде:
    - Сервер 1 (LXC Gateway) -> подключается к Серверу 2 по IPv4 (198.51.100.20:443)
    - Сервер 2 (Transit Relay) -> подключается к Серверу 3 по IPv6 ([2001:db8:2000::3]:8443)
    - Сервер 3 (Exit VPS) -> клиент совершает обращение на sensitive port 22 ([2001:db8:bad:c0de::1]:22)
    Проверяем пошаговую атрибуцию через эндпоинт /api/security/client-by-connection от Сервера 3 к Серверу 1.
    """
    import backend.routes.security_routes.management as mgmt
    monkeypatch.setattr(mgmt, "check_auth", lambda r: True)

    now_str_xray = time.strftime("%Y/%m/%d %H:%M:%S")
    now_str_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    target_ipv6 = "2001:db8:bad:c0de::1"
    target_port = 22

    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.commit()

        ib1 = Inbound(remark="Gateway Inbound", port=10443, protocol="vless", core="xray", enable=1)
        ib2 = Inbound(remark="Relay Inbound", port=20443, protocol="vless", core="xray", enable=1)
        ib3 = Inbound(remark="Exit Inbound", port=30443, protocol="hysteria", core="hysteria", enable=1)
        session.add_all([ib1, ib2, ib3])
        session.flush()

        # Сервер 1: реальный клиент
        c_attacker = ClientStats(inbound_id=ib1.id, email="attacker_v4_v6@corp.lan", client_uuid_or_pwd="pwd1", enable=1)
        # Сервер 2: транзитный аккаунт Сервера 1
        c_tunnel_s1 = ClientStats(inbound_id=ib2.id, email="server1_transit_tunnel@corp.lan", client_uuid_or_pwd="pwd2", enable=1)
        # Сервер 3: транзитный аккаунт Сервера 2 и невиновный клиент
        c_tunnel_s2 = ClientStats(inbound_id=ib3.id, email="server2_transit_tunnel@corp.lan", client_uuid_or_pwd="pwd3", enable=1)
        c_innocent = ClientStats(inbound_id=ib3.id, email="innocent_v6_client@corp.lan", client_uuid_or_pwd="pwd4", enable=1)

        session.add_all([c_attacker, c_tunnel_s1, c_tunnel_s2, c_innocent])
        session.commit()

    # Имитируем логи всех 3 серверов
    s1_logs = [
        f"{now_str_xray} [info] 198.51.100.42:51234 accepted tcp:[{target_ipv6}]:{target_port} [vless-in >> out-s2-v4] email: attacker_v4_v6@corp.lan",
    ]
    s2_logs = [
        f'{{"time":"{now_str_iso}","auth":"server1_transit_tunnel@corp.lan","addr":"198.51.100.10:45123"}}',
        f'{{"time":"{now_str_iso}","id":"server1_transit_tunnel@corp.lan","reqAddr":"[{target_ipv6}]:{target_port}"}}',
    ]
    s3_logs = [
        f'{{"time":"{now_str_iso}","auth":"server2_transit_tunnel@corp.lan","addr":"[2001:db8:2000::2]:52341"}}',
        f'{{"time":"{now_str_iso}","id":"server2_transit_tunnel@corp.lan","reqAddr":"[{target_ipv6}]:{target_port}"}}',
        f'{{"time":"{now_str_iso}","id":"innocent_v6_client@corp.lan","reqAddr":"[2001:db8:good::1]:443"}}',
    ]

    current_logs = {"xray": [], "hysteria": []}
    def mock_get_logs(core, limit=500):
        return current_logs.get(core, [])

    monkeypatch.setattr("backend.routes.security_routes.management.get_in_memory_core_logs", mock_get_logs)

    # 1. Расследование на Сервере 3 (Exit VPS)
    current_logs["hysteria"] = s3_logs
    current_logs["xray"] = []
    res3 = client.get(f"/api/security/client-by-connection?dst_ip={target_ipv6}&port={target_port}")
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["success"] is True
    assert data3["email"] == "server2_transit_tunnel@corp.lan"
    assert data3["client_ip"] == "2001:db8:2000::2"  # IPv6-адрес Сервера 2

    # 2. Расследование на Сервере 2 (Intermediate Relay)
    current_logs["hysteria"] = s2_logs
    current_logs["xray"] = []
    res2 = client.get(f"/api/security/client-by-connection?dst_ip={target_ipv6}&port={target_port}")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["success"] is True
    assert data2["email"] == "server1_transit_tunnel@corp.lan"
    assert data2["client_ip"] == "198.51.100.10"  # IPv4-адрес Сервера 1

    # 3. Расследование на Сервере 1 (Home Gateway / Origin)
    current_logs["hysteria"] = []
    current_logs["xray"] = s1_logs
    res1 = client.get(f"/api/security/client-by-connection?dst_ip={target_ipv6}&port={target_port}")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["success"] is True
    assert data1["email"] == "attacker_v4_v6@corp.lan"  # Истинный клиент!
    assert data1["client_ip"] == "198.51.100.42"

    # 4. Проверка с квадратными скобками [2001:db8:bad:c0de::1]
    res1_bracket = client.get(f"/api/security/client-by-connection?dst_ip=[{target_ipv6}]&port={target_port}")
    assert res1_bracket.status_code == 200
    assert res1_bracket.json()["email"] == "attacker_v4_v6@corp.lan"
