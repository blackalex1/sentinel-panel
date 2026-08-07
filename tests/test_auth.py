import json
import time
import hmac
import hashlib
import urllib.parse
import pytest
import httpx
from backend.database import set_setting

@pytest.fixture(autouse=True)
def reset_decoy_settings():
    yield
    try:
        set_setting("decoy_type", "none")
        set_setting("decoy_value", "company_landing")
    except Exception:
        pass

# Helper function to generate signed Telegram initData
def make_telegram_init_data(user_id: int, username: str, bot_token: str, expired: bool = False) -> str:
    auth_date = int(time.time()) - (90000 if expired else 0)  # > 24h ago
    user_data = {"id": user_id, "username": username, "first_name": "Test"}
    params = {
        "auth_date": str(auth_date),
        "query_id": "AAH_test",
        "user": json.dumps(user_data)
    }
    # Sort and sign
    sorted_params = sorted(params.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
    
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    params["hash"] = calc_hash
    return urllib.parse.urlencode(params)


def test_fastapi_decoy_protection(client):
    """Test Stealth Mode (returns standard Nginx 404 page for unauthorized access)."""
    # Root page access without authorization -> decoy Nginx 404
    response = client.get("/")
    assert response.status_code == 404
    assert "404 Not Found" in response.text
    assert "nginx" in response.text

    # Access random invalid path -> decoy Nginx 404
    response = client.get("/random_path")
    assert response.status_code == 404
    assert "404 Not Found" in response.text

    # Access API list endpoint without token or cookie -> decoy Nginx 404
    response = client.get("/panel/api/inbounds/list")
    assert response.status_code == 404
    assert "404 Not Found" in response.text

    # Access Swagger documentation (which must be disabled) -> decoy Nginx 404
    response = client.get("/docs")
    assert response.status_code == 404
    assert "404 Not Found" in response.text
    
    response = client.get("/openapi.json")
    assert response.status_code == 404
    assert "404 Not Found" in response.text

    # Access POST-only route with GET (Method Not Allowed) -> decoy Nginx 404
    response = client.get("/login")
    assert response.status_code == 404
    assert "404 Not Found" in response.text
    assert "nginx" in response.text



def test_fastapi_bearer_auth(client):
    """Test API Bearer token authentication."""
    # Invalid Bearer Token -> Decoy 404
    response = client.get("/panel/api/inbounds/list", headers={"Authorization": "Bearer wrong_token"})
    assert response.status_code == 404
    assert "nginx" in response.text

    # Valid Bearer Token -> Success (Empty list initially)
    response = client.get("/panel/api/inbounds/list", headers={"Authorization": "Bearer test_bearer_token"})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_login_json(client):
    """Test login with JSON payload (used by SPA frontend)."""
    client.cookies.clear()
    login_payload = {"username": "test_admin", "password": "test_password"}
    response = client.post("/login", json=login_payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.cookies.get("session_id") is not None

    # Test incorrect credentials with JSON
    client.cookies.clear()
    login_payload_wrong = {"username": "test_admin", "password": "wrong_password"}
    response = client.post("/login", json=login_payload_wrong)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Неверный" in response.json()["msg"]


def test_login_missing_credentials(client):
    """Test login with missing credentials returns decoy 404."""
    client.cookies.clear()
    
    # 1. Missing credentials in JSON
    response = client.post("/login", json={})
    assert response.status_code == 404
    assert "404 Not Found" in response.text

    # 2. Missing credentials in Form Data
    response = client.post("/login", data={})
    assert response.status_code == 404
    assert "404 Not Found" in response.text


def test_fastapi_session_and_csrf(client):
    """Test Cookie-based sessions & CSRF tokens protection."""
    # 1. Login with correct credentials
    login_data = {"username": "test_admin", "password": "test_password"}
    response = client.post("/login", data=login_data)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Store session cookie
    session_cookie = response.cookies.get("session_id")
    assert session_cookie is not None

    # 2. Get CSRF Token
    client.cookies.set("session_id", session_cookie)
    csrf_response = client.get("/csrf-token")
    assert csrf_response.status_code == 200
    csrf_token = csrf_response.json()["obj"]
    assert csrf_token is not None

    # 3. Request without CSRF token on POST -> should get decoy 404
    payload = {
        "remark": "CSRF test",
        "port": 9999,
        "protocol": "vmess",
        "settings": {}
    }
    response = client.post("/api/inbounds/create", json=payload)
    assert response.status_code == 404
    assert "nginx" in response.text

    # 4. Request with valid CSRF token -> success
    headers = {"X-CSRF-Token": csrf_token}
    response = client.post("/api/inbounds/create", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True

    # Cleanup created inbound
    inbound_id = response.json()["id"]
    client.post(f"/api/inbounds/delete/{inbound_id}", headers=headers)


def test_fastapi_telegram_webapp_auth(client):
    """Test Telegram WebApp initData HMAC verification."""
    # 1. Authorized Telegram Admin (ID 55555) -> Success
    init_data = make_telegram_init_data(55555, "admin_user", "123456:ABC-DEF1234ghIkl-zyx")
    response = client.post("/api/auth/telegram", json={"initData": init_data})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "token" in response.json()
    assert response.cookies.get("session_id") is not None

    # 2. Unauthorized Telegram user (ID 99999, not in whitelist) -> 403 Forbidden
    init_data_unauth = make_telegram_init_data(99999, "regular_user", "123456:ABC-DEF1234ghIkl-zyx")
    response = client.post("/api/auth/telegram", json={"initData": init_data_unauth})
    assert response.status_code == 403
    assert "белом списке" in response.json()["msg"]

    # 3. Expired authentication time (>24h) -> 401 Unauthorized
    init_data_expired = make_telegram_init_data(55555, "admin_user", "123456:ABC-DEF1234ghIkl-zyx", expired=True)
    response = client.post("/api/auth/telegram", json={"initData": init_data_expired})
    assert response.status_code == 401

    # 4. Tampered Signature (wrong bot token) -> 401 Unauthorized
    init_data_tampered = make_telegram_init_data(55555, "admin_user", "wrong_bot_token")
    response = client.post("/api/auth/telegram", json={"initData": init_data_tampered})
    assert response.status_code == 401


def test_decoy_system_static(client):
    set_setting("decoy_type", "static")
    set_setting("decoy_value", "company_landing")
    
    response = client.get("/")
    assert response.status_code == 200
    assert "Nimbus Digital Solutions" in response.text


def test_decoy_system_drop(client):
    set_setting("decoy_type", "drop")
    
    with pytest.raises(Exception):
        client.get("/", timeout=0.1)


def test_decoy_system_none(client):
    set_setting("decoy_type", "none")
    
    response = client.get("/")
    assert response.status_code == 404
    assert "404 Not Found" in response.text
    assert "nginx" in response.text


@pytest.mark.anyio
async def test_decoy_system_proxy(client, monkeypatch):
    set_setting("decoy_type", "proxy")
    set_setting("decoy_value", "https://httpbin.org")
    
    # Mock httpx.AsyncClient.request
    class MockResponse:
        def __init__(self):
            self.status_code = 200
            self.content = b"mocked proxy site content"
            self.headers = {"content-type": "text/html"}
            
    async def mock_request(*args, **kwargs):
        return MockResponse()
        
    monkeypatch.setattr(httpx.AsyncClient, "request", mock_request)
    
    response = client.get("/some-other-path")
    assert response.status_code == 200
    assert "mocked proxy site content" in response.text


def test_decoy_system_redirect(client):
    set_setting("decoy_type", "redirect")
    set_setting("decoy_value", "https://google.com")
    
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://google.com"


def test_login_rate_limiting(client):
    """Test login rate limiting triggers correctly and respects custom db settings."""
    from backend.routes.auth import LOGIN_ATTEMPTS
    LOGIN_ATTEMPTS.clear()
    
    # Configure tight rate limit thresholds (3 attempts, 0s delay for fast tests)
    set_setting("login_max_attempts", "3")
    set_setting("login_attempts_period", "10")
    set_setting("login_fail_delay", "0.0")
    
    try:
        login_payload = {"username": "test_admin", "password": "wrong_password"}
        
        # 1st failed attempt
        response = client.post("/login", json=login_payload)
        assert response.status_code == 200
        assert response.json()["success"] is False
        
        # 2nd failed attempt
        response = client.post("/login", json=login_payload)
        assert response.status_code == 200
        assert response.json()["success"] is False
        
        # 3rd failed attempt
        response = client.post("/login", json=login_payload)
        assert response.status_code == 200
        assert response.json()["success"] is False
        
        # 4th failed attempt -> 429 Too Many Requests (Blocked)
        response = client.post("/login", json=login_payload)
        assert response.status_code == 429
        assert response.json()["success"] is False
        assert "Слишком много попыток" in response.json()["msg"]
        
    finally:
        # Restore settings
        LOGIN_ATTEMPTS.clear()
        set_setting("login_max_attempts", "5")
        set_setting("login_attempts_period", "60")
        set_setting("login_fail_delay", "1.0")


def test_change_credentials(client):
    """Test changing admin username and password."""
    client.cookies.clear()
    
    # 1. Login
    login_payload = {"username": "test_admin", "password": "test_password"}
    response = client.post("/login", json=login_payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    session_cookie = response.cookies.get("session_id")
    client.cookies.set("session_id", session_cookie)
    
    csrf_res = client.get("/csrf-token")
    csrf_token = csrf_res.json()["obj"]
    
    try:
        # 2. Try to change credentials with wrong current password
        change_payload = {
            "current_password": "wrong_password",
            "new_username": "new_admin",
            "new_password": "new_password"
        }
        response = client.post(
            "/api/settings/credentials",
            json=change_payload,
            headers={"X-CSRF-Token": csrf_token}
        )
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "Неверный текущий" in response.json()["msg"]
        
        # 3. Change credentials with correct password
        change_payload["current_password"] = "test_password"
        response = client.post(
            "/api/settings/credentials",
            json=change_payload,
            headers={"X-CSRF-Token": csrf_token}
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        # 4. Old login should now fail
        client.cookies.clear()
        login_payload = {"username": "test_admin", "password": "test_password"}
        response = client.post("/login", json=login_payload)
        assert response.status_code == 200
        assert response.json()["success"] is False
        
        # 5. New login should succeed
        login_payload_new = {"username": "new_admin", "password": "new_password"}
        response = client.post("/login", json=login_payload_new)
        assert response.status_code == 200
        assert response.json()["success"] is True
        
        session_cookie_new = response.cookies.get("session_id")
        client.cookies.set("session_id", session_cookie_new)
        
        # 6. Revert back for other tests
        csrf_res = client.get("/csrf-token")
        csrf_token = csrf_res.json()["obj"]
        revert_payload = {
            "current_password": "new_password",
            "new_username": "test_admin",
            "new_password": "test_password"
        }
        response = client.post(
            "/api/settings/credentials",
            json=revert_payload,
            headers={"X-CSRF-Token": csrf_token}
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
    finally:
        # Guarantee database state is reverted for other tests
        from backend.database import update_admin_credentials
        update_admin_credentials("new_admin", "test_admin", "test_password")


def test_2fa_flow(client):
    """Test complete 2FA setup, login challenge, and disabling flow."""
    from backend.totp import get_totp_token
    client.cookies.clear()
    
    # 1. Login
    login_payload = {"username": "test_admin", "password": "test_password"}
    response = client.post("/login", json=login_payload)
    assert response.status_code == 200
    
    session_cookie = response.cookies.get("session_id")
    client.cookies.set("session_id", session_cookie)
    
    csrf_res = client.get("/csrf-token")
    csrf_token = csrf_res.json()["obj"]
    
    # 2. Get 2FA setup
    response = client.get("/api/settings/2fa/setup")
    assert response.status_code == 200
    assert response.json()["success"] is True
    secret = response.json()["secret"]
    assert len(secret) == 32
    
    # 3. Try to enable with wrong code
    response = client.post(
        "/api/settings/2fa/enable",
        json={"code": "000000"},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Неверный код" in response.json()["msg"]
    
    # 4. Enable with correct code
    correct_code = get_totp_token(secret)
    response = client.post(
        "/api/settings/2fa/enable",
        json={"code": correct_code},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 5. Log out
    client.post("/api/logout")
    client.cookies.clear()
    
    # 6. Login without 2FA code -> should require 2FA
    response = client.post("/login", json=login_payload)
    assert response.status_code == 200
    assert response.json().get("requires_2fa") is True
    
    # 7. Login with incorrect 2FA code
    login_payload_wrong_2fa = {
        "username": "test_admin",
        "password": "test_password",
        "code": "111111"
    }
    response = client.post("/login", json=login_payload_wrong_2fa)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Неверный код" in response.json()["msg"]
    
    # 8. Login with correct 2FA code
    login_payload_correct_2fa = {
        "username": "test_admin",
        "password": "test_password",
        "code": get_totp_token(secret)
    }
    response = client.post("/login", json=login_payload_correct_2fa)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    session_cookie_2fa = response.cookies.get("session_id")
    client.cookies.set("session_id", session_cookie_2fa)
    
    csrf_res = client.get("/csrf-token")
    csrf_token = csrf_res.json()["obj"]
    
    # 9. Try to disable with incorrect code
    response = client.post(
        "/api/settings/2fa/disable",
        json={"code": "111111"},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200
    assert response.json()["success"] is False
    
    # 10. Disable with correct code
    correct_code_disable = get_totp_token(secret)
    response = client.post(
        "/api/settings/2fa/disable",
        json={"code": correct_code_disable},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 11. Log out and verify login no longer requires 2FA
    client.post("/api/logout")
    client.cookies.clear()
    response = client.post("/login", json=login_payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json().get("requires_2fa") is not True


def test_file_permissions():
    """Verify that file permissions functions run successfully."""
    import os
    from backend.config import ENV_FILE, DB_PATH
    
    # Ensure database initialization set permissions if file exists
    if ENV_FILE.exists():
        assert os.path.exists(ENV_FILE)
        # Verify chmod works and doesn't raise exception
        os.chmod(ENV_FILE, 0o600)
    
    if os.path.exists(DB_PATH):
        os.chmod(DB_PATH, 0o600)


def test_2fa_session_eviction(client):
    """Test that toggling 2FA terminates all other active sessions of the user."""
    from backend.totp import get_totp_token
    from backend.database import db_session, add_session_db
    from backend.models import UserSession
    client.cookies.clear()
    
    # 1. Login to establish current active session
    login_payload = {"username": "test_admin", "password": "test_password"}
    response = client.post("/login", json=login_payload)
    assert response.status_code == 200
    
    current_sid = response.cookies.get("session_id")
    client.cookies.set("session_id", current_sid)
    
    csrf_res = client.get("/csrf-token")
    csrf_token = csrf_res.json()["obj"]
    
    # 2. Programmatically inject another active session in the database for the same user
    with db_session() as session:
        # Delete existing sessions to start clean
        session.query(UserSession).filter_by(username="test_admin").delete()
        session.commit()
    
    # Re-insert the current session
    add_session_db(current_sid, "test_admin", 7)
    # Insert another session (simulating logged in on another device)
    other_sid = "fake_other_device_session_id_12345"
    add_session_db(other_sid, "test_admin", 7)
    
    # Verify both sessions exist
    with db_session() as session:
        sessions = session.query(UserSession).filter_by(username="test_admin").all()
        assert len(sessions) == 2
        
    # 3. Setup 2FA
    response = client.get("/api/settings/2fa/setup")
    secret = response.json()["secret"]
    
    # 4. Enable 2FA
    correct_code = get_totp_token(secret)
    response = client.post(
        "/api/settings/2fa/enable",
        json={"code": correct_code},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 5. Verify other session is evicted, while current is kept
    with db_session() as session:
        sessions = session.query(UserSession).filter_by(username="test_admin").all()
        assert len(sessions) == 1
        assert sessions[0].session_id == current_sid
        
    # 6. Inject another session again
    add_session_db(other_sid, "test_admin", 7)
    
    with db_session() as session:
        sessions = session.query(UserSession).filter_by(username="test_admin").all()
        assert len(sessions) == 2
        
    # 7. Disable 2FA
    correct_code_disable = get_totp_token(secret)
    response = client.post(
        "/api/settings/2fa/disable",
        json={"code": correct_code_disable},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 8. Verify other session is evicted again, and current is kept
    with db_session() as session:
        sessions = session.query(UserSession).filter_by(username="test_admin").all()
        assert len(sessions) == 1
        assert sessions[0].session_id == current_sid


def test_static_css_components_accessibility():
    from backend.main import app
    from backend.config import settings
    from fastapi.testclient import TestClient
    unauth_client = TestClient(app)
    secret = settings.PANEL_SECRET_PATH
    
    # CSS component files should be accessible unauthenticated (HTTP 200)
    for css_file in ["forms.css", "tables.css", "buttons.css", "scrollbars.css"]:
        res = unauth_client.get(f"/{secret}/css/components/{css_file}")
        assert res.status_code == 200, f"Expected 200 for {css_file}, got {res.status_code}"

    # HTML components should NOT be accessible unauthenticated (Decoy 404 response)
    res_comp = unauth_client.get(f"/{secret}/components/dashboard.html")
    assert res_comp.status_code == 404, f"Expected 404 decoy for HTML component, got {res_comp.status_code}"

    # Path traversal attempt to bypass component protection should still be caught
    res_traversal = unauth_client.get(f"/{secret}/css/components/../../components/dashboard.html")
    assert res_traversal.status_code in (400, 404), f"Path traversal failed to block component access, got {res_traversal.status_code}"

    # Traversal attempting to escape root directory should be blocked by Starlette StaticFiles
    res_outside = unauth_client.get(f"/{secret}/../../backend/main.py")
    assert res_outside.status_code in (400, 404), f"Path traversal outside frontend allowed, got {res_outside.status_code}"


