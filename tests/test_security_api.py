import pytest
import json
from backend.database import db_session
from backend.models import Inbound, ClientStats

def test_security_auth_decoy(client):
    """
    Проверка, что при неверном или отсутствующем токене эндпоинты возвращают Decoy (404).
    """
    # Без токена
    response = client.get("/api/security/system-status")
    assert response.status_code == 404
    assert "404 Not Found" in response.text
    
    # С неверным токеном
    headers = {"Authorization": "Bearer invalid_token"}
    response = client.get("/api/security/system-status", headers=headers)
    assert response.status_code == 404

def test_security_system_status(client):
    """
    Проверка эндпоинта /api/security/system-status с верным токеном.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.get("/api/security/system-status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "counts" in data
    assert "total_inbounds" in data["counts"]
    assert "total_clients" in data["counts"]

def test_security_backup(client):
    """
    Проверка эндпоинта /api/security/backup.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.get("/api/security/backup", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "dump" in data

def test_security_search_client_and_disable(client):
    """
    Проверка эндпоинтов поиска и блокировки клиента.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Создаем тестового клиента в БД
    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        
        ib = Inbound(
            remark="Test Inbound for Security API",
            port=20800,
            protocol="vless",
            settings="{}",
            stream_settings="{}",
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.flush()
        
        c = ClientStats(
            inbound_id=ib.id,
            email="threat_user@example.com",
            client_uuid_or_pwd="c56a4180-65aa-42ec-a945-5fd21dec0538",
            up=1000,
            down=2000,
            total=1000000,
            expiry_time=0,
            enable=1,
            limit_ip=1,
            block_reason=""
        )
        session.add(c)
        session.commit()

    # 2. Выполняем поиск клиента по email
    response = client.get("/api/security/search-client?key=threat_user@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["clients"]) == 1
    assert data["clients"][0]["client"]["email"] == "threat_user@example.com"
    assert data["clients"][0]["client"]["enable"] == 1

    # 3. Блокируем клиента через API
    response = client.post("/api/security/disable-client", data={"email": "threat_user@example.com"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # 4. Проверяем, что в БД клиент заблокирован
    with db_session() as session:
        c_db = session.query(ClientStats).filter_by(email="threat_user@example.com").first()
        assert c_db.enable == 0
        assert c_db.block_reason == "IPS Auto-blocked"

    # 5. Проверяем поиск заблокированного клиента
    response = client.get("/api/security/search-client?key=threat_user@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["clients"][0]["client"]["enable"] == 0

    # 6. Разблокируем клиента через API /api/security/enable-client
    response = client.post("/api/security/enable-client", data={"email": "threat_user@example.com"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # 7. Проверяем, что в БД клиент снова разблокирован
    with db_session() as session:
        c_db = session.query(ClientStats).filter_by(email="threat_user@example.com").first()
        assert c_db.enable == 1
        assert c_db.block_reason is None

def test_security_client_by_connection_hysteria(client, monkeypatch):
    """
    Проверка поиска клиента по соединению в логах Hysteria через sentinel-core bridge.
    """
    import datetime
    headers = {"Authorization": "Bearer test_bearer_token"}
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    log_content = [
        f'{now_iso}\tinfo\t[socks5] tcp request\t{{"client": "1.2.3.4:5678", "auth": "tunnel_user@example.com", "req": "185.112.14.3:22"}}\n'
    ]
    monkeypatch.setattr("backend.routes.security_routes.management.get_in_memory_core_logs", lambda core, limit: log_content if core == "hysteria" else [])
    
    response = client.get("/api/security/client-by-connection?dst_ip=185.112.14.3&port=22", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["email"] == "tunnel_user@example.com"
    assert data["source"] == "hysteria"


def test_security_client_by_connection_hysteria_v2(client, monkeypatch):
    """
    Проверка поиска клиента по соединению в логах Hysteria 2 (новый формат с id и reqAddr).
    """
    import datetime
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
    from backend.models import ClientTrafficDaily
    import datetime
    
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


def test_telegram_2fa_auth_endpoints(client):
    """
    Проверка маршрутов опроса и действий Telegram 2FA (/api/auth/tg-2fa/poll, /api/auth/tg-2fa/action).
    """
    from backend.models import SystemSetting
    import json
    import time
    
    token = "test_tg_2fa_token_12345"
    
    # 1. Создаем запрос 2FA в SystemSetting
    with db_session() as session:
        session.query(SystemSetting).filter(SystemSetting.key.like("tg_2fa_req_%")).delete()
        
        req = SystemSetting(
            key=f"tg_2fa_req_{token}",
            value=json.dumps({
                "username": "admin",
                "client_ip": "192.168.1.100",
                "status": "pending",
                "expires": time.time() + 120
            })
        )
        session.add(req)
        session.commit()
        
    # 2. Опрашиваем статус (ожидаем pending)
    response = client.get(f"/api/auth/tg-2fa/poll?token={token}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "pending"
    
    # 2.5. Неавторизованный запрос к action -> 404 decoy
    res_unauth = client.post("/api/auth/tg-2fa/action", json={"token": token, "action": "approve"})
    assert res_unauth.status_code == 404

    # 3. Выполняем подтверждение входа (approve) с авторизацией
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.post("/api/auth/tg-2fa/action", json={"token": token, "action": "approve"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # 4. Снова опрашиваем статус (ожидаем approved и установку session_id cookie)
    response = client.get(f"/api/auth/tg-2fa/poll?token={token}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "approved"
    assert "session_id" in response.cookies
    
    # 5. Проверяем блокировку (block) с повторным созданием
    token_block = "test_tg_2fa_token_block"
    with db_session() as session:
        req = SystemSetting(
            key=f"tg_2fa_req_{token_block}",
            value=json.dumps({
                "username": "admin",
                "client_ip": "1.2.3.4",
                "status": "pending",
                "expires": time.time() + 120
            })
        )
        session.add(req)
        session.commit()
        
    response = client.post("/api/auth/tg-2fa/action", json={"token": token_block, "action": "block"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # 6. Опрашиваем статус после блокировки
    response = client.get(f"/api/auth/tg-2fa/poll?token={token_block}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "blocked"


def test_security_whitelist_sync_and_bypass(client):
    """
    Проверка синхронизации белого списка и обхода 2FA и ограничений частоты входа.
    """
    from backend.database import set_setting, get_setting
    from backend.routes.auth import is_ip_whitelisted_sync, check_rate_limit
    
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Синхронизируем белый список с IP "testclient"
    whitelist_payload = {"ips": ["testclient", "1.2.3.4:12345"]}
    response = client.post("/api/security/whitelist/sync", json=whitelist_payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Проверяем, что настройка сохранилась в БД
    assert "testclient" in get_setting("ips_whitelisted_sync", "[]")
    
    # 2. Проверяем работу функции is_ip_whitelisted_sync
    assert is_ip_whitelisted_sync("testclient") is True
    assert is_ip_whitelisted_sync("1.2.3.4") is True
    assert is_ip_whitelisted_sync("9.9.9.9") is False
    
    # 3. Проверяем обход rate limit
    # Сбросим лимиты и включим жесткий лимит на 1 попытку
    set_setting("login_max_attempts", "1")
    set_setting("login_attempts_period", "10")
    try:
        # Для белого IP лимит всегда разрешен (True)
        assert check_rate_limit("testclient") is True
        assert check_rate_limit("testclient") is True
    finally:
        set_setting("login_max_attempts", "5")
        set_setting("login_attempts_period", "60")
        
    # 4. Проверяем обход rate limit при логине через белый список
    # Whitelist bypass: rate limiting пропускается, поэтому login-запрос проходит.
    # Примечание: 2FA не отключается для whitelisted IP (только rate limit bypass),
    # что задокументировано в login.py: "2FA is NOT disabled for whitelisted IPs".
    set_setting("telegram_2fa_enabled", "true")
    try:
        login_payload = {"username": "test_admin", "password": "test_password"}
        response = client.post("/login", json=login_payload)
        # Запрос должен пройти (не заблокирован rate limit)
        assert response.status_code == 200
        assert response.json()["success"] is True
        # Либо 2FA требуется (если telegram настроен), либо нет — оба варианта корректны.
        # Главное — что ответ успешный (rate limit bypass работает).
    finally:
        set_setting("telegram_2fa_enabled", "false")


def test_security_unban_ip(client):
    """
    Проверка разблокировки IP через API /api/security/unban-ip.
    """
    from backend.database import set_setting, get_setting
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    set_setting("banned_login_ips", "1.1.1.1,2.2.2.2,3.3.3.3")
    
    response = client.post("/api/security/unban-ip", data={"ip": "2.2.2.2"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Проверяем, что 2.2.2.2 удален из списка
    banned_ips = get_setting("banned_login_ips", "")
    assert "2.2.2.2" not in banned_ips
    assert "1.1.1.1" in banned_ips
    assert "3.3.3.3" in banned_ips


def test_security_banned_ips_list(client):
    """
    Проверка эндпоинта /api/security/banned-ips с поиском причин в аудите.
    """
    from backend.database import set_setting
    from backend.models import AuditLog
    import time
    
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # Подготавливаем заблокированные IP и логи аудита
    set_setting("banned_login_ips", "1.1.1.1,5.5.5.5")
    
    with db_session() as session:
        session.query(AuditLog).delete()
        log1 = AuditLog(
            timestamp=int(time.time()), 
            username="system", 
            action="login_rate_limited", 
            target="1.1.1.1", 
            details="IP 1.1.1.1 exceeded max login attempts."
        )
        session.add(log1)
        session.commit()
        
    # 1. Запрос без авторизации -> 404 decoy
    response = client.get("/api/security/banned-ips")
    assert response.status_code == 404
    
    # 2. Запрос с авторизацией
    response = client.get("/api/security/banned-ips", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["banned_ips"]) == 2
    
    # Проверяем, что 1.1.1.1 получил причину Bruteforce из аудита
    ip1 = next(item for item in data["banned_ips"] if item["ip"] == "1.1.1.1")
    assert "Bruteforce" in ip1["reason"]
    
    # Проверяем, что 5.5.5.5 получил дефолтную причину (так как лога для него нет)
    ip2 = next(item for item in data["banned_ips"] if item["ip"] == "5.5.5.5")
    assert ip2["reason"] == "2FA-блокировка или настройки"


def test_security_audit_logs(client):
    """
    Проверка эндпоинта /api/security/audit-logs.
    """
    from backend.models import AuditLog
    import time
    
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


def test_security_sessions_management(client):
    """
    Проверка эндпоинтов управления активными сессиями:
    - GET /api/security/sessions
    - POST /api/security/sessions/terminate
    """
    from backend.models import UserSession
    from backend.auth_utils import ACTIVE_SESSIONS, CSRF_TOKENS
    
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Очищаем старые сессии в БД
    with db_session() as session:
        session.query(UserSession).delete()
        session.commit()
        
    ACTIVE_SESSIONS.clear()
    CSRF_TOKENS.clear()
    
    # 2. Добавляем две тестовые сессии в БД и кэш
    sid1 = "session_test_token_1"
    sid2 = "session_test_token_2"
    
    from backend.database.crud.sessions import add_session_db
    add_session_db(sid1, "admin", 1, ip_address="192.168.1.1", user_agent="Mozilla/Windows")
    add_session_db(sid2, "admin", 1, ip_address="10.0.0.1", user_agent="Mozilla/iPhone")
    
    ACTIVE_SESSIONS.add(sid1)
    ACTIVE_SESSIONS.add(sid2)
    CSRF_TOKENS[sid1] = "csrf_token_1"
    CSRF_TOKENS[sid2] = "csrf_token_2"
    
    # 3. Вызываем GET /api/security/sessions (без куки сессии)
    response = client.get("/api/security/sessions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["sessions"]) == 2
    
    # Сверяем IP и User Agent одной из сессий
    s_ips = [s["ip_address"] for s in data["sessions"]]
    assert "192.168.1.1" in s_ips
    assert "10.0.0.1" in s_ips
    
    # 4. Устанавливаем куку сессии sid1, чтобы проверить флаг is_current
    client.cookies.set("session_id", sid1)
    response = client.get("/api/security/sessions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Находим сессию sid1 и проверяем, что is_current == True, а для sid2 == False
    s1_obj = next(s for s in data["sessions"] if s["session_id"] == sid1)
    s2_obj = next(s for s in data["sessions"] if s["session_id"] == sid2)
    assert s1_obj["is_current"] is True
    assert s2_obj["is_current"] is False
    
    # 5. Завершаем сессию sid2 через API
    response = client.post("/api/security/sessions/terminate", json={"session_id": sid2}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Проверяем, что сессия удалилась из БД и из кэша в памяти
    response = client.get("/api/security/sessions", headers=headers)
    assert len(response.json()["sessions"]) == 1
    assert sid2 not in ACTIVE_SESSIONS
    assert sid2 not in CSRF_TOKENS


def test_security_banned_clients_endpoints(client):
    """
    Проверка эндпоинтов GET /api/security/banned-clients и POST /api/security/unban-client:
    1. Без авторизации -> 404 decoy response.
    2. С авторизацией -> корректное получение списка и разблокировка.
    """
    from backend.models import ClientStats, Inbound
    
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Тест безопасности: Запросы без авторизации должны отдавать decoy response (404)
    res_get_unauth = client.get("/api/security/banned-clients")
    assert res_get_unauth.status_code == 404
    
    res_post_unauth = client.post("/api/security/unban-client", json={"email": "test@test.com"})
    assert res_post_unauth.status_code == 404
    
    # 2. Создаем заблокированного клиента в БД
    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        
        ib = Inbound(remark="Test-VLESS", port=44332, protocol="vless", enable=1)
        session.add(ib)
        session.commit()
        
        c1 = ClientStats(
            inbound_id=ib.id,
            email="banned_user@example.com",
            client_uuid_or_pwd="uuid-banned-1",
            enable=0,
            block_reason="Multi-login ban test"
        )
        session.add(c1)
        session.commit()
        
    # 3. Запрос с авторизацией: получаем список
    response = client.get("/api/security/banned-clients", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["banned_clients"]) == 1
    bc = data["banned_clients"][0]
    assert bc["email"] == "banned_user@example.com"
    assert bc["reason"] == "Multi-login ban test"
    assert bc["inbound_remark"] == "Test-VLESS"
    
    # 4. Разблокировка клиента через POST /api/security/unban-client
    unban_res = client.post("/api/security/unban-client", json={"email": "banned_user@example.com"}, headers=headers)
    assert unban_res.status_code == 200
    assert unban_res.json()["success"] is True
    
    # 5. Проверяем, что у клиента в БД сброшен флаго enable=1 и block_reason=""
    with db_session() as session:
        updated = session.query(ClientStats).filter_by(email="banned_user@example.com").first()
        assert updated is not None
        assert updated.enable == 1
        assert updated.block_reason == ""
        
    # 6. Список заблокированных теперь пуст
    response_after = client.get("/api/security/banned-clients", headers=headers)
    assert len(response_after.json()["banned_clients"]) == 0


def test_ws_logs_unauthorized_rejected(client):
    """
    Проверка, что неавторизованные WebSocket-подключения к логам немедленно отклоняются.
    """
    from starlette.websockets import WebSocketDisconnect
    for core in ("xray", "singbox", "hysteria"):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/api/{core}/logs/ws"):
                pass
        # Connection closed due to unauthorized policy violation
        assert excinfo.value.code in (1008, 4401, 1000)


def test_ws_logs_authorized_streaming(client):
    """
    Проверка, что авторизованный пользователь получает стрим логов через WebSocket.
    """
    from backend.auth.sessions import ACTIVE_SESSIONS
    from backend.database import add_session_db
    from backend.log_streamer import push_log_line

    sess_id = "test_ws_stream_session_12345"
    add_session_db(sess_id, "admin", 7)
    ACTIVE_SESSIONS.add(sess_id)
    client.cookies.set("session_id", sess_id)

    with client.websocket_connect("/api/xray/logs/ws") as ws:
        # Push live test line
        push_log_line("xray", "TEST_LIVE_STREAM_LINE_123")
        msg = ws.receive_json()
        assert "event" in msg




