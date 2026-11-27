import pytest
from backend.database import set_setting, get_setting
from backend.routes.auth import is_ip_whitelisted_sync, check_rate_limit


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


def test_security_whitelist_sync_and_bypass(client):
    """
    Проверка синхронизации белого списка и обхода 2FA и ограничений частоты входа.
    """
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
    set_setting("telegram_2fa_enabled", "true")
    try:
        login_payload = {"username": "test_admin", "password": "test_password"}
        response = client.post("/login", json=login_payload)
        # Запрос должен пройти (не заблокирован rate limit)
        assert response.status_code == 200
        assert response.json()["success"] is True
    finally:
        set_setting("telegram_2fa_enabled", "false")
