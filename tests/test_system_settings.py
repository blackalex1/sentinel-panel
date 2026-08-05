import os
from backend.database import set_setting, get_setting
import backend.config
from backend.i18n import t, get_available_languages
from backend.host_client import HostClient

def test_server_status_via_agent(client):
    """Test server status endpoint collects stats from mocked host agent."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.get("/panel/api/server/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    obj = data["obj"]
    assert obj["cpu"] == 12.5
    assert obj["mem"]["current"] == 1000000000
    assert obj["mem"]["total"] == 4000000000
    assert obj["swap"]["current"] == 500000000
    assert obj["swap"]["total"] == 2000000000
    assert obj["swap"]["percent"] == 25.0
    assert obj["uptime"] == 7200
    assert obj["netIO"]["up"] == 500000
    assert obj["netIO"]["down"] == 1500000


def test_bbr_endpoints(client):
    """Test BBR query and enable API endpoints with authentication."""
    client.cookies.clear()
    headers = {"Authorization": "Bearer test_bearer_token"}

    # 1. Access BBR status without auth -> decoy 404
    response = client.get("/api/system/bbr")
    assert response.status_code == 404
    assert "404 Not Found" in response.text

    # 2. Access BBR status with auth -> success
    response = client.get("/api/system/bbr", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["bbr_enabled"] is True

    # 3. Access enable BBR without auth -> decoy 404
    response = client.post("/api/system/bbr/enable")
    assert response.status_code == 404

    # 4. Access enable BBR with auth -> success
    response = client.post("/api/system/bbr/enable", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "successfully" in response.json()["msg"]


def test_settings_update_api(client, monkeypatch):
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    orig_path = backend.config.settings.PANEL_SECRET_PATH
    orig_type = get_setting("decoy_type", "none")
    orig_val = get_setting("decoy_value", "company_landing")
    
    patched_saves = []
    def mock_save(new_settings):
        patched_saves.append(new_settings)
        for k, v in new_settings.items():
            setattr(backend.config.settings, k, v)
            
    monkeypatch.setattr(backend.routes.system, "save_settings_to_env", mock_save)
    
    try:
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["decoy_type"] == orig_type
        
        payload = {
            "secret_path": "newsecretpath",
            "decoy_type": "proxy",
            "decoy_value": "https://wikipedia.org"
        }
        response = client.post("/api/settings/update", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        assert len(patched_saves) == 1
        assert patched_saves[0]["PANEL_SECRET_PATH"] == "newsecretpath"
        
        assert get_setting("decoy_type") == "proxy"
        assert get_setting("decoy_value") == "https://wikipedia.org"
        assert backend.config.settings.PANEL_SECRET_PATH == "newsecretpath"
        
    finally:
        backend.config.settings.PANEL_SECRET_PATH = orig_path
        set_setting("decoy_type", orig_type)
        set_setting("decoy_value", orig_val)


def test_ssl_generation_api(client, monkeypatch):
    """Test SSL generation API route."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    monkeypatch.setattr("backend.ssl_utils.request_ssl_cert", lambda d, e: (True, "Cert generated"))
    
    # Test with full credentials
    payload = {"domain": "test.com", "email": "admin@test.com"}
    response = client.post("/api/ssl/generate", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["msg"] == "Cert generated"

    # Test with empty email (should succeed now)
    payload_no_email = {"domain": "test.com", "email": ""}
    response = client.post("/api/ssl/generate", json=payload_no_email)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["msg"] == "Cert generated"

    # Test with empty domain (should fail)
    payload_no_domain = {"domain": "", "email": "admin@test.com"}
    response = client.post("/api/ssl/generate", json=payload_no_domain)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Домен обязателен" in response.json()["msg"]


def test_settings_saving(client, monkeypatch):
    """Test saving system settings options."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    orig_decoy = get_setting("decoy_type", "none")
    
    try:
        payload = {
            "secret_path": "testsecret",
            "decoy_type": "none",
        }
        response = client.post("/api/settings/update", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        assert get_setting("decoy_type") == "none"
    finally:
        set_setting("decoy_type", orig_decoy)


def test_i18n_translation_helper():
    """Test backend i18n translation helper function t()."""
    
    # Test RU translations
    ru_val = t("traffic_limit_exceeded", lang="ru", category="backend")
    assert ru_val == "Лимит трафика исчерпан"
    
    # Test EN translations
    en_val = t("traffic_limit_exceeded", lang="en", category="backend")
    assert en_val == "Traffic limit exceeded"
    
    # Test parameterized RU translations
    ru_param = t("ip_limit_exceeded", lang="ru", category="backend", count=5, limit=3)
    assert ru_param == "Превышен лимит IP (5 > 3)"
    
    # Test parameterized EN translations
    en_param = t("ip_limit_exceeded", lang="en", category="backend", count=5, limit=3)
    assert en_param == "IP limit exceeded (5 > 3)"
    
    # Test fallback to RU if requested language not found
    fallback_val = t("traffic_limit_exceeded", lang="nonexistent", category="backend")
    assert fallback_val == "Лимит трафика исчерпан"
    
    # Test fallback to key if key not found
    key_val = t("nonexistent_key_123", lang="ru", category="backend")
    assert key_val == "nonexistent_key_123"
    
    # Test get_available_languages list
    langs = get_available_languages()
    # Should at least contain RU and EN
    lang_codes = [x["code"] for x in langs]
    assert "ru" in lang_codes
    assert "en" in lang_codes


def test_locales_endpoints(client, monkeypatch):
    """Test locales list and dictionary API endpoints."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    # Test GET /api/locales
    response = client.get("/api/locales")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert any(x["code"] == "ru" for x in res_data["obj"])
    assert any(x["code"] == "en" for x in res_data["obj"])
    
    # Test GET /api/locales/ru
    response = client.get("/api/locales/ru")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "nav_dashboard" in res_data["obj"]
    assert res_data["obj"]["nav_dashboard"] == "Панель"
    
    # Test GET /api/locales/en
    response = client.get("/api/locales/en")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "nav_dashboard" in res_data["obj"]
    assert res_data["obj"]["nav_dashboard"] == "Dashboard"
    
    # Test GET /api/locales/invalid fallback
    response = client.get("/api/locales/invalid_lang")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "nav_dashboard" in res_data["obj"]


def test_system_optimization_endpoints(client, monkeypatch):
    """Test network optimization status and apply endpoints."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    # Test GET /api/system/optimization/status
    response = client.get("/api/system/optimization/status")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["optimized"] is False
    
    # Test POST /api/system/optimization/apply
    response = client.post("/api/system/optimization/apply")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "[Mock] Network optimized." in res_data["msg"]


def test_host_client_dynamic_mock(tmp_path):
    """Test that HostClient switches mock mode dynamically depending on socket presence."""
    socket_file = tmp_path / "test_agent.sock"
    client = HostClient(socket_path=str(socket_file))
    
    # Force self.is_linux = True to test Linux behavior on any platform
    client.is_linux = True
    
    # Initially socket file does not exist -> is_mock is True
    assert client.is_mock is True
    
    # Create the socket file
    with open(socket_file, "w") as f:
        f.write("")
        
    # Socket file exists -> is_mock is False
    assert client.is_mock is False
    
    # Remove socket file
    os.remove(socket_file)
    
    # Socket file removed -> is_mock is True again
    assert client.is_mock is True


def test_warp_endpoints(client, monkeypatch):
    """Test Cloudflare WARP query, install, register, connect, disconnect, and uninstall API endpoints."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    # Access status initially (Mock: not installed, not connected)
    response = client.get("/api/system/warp/status")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["installed"] is False
    assert res_data["connected"] is False
    assert res_data["dependent_rules"] == []
    assert res_data.get("quota") == 0
    assert res_data.get("usage") == 0

    # Install WARP
    response = client.post("/api/system/warp/install")
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Status check after install (should be installed & connected in mock)
    response = client.get("/api/system/warp/status")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["installed"] is True
    assert res_data["connected"] is True
    assert res_data["type"] == "free"
    assert res_data.get("quota") == 0
    assert res_data.get("usage") == 0

    # Try applying invalid short license key (should fail)
    response = client.post("/api/system/warp/register", json={"license_key": "short"})
    assert response.status_code == 200
    assert response.json()["success"] is False

    # Try applying valid long license key (should succeed)
    response = client.post("/api/system/warp/register", json={"license_key": "valid_license_key_long_enough"})
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Check status again (type should be plus now)
    response = client.get("/api/system/warp/status")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["type"] == "plus"
    assert res_data["license"] == "valid_license_key_long_enough"
    assert res_data.get("quota") == 100 * 1024 * 1024 * 1024
    assert res_data.get("usage") == 25 * 1024 * 1024 * 1024

    # Disconnect WARP
    response = client.post("/api/system/warp/disconnect")
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Status check after disconnect
    response = client.get("/api/system/warp/status")
    assert response.status_code == 200
    assert response.json()["connected"] is False

    # Connect WARP again
    response = client.post("/api/system/warp/connect")
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Status check after connect
    response = client.get("/api/system/warp/status")
    assert response.status_code == 200
    assert response.json()["connected"] is True

    # Uninstall WARP
    response = client.post("/api/system/warp/uninstall")
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Status check after uninstall
    response = client.get("/api/system/warp/status")
    assert response.status_code == 200
    assert response.json()["installed"] is False
    assert response.json()["connected"] is False


def test_telegram_settings_api(client, monkeypatch):
    """Test saving and loading Telegram settings via database, ensuring masking works."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    # Mock bot restart
    monkeypatch.setattr("backend.bot_manager.restart_telegram_bot", lambda: True)
    
    orig_token = get_setting("telegram_bot_token", "")
    orig_ids = get_setting("telegram_admin_ids", "")
    orig_bot_enabled = get_setting("telegram_bot_enabled", "true")
    
    try:
        # Save new values
        payload = {
            "telegram_bot_token": "987654:XYZ-TEST",
            "telegram_admin_ids": "11111,22222",
            "telegram_bot_enabled": False
        }
        response = client.post("/api/settings/update", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        # Verify saved in database
        assert get_setting("telegram_bot_token") == "987654:XYZ-TEST"
        assert get_setting("telegram_admin_ids") == "11111,22222"
        assert get_setting("telegram_bot_enabled") == "false"
        
        # Verify retrieved in GET route (should be masked with dots)
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["telegram_bot_token"] == "••••••••"
        assert data["telegram_admin_ids"] == "11111,22222"
        assert data["telegram_bot_enabled"] is False

        # Verify updating with "••••••••" preserves the token in DB
        payload = {
            "telegram_bot_token": "••••••••",
            "telegram_admin_ids": "33333,44444",
            "telegram_bot_enabled": True
        }
        response = client.post("/api/settings/update", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert get_setting("telegram_bot_token") == "987654:XYZ-TEST"
        assert get_setting("telegram_admin_ids") == "33333,44444"
        assert get_setting("telegram_bot_enabled") == "true"

        # Verify empty token is returned as empty string, not masked
        payload = {
            "telegram_bot_token": "",
            "telegram_admin_ids": "33333,44444",
            "telegram_bot_enabled": True
        }
        response = client.post("/api/settings/update", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert get_setting("telegram_bot_token") == ""
        
        response = client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["telegram_bot_token"] == ""
        
    finally:
        set_setting("telegram_bot_token", orig_token)
        set_setting("telegram_admin_ids", orig_ids)
        set_setting("telegram_bot_enabled", orig_bot_enabled)


def test_get_telegram_token_api(client, monkeypatch):
    """Test retrieving raw Telegram token via the dedicated protected API endpoint."""
    import backend.routes.system
    
    orig_token = get_setting("telegram_bot_token", "")
    try:
        set_setting("telegram_bot_token", "my-secret-bot-token")
        
        # 1. Unauthenticated request -> should return decoy (404)
        monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: False)
        response = client.get("/api/settings/telegram/token")
        assert response.status_code == 404
        assert "404 Not Found" in response.text
        
        # 2. Authenticated request -> should return the actual token
        monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
        response = client.get("/api/settings/telegram/token")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["token"] == "my-secret-bot-token"
        
        # 3. Authenticated request when token is empty
        set_setting("telegram_bot_token", "")
        response = client.get("/api/settings/telegram/token")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["token"] == ""
        
    finally:
        set_setting("telegram_bot_token", orig_token)


def test_restart_telegram_bot_api(client, monkeypatch):
    """Test the manual Telegram bot restart API endpoint."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    # Mock bot restart to return True
    monkeypatch.setattr("backend.bot_manager.restart_telegram_bot", lambda: True)
    response = client.post("/api/system/telegram/restart")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "успешно перезапущен" in response.json()["msg"]
    
    # Mock bot restart to return False (error state)
    monkeypatch.setattr("backend.bot_manager.restart_telegram_bot", lambda: False)
    response = client.post("/api/system/telegram/restart")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Не удалось запустить" in response.json()["msg"]

def test_change_backup_password_api(client, monkeypatch):
    """Test the POST /api/settings/backup/password API endpoint."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    orig_pwd = get_setting("backup_password", "")
    orig_encrypt = get_setting("backup_encrypt", "false")
    set_setting("backup_password", "initial-backup-pwd")
    set_setting("backup_encrypt", "true")
    
    try:
        headers = {"Authorization": "Bearer test_bearer_token"}
        
        # 1. Mismatching current password
        payload = {
            "current_password": "wrong-current-pwd",
            "new_password": "new-backup-pwd"
        }
        response = client.post("/api/settings/backup/password", json=payload, headers=headers)
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "Неверный текущий пароль" in response.json()["msg"]
        
        # 2. Empty fields
        payload = {
            "current_password": "",
            "new_password": "new-backup-pwd"
        }
        response = client.post("/api/settings/backup/password", json=payload, headers=headers)
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "Заполните все поля" in response.json()["msg"]
        
        # 3. Successful password change
        payload = {
            "current_password": "initial-backup-pwd",
            "new_password": "new-backup-pwd"
        }
        response = client.post("/api/settings/backup/password", json=payload, headers=headers)
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert "успешно изменен" in response.json()["msg"]
        
        # Check database value has changed
        assert get_setting("backup_password") == "new-backup-pwd"
    finally:
        set_setting("backup_password", orig_pwd)
        set_setting("backup_encrypt", orig_encrypt)


