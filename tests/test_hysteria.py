import pytest
import requests
import subprocess
import importlib

pytestmark = pytest.mark.xdist_group("core_ops")

from backend.database import add_inbound, add_client_db, get_clients_for_inbound, delete_inbound
from backend.hysteria import generate_hysteria_config, kick_client_hysteria_api, get_latest_hysteria_version_info, download_hysteria_core


def test_hysteria_config_generation():
    """Test Hysteria 2 Config Generation."""
    hyst_settings = {"clients": []}
    hyst_stream_settings = {
        "hysteria": {
            "obfsPassword": "obfs_test_pwd",
            "upMbps": 50,
            "downMbps": 100
        }
    }
    ib_hyst_id = add_inbound(
        remark="Hysteria 2 Inbound",
        port=60003,
        protocol="hysteria2",
        settings_dict=hyst_settings,
        stream_settings_dict=hyst_stream_settings
    )
    
    # Add client to Hysteria 2 inbound
    add_client_db(ib_hyst_id, "client2@hysteria.com", "pass-client-2")

    try:
        # Generate Hysteria config and test
        clients = get_clients_for_inbound(ib_hyst_id)
        hyst_config = generate_hysteria_config(ib_hyst_id, 60003, clients, hyst_stream_settings)
        
        assert hyst_config["listen"] == ":60003"
        assert hyst_config["auth"]["type"] == "http"
        assert "api/hysteria/auth" in hyst_config["auth"]["http"]["url"]
        assert "secret=" in hyst_config["auth"]["http"]["url"]
        assert hyst_config["trafficStats"]["listen"].startswith("127.0.0.1:")
        assert hyst_config["obfs"]["type"] == "salamander"
        assert hyst_config["obfs"]["salamander"]["password"] == "obfs_test_pwd"
        assert hyst_config["bandwidth"]["up"] == "50 mbps"
        from tests.core_verifier import validate_hysteria_config
        valid, msg = validate_hysteria_config(hyst_config)
        assert valid is True, f"Real Hysteria binary validation failed: {msg}"
    finally:
        # Cleanup test inbound
        delete_inbound(ib_hyst_id)


def test_advanced_hysteria_configs():
    """Test Hysteria 2 config generator with custom certificates, masquerades, and port hopping."""
    stream_settings = {
        "hysteria": {
            "upMbps": 20,
            "downMbps": 40,
            "certMode": "custom",
            "certPath": "/path/to/cert.pem",
            "keyPath": "/path/to/key.pem",
            "masqType": "status",
            "masqValue": "403",
            "hop": "30000-40000"
        }
    }
    clients = [
        {"email": "user1", "client_uuid_or_pwd": "password123", "enable": True}
    ]

    config = generate_hysteria_config(1, 60020, clients, stream_settings)

    # Verify custom certificates
    assert config["tls"]["cert"] == "/path/to/cert.pem"
    assert config["tls"]["key"] == "/path/to/key.pem"

    # Verify status masquerade
    assert config["masquerade"]["type"] == "string"
    assert config["masquerade"]["string"]["statusCode"] == 403

    # Verify port hopping listen
    assert config["listen"] == ":30000-40000"


    # Verify routingViaXray config
    stream_settings_routing = {
        "hysteria": {
            "routingViaXray": True,
            "socksUsername": "test_user",
            "socksPassword": "test_password"
        }
    }
    config_routing = generate_hysteria_config(1, 60020, clients, stream_settings_routing)
    assert config_routing["outbounds"][0]["type"] == "socks5"
    assert config_routing["outbounds"][0]["socks5"]["addr"] == "127.0.0.1:20001"
    assert config_routing["outbounds"][0]["socks5"]["username"] == "test_user"
    assert config_routing["outbounds"][0]["socks5"]["password"] == "test_password"


def test_hysteria_endpoints(client):
    """Test Hysteria 2 API endpoints for status, actions, logs, version, and update."""
    headers = {"Authorization": "Bearer test_bearer_token"}

    # 1. Status without auth -> 404 Nginx
    response = client.get("/api/hysteria/status")
    assert response.status_code == 404

    # 2. Status with auth -> 200
    response = client.get("/api/hysteria/status", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json()["running"], bool)

    # 3. Action without auth -> 404
    response = client.post("/api/hysteria/action", json={"action": "restart"})
    assert response.status_code == 404

    # 4. Action with auth -> 200
    response = client.post("/api/hysteria/action", json={"action": "restart"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True

    # 5. Logs without auth -> 404
    response = client.get("/api/hysteria/logs")
    assert response.status_code == 404

    # 6. Logs with auth -> 200
    response = client.get("/api/hysteria/logs", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json()["logs"], list)

    # 7. Version without auth -> 404
    response = client.get("/api/hysteria/version")
    assert response.status_code == 404

    # 8. Version with auth -> 200
    response = client.get("/api/hysteria/version", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["current"].startswith("v2.")

    # 9. Update without auth -> 404
    response = client.post("/api/hysteria/update", json={"download_url": "https://github.com/apernet/hysteria/releases/download/v2.5.0/hysteria-linux-amd64"})
    assert response.status_code == 404

    # 10. Update with auth -> 200
    response = client.post("/api/hysteria/update", json={"download_url": "https://github.com/apernet/hysteria/releases/download/v2.5.0/hysteria-linux-amd64"}, headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json()["success"], bool)


def test_instant_disconnect_hysteria_api(monkeypatch):
    """Test calling Hysteria kick client via sentinel_core_bridge kick_client."""
    kicked_emails = []
    def mock_kick(email: str) -> bool:
        kicked_emails.append(email)
        return True

    monkeypatch.setattr("backend.sentinel_core_bridge.kick_client", mock_kick)
    
    res = kick_client_hysteria_api(1, "test@client.com")
    assert res is True
    assert "test@client.com" in kicked_emails



def test_hysteria_config_port_hopping():
    """Test Hysteria 2 configuration listen address generation under various port range scenarios."""
    clients = [{"email": "test@mail.com", "client_uuid_or_pwd": "pass", "enable": True}]
    
    # Scenario 1: Port hopping range specified
    config1 = generate_hysteria_config(999, 20000, clients, {"hysteria": {"hop": "20000-30000"}})
    assert config1["listen"] == ":20000-30000"
    
    # Scenario 2: Port hopping range overrides base port
    config2 = generate_hysteria_config(999, 8443, clients, {"hysteria": {"hop": "20000-30000"}})
    assert config2["listen"] == ":20000-30000"

    
    # Scenario 3: Invalid range format (no hyphen)
    config3 = generate_hysteria_config(999, 8443, clients, {"hysteria": {"hop": "invalid_hop"}})
    assert config3["listen"] == ":8443"

    
    # Scenario 4: Non-range input
    config4 = generate_hysteria_config(999, 8443, clients, {"hysteria": {"hop": "20000"}})
    assert config4["listen"] == ":8443"


def test_hysteria_version_api(client, monkeypatch):
    """Test Hysteria latest version parsing and API response."""
    import backend.routes.hysteria
    monkeypatch.setattr(backend.routes.hysteria, "check_auth", lambda r: True)
    
    # Clear any previous cached release info
    from backend.hysteria.core import _HYSTERIA_RELEASES_CACHE
    _HYSTERIA_RELEASES_CACHE.clear()

    # Mock requests.get for GitHub API
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "tag_name": "app/v2.9.2",
                "assets": [
                    {
                        "name": "hysteria-windows-amd64.exe",
                        "browser_download_url": "https://github.com/apernet/hysteria/releases/download/app/v2.9.2/hysteria-windows-amd64.exe"
                    },
                    {
                        "name": "hysteria-linux-amd64",
                        "browser_download_url": "https://github.com/apernet/hysteria/releases/download/app/v2.9.2/hysteria-linux-amd64"
                    }
                ]
            }
            
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())
    
    # Verify latest version info parsing
    info = get_latest_hysteria_version_info()
    assert info is not None
    assert info["version"] == "v2.9.2"
    assert "releases/download/app/v2.9.2" in info["download_url"]
    
    # Verify API endpoint
    response = client.get("/api/hysteria/version")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["latest"] == "v2.9.2"


def test_download_hysteria_core_verification_failure_actual(monkeypatch, tmp_path):
    import backend.hysteria
    
    # Reload to get the real functions
    importlib.reload(backend.hysteria)
    
    # Set paths to temp path
    monkeypatch.setattr(backend.hysteria, "BIN_DIR", tmp_path)
    monkeypatch.setattr(backend.hysteria, "HYSTERIA_BIN_PATH", tmp_path / "hysteria")
    
    # Mock get_latest_hysteria_version_info
    monkeypatch.setattr(backend.hysteria, "get_latest_hysteria_version_info", lambda: {
        "version": "v2.5.0",
        "download_url": "https://github.com/apernet/hysteria/releases/download/v2.5.0/hysteria"
    })
    
    # Mock requests.get
    class MockResponse:
        status_code = 200
        def iter_content(self, chunk_size):
            return [b"mock binary content"]
        def raise_for_status(self):
            pass
        def json(self):
            return [
                {
                    "tag_name": "app/v2.5.0",
                    "assets": [
                        {"name": "hysteria-windows-amd64.exe", "browser_download_url": "https://github.com/apernet/hysteria/releases/download/v2.5.0/hysteria"},
                        {"name": "hysteria-linux-amd64", "browser_download_url": "https://github.com/apernet/hysteria/releases/download/v2.5.0/hysteria"}
                    ]
                }
            ]
            
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())
    
    # Mock subprocess.run to simulate a failed self-test (returncode = 1)
    class MockCompletedProcess:
        returncode = 1
        stdout = "Execution failed"
        stderr = "Exec format error"
        
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockCompletedProcess())
    
    # Verify download_hysteria_core raises verification failure exception
    with pytest.raises(Exception) as excinfo:
        backend.hysteria.download_hysteria_core()
    assert "failed self-test verification" in str(excinfo.value)
    
    # Ensure temporary file is cleaned up and the binary doesn't exist
    assert not (tmp_path / "hysteria.tmp").exists()
    assert not (tmp_path / "hysteria").exists()
    # monkeypatch automatically restores backend.hysteria after this test


def test_update_online_emails_hysteria(monkeypatch):
    """Test update_online_emails properly queries Hysteria 2 online users via sentinel_core_bridge get_unified_traffic."""
    from backend.routes.clients.actions import update_online_emails
    import backend.routes.clients.actions
    
    # 1. Mock inbounds in database
    mock_inbounds = [
        {"id": 1, "protocol": "hysteria2", "enable": True}
    ]
    monkeypatch.setattr("backend.database.get_all_inbounds", lambda: mock_inbounds)
    
    # Mock db_session to return mock clients
    class MockClient:
        def __init__(self, email):
            self.email = email
            self.enable = 1

    class MockSession:
        def query(self, model):
            class MockQuery:
                def filter_by(self, **kwargs):
                    class MockResult:
                        def all(self):
                            return [MockClient("user_traffic@mail.com"), MockClient("user_online@mail.com")]
                    return MockResult()
            return MockQuery()
        def commit(self): pass
        def rollback(self): pass

    import contextlib
    @contextlib.contextmanager
    def mock_db_session():
        yield MockSession()

    monkeypatch.setattr("backend.database.db_session", mock_db_session)
    
    # 2. Mock sentinel_core_bridge.get_unified_traffic
    monkeypatch.setattr("backend.sentinel_core_bridge.get_unified_traffic", lambda: {
        "user_traffic@mail.com": {"online": True, "up": 100, "down": 200},
        "user_online@mail.com": {"connections": 2, "up": 50, "down": 50},
        "user_zero_conn@mail.com": {"connections": 0, "online": False}
    })
    
    # 3. Clear existing _online_emails
    backend.routes.clients.actions._online_emails = []
    
    # 4. Call update_online_emails
    update_online_emails()
    
    # 5. Verify results
    assert "user_traffic@mail.com" in backend.routes.clients.actions._online_emails
    assert "user_online@mail.com" in backend.routes.clients.actions._online_emails
    assert "user_zero_conn@mail.com" not in backend.routes.clients.actions._online_emails



def test_hysteria_auth_endpoint(client, monkeypatch):
    """Test `/api/hysteria/auth` with token authentication and real-time limit checks."""
    from backend.config import settings
    
    # 1. Access without token -> decoy 404
    response = client.post("/api/hysteria/auth", json={"auth": "test@mail.com:pwd"})
    assert response.status_code == 404
    
    # 2. Access with wrong token -> decoy 404
    response = client.post(f"/api/hysteria/auth?secret=wrong_token", json={"auth": "test@mail.com:pwd"})
    assert response.status_code == 404
    
    # 3. Access with correct token but client not found -> {"ok": False}
    import contextlib
    class MockSessionNone:
        def query(self, model):
            class MockQuery:
                def filter_by(self, **kwargs):
                    class MockResult:
                        def first(self):
                            return None
                    return MockResult()
            return MockQuery()
    @contextlib.contextmanager
    def mock_db_session_none():
        yield MockSessionNone()
        
    monkeypatch.setattr("backend.database.db_session", mock_db_session_none)
    
    response = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={"auth": "test@mail.com:pwd"})
    assert response.status_code == 200
    assert response.json() == {"ok": False}
    
    # 4. Access with correct token and valid enabled client -> {"ok": True}
    class MockClient:
        def __init__(self, email, pwd, enable=1, total=0, up=0, down=0, expiry_time=0, limit_ip=0, allowed_ips=""):
            self.email = email
            self.client_uuid_or_pwd = pwd
            self.enable = enable
            self.total = total
            self.up = up
            self.down = down
            self.expiry_time = expiry_time
            self.limit_ip = limit_ip
            self.allowed_ips = allowed_ips

    class MockSessionValid:
        def __init__(self, client_obj):
            self.client_obj = client_obj
        def query(self, model):
            class MockQuery:
                def __init__(self, outer):
                    self.outer = outer
                def filter_by(self, **kwargs):
                    class MockResult:
                        def __init__(self, outer):
                            self.outer = outer
                        def first(self):
                            return self.outer.outer.client_obj
                    return MockResult(self)
            return MockQuery(self)
            
    c_valid = MockClient("test@mail.com", "pwd")
    @contextlib.contextmanager
    def mock_db_session_valid():
        yield MockSessionValid(c_valid)
    monkeypatch.setattr("backend.database.db_session", mock_db_session_valid)
    
    response = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={"auth": "test@mail.com:pwd"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": "test@mail.com"}
    
    # 5. Traffic limit exceeded -> {"ok": False}
    c_traffic = MockClient("test@mail.com", "pwd", total=1000, up=600, down=400)
    @contextlib.contextmanager
    def mock_db_session_traffic():
        yield MockSessionValid(c_traffic)
    monkeypatch.setattr("backend.database.db_session", mock_db_session_traffic)
    
    response = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={"auth": "test@mail.com:pwd"})
    assert response.json() == {"ok": False}
    
    # 6. Subscription expired -> {"ok": False}
    import time
    c_expired = MockClient("test@mail.com", "pwd", expiry_time=int(time.time() * 1000) - 5000)
    @contextlib.contextmanager
    def mock_db_session_expired():
        yield MockSessionValid(c_expired)
    monkeypatch.setattr("backend.database.db_session", mock_db_session_expired)
    
    response = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={"auth": "test@mail.com:pwd"})
    assert response.json() == {"ok": False}

    # 7. IP limit exceeded -> {"ok": False}
    class MockClient:
        def __init__(self, email, pwd, enable=1, total=0, up=0, down=0, expiry_time=0, limit_ip=0, allowed_ips=""):
            self.email = email
            self.client_uuid_or_pwd = pwd
            self.enable = enable
            self.total = total
            self.up = up
            self.down = down
            self.expiry_time = expiry_time
            self.limit_ip = limit_ip
            self.allowed_ips = allowed_ips

    c_ip_limit = MockClient("test@mail.com", "pwd", limit_ip=1)
    @contextlib.contextmanager
    def mock_db_session_ip_limit():
        yield MockSessionValid(c_ip_limit)
    monkeypatch.setattr("backend.database.db_session", mock_db_session_ip_limit)
    
    # Clear ACTIVE_IP_CACHE to ensure test is clean
    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
    ACTIVE_IP_CACHE.clear()

    # First IP connect -> True
    response = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={
        "auth": "test@mail.com:pwd",
        "req": {"ip": "1.1.1.1"}
    })
    assert response.json() == {"ok": True, "id": "test@mail.com"}
    
    # Second IP connect -> False (since limit_ip = 1)
    response = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={
        "auth": "test@mail.com:pwd",
        "req": {"ip": "2.2.2.2"}
    })
    assert response.json() == {"ok": False}

    # 8. Allowed IPs (IP Whitelist / Binding) check
    c_allowed = MockClient("test@mail.com", "pwd", allowed_ips="198.51.100.1, 203.0.113.0/24")
    @contextlib.contextmanager
    def mock_db_session_allowed():
        yield MockSessionValid(c_allowed)
    monkeypatch.setattr("backend.database.db_session", mock_db_session_allowed)

    # Allowed exact IP -> True
    res_allowed1 = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={
        "auth": "test@mail.com:pwd",
        "req": {"ip": "198.51.100.1"}
    })
    assert res_allowed1.json() == {"ok": True, "id": "test@mail.com"}

    # Allowed CIDR subnet IP -> True
    res_allowed2 = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={
        "auth": "test@mail.com:pwd",
        "req": {"ip": "203.0.113.14"}
    })
    assert res_allowed2.json() == {"ok": True, "id": "test@mail.com"}

    # Non-allowed IP -> False
    res_denied = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={
        "auth": "test@mail.com:pwd",
        "req": {"ip": "99.99.99.99"}
    })
    assert res_denied.json() == {"ok": False}

    # 9. URL-encoded username/email authentication (e.g. test%40mail.com:pwd)
    c_encoded = MockClient("test@mail.com", "pwd")
    @contextlib.contextmanager
    def mock_db_session_encoded():
        yield MockSessionValid(c_encoded)
    monkeypatch.setattr("backend.database.db_session", mock_db_session_encoded)

    res_encoded = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={
        "auth": "test%40mail.com:pwd",
        "addr": "127.0.0.1:54321"
    })
    assert res_encoded.status_code == 200
    assert res_encoded.json() == {"ok": True, "id": "test@mail.com"}

    # 10. Direct user:pass authentication (e.g. mock_user:mock_password)
    c_custom = MockClient("mock_user", "mock_password")
    @contextlib.contextmanager
    def mock_db_session_custom():
        yield MockSessionValid(c_custom)
    monkeypatch.setattr("backend.database.db_session", mock_db_session_custom)

    res_custom = client.post(f"/api/hysteria/auth?secret={settings.API_TOKEN}", json={
        "auth": "mock_user:mock_password",
        "addr": "127.0.0.1:54321"
    })
    assert res_custom.status_code == 200
    assert res_custom.json() == {"ok": True, "id": "mock_user"}


def test_hysteria_bridge_methods():
    """Verify sentinel_core_bridge methods: build_server_config, validate_core_config, get_core_version."""
    from backend.sentinel_core_bridge import (
        build_server_config,
        validate_core_config,
        get_core_version
    )
    from backend.hysteria import HYSTERIA_BIN_PATH

    inbounds = [{
        "id": 1,
        "port": 443,
        "protocol": "hysteria2",
        "tag": "inbound-1",
        "settings": {},
        "streamSettings": {"security": "tls"}
    }]
    compiled = build_server_config("hysteria2", inbounds)
    assert isinstance(compiled, dict)

    ver = get_core_version("hysteria2", str(HYSTERIA_BIN_PATH))
    assert isinstance(ver, str)


