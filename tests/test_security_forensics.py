import time
import datetime
import pytest
from backend.database import db_session
from backend.models import AuditLog, ClientTrafficDaily


def test_security_client_by_connection_hysteria(client, monkeypatch):
    """
    Проверка поиска клиента по соединению в логах Hysteria через sentinel-core bridge.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    log_content = [
        f'{now_iso}\tinfo\t[socks5] tcp request\t{{"client": "1.2.3.4:5678", "auth": "tunnel_user@example.com", "req": "203.0.113.88:22"}}\n'
    ]
    monkeypatch.setattr("backend.routes.security_routes.management.get_in_memory_core_logs", lambda core, limit: log_content if core == "hysteria" else [])
    
    response = client.get("/api/security/client-by-connection?dst_ip=203.0.113.88&port=22", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["email"] == "tunnel_user@example.com"
    assert data["source"] == "hysteria"


def test_security_client_by_connection_hysteria_v2(client, monkeypatch):
    """
    Проверка поиска клиента по соединению в логах Hysteria 2 (новый формат с id и reqAddr).
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    log_content = [
        f'{now_iso} DEBUG\tTCP request\t{{"addr": "198.51.100.42:47534", "id": "test_hysteria_v2_user@vpn.net", "reqAddr": "mtalk.google.com:5228"}}\n',
        f'[Hysteria] {now_iso} DEBUG\tTCP request\t{{"addr": "198.51.100.42:47534", "id": "test_hysteria_v2_user@vpn.net", "reqAddr": "203.0.113.84:22"}}\n'
    ]
    monkeypatch.setattr("backend.routes.security_routes.management.get_in_memory_core_logs", lambda core, limit: log_content if core == "hysteria" else [])
    
    response = client.get("/api/security/client-by-connection?dst_ip=203.0.113.84&port=22", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["email"] == "test_hysteria_v2_user@vpn.net"
    assert data["source"] == "hysteria"
    assert data["client_ip"] == "198.51.100.42"


def test_security_top_traffic(client):
    """
    Проверка эндпоинта /api/security/top-traffic.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    today_str = datetime.date.today().isoformat()
    
    with db_session() as session:
        session.query(ClientTrafficDaily).delete()
        
        t1 = ClientTrafficDaily(
            email="user1@example.com",
            up=1000 * 1024 * 1024,
            down=2000 * 1024 * 1024,
            date=today_str
        )
        t2 = ClientTrafficDaily(
            email="user2@example.com",
            up=5000 * 1024 * 1024,
            down=5000 * 1024 * 1024,
            date=today_str
        )
        session.add(t1)
        session.add(t2)
        session.commit()
        
    response = client.get("/api/security/top-traffic?period=today", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["period"] == "today"
    
    users = data["users"]
    assert len(users) == 2
    assert users[0]["email"] == "user2@example.com"
    assert users[0]["total"] == 10000 * 1024 * 1024
    assert users[1]["email"] == "user1@example.com"
    assert users[1]["total"] == 3000 * 1024 * 1024


def test_security_audit_logs(client):
    """
    Проверка эндпоинта /api/security/audit-logs.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    with db_session() as session:
        session.query(AuditLog).delete()
        log1 = AuditLog(timestamp=int(time.time()) - 10, username="admin", action="login_success", target="1.2.3.4", details="Web password login success")
        log2 = AuditLog(timestamp=int(time.time()), username="bot", action="sync_whitelist", target=None, details="Sync ok")
        session.add(log1)
        session.add(log2)
        session.commit()
        
    # 1. Без авторизации -> 404 decoy
    response = client.get("/api/security/audit-logs")
    assert response.status_code == 404
    
    # 2. С правильной авторизацией -> логи
    response = client.get("/api/security/audit-logs?limit=5", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["logs"]) == 2
    # Должны быть отсортированы по убыванию времени (новые в начале)
    assert data["logs"][0]["username"] == "bot"
    assert data["logs"][1]["username"] == "admin"

    # 3. Фильтрация по поисковому запросу
    response = client.get("/api/security/audit-logs?search=sync", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["logs"]) == 1
    assert data["logs"][0]["action"] == "sync_whitelist"

    response = client.get("/api/security/audit-logs?search=admin", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["logs"]) == 1
    assert data["logs"][0]["username"] == "admin"

    # 4. Проверка очистки логов подключений
    with db_session() as session:
        conn_log1 = AuditLog(timestamp=int(time.time()), username="system", action="xray_connect", target="192.168.1.10", details="Connected")
        conn_log2 = AuditLog(timestamp=int(time.time()), username="system", action="hysteria_connect", target="192.168.1.20", details="Connected")
        session.add(conn_log1)
        session.add(conn_log2)
        session.commit()

    response = client.post("/api/security/audit-logs/clear-connections", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True

    response = client.get("/api/security/audit-logs", headers=headers)
    logs = response.json()["logs"]
    actions = [l["action"] for l in logs]
    assert "xray_connect" not in actions
    assert "hysteria_connect" not in actions
    assert "clear_connection_logs" in actions
