import json
import subprocess
import pytest
from backend.xray import remove_client_api

pytestmark = pytest.mark.xdist_group("core_ops")


def test_instant_disconnect_xray_api(monkeypatch):
    """Test calling gRPC api removeclient function."""
    # Mock is_xray_running to return True
    monkeypatch.setattr("backend.xray.is_xray_running", lambda: True)
    
    called_args = []
    class MockCompletedProcess:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr
            
    def mock_run(args, **kwargs):
        called_args.append(args)
        return MockCompletedProcess(0, "success", "")
        
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    res = remove_client_api(1, "test@client.com")
    assert res is True
    assert any("removeclient" in str(arg) for arg in called_args)


def test_x25519_key_generation_api(client, monkeypatch):
    """Test x25519 key generation API endpoint using real Xray core binary."""
    import backend.routes.xray
    monkeypatch.setattr(backend.routes.xray, "check_auth", lambda r: True)
    
    response = client.get("/api/xray/x25519")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "privateKey" in res_data and len(res_data["privateKey"]) > 10
    assert "publicKey" in res_data and len(res_data["publicKey"]) > 10


def test_api_crud_flow(client):
    """Test full API inbound and client CRUD cycle (using Bearer bypass)."""
    headers = {"Authorization": "Bearer test_bearer_token"}

    # Dynamically find a free port to avoid OS socket bind collision on host
    import socket
    temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    temp_sock.bind(("127.0.0.1", 0))
    free_port = temp_sock.getsockname()[1]
    temp_sock.close()

    # 1. Create Inbound
    payload = {
        "remark": "API CRUD Inbound",
        "port": free_port,
        "protocol": "vless",
        "settings": {},
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "dest": "yahoo.com:443",
                "serverNames": ["yahoo.com"],
                "privateKey": "SBrIvH6Qk70mSKa_ASLAKkbY_Sd6LduyKmlAZMCwiFg",
                "publicKey": "RSgNtsTFmu3_g0HtVRcmW6kNBCYxBYLKH0b1ndNlPHc",
                "shortIds": ["123456"]
            }
        },
        "total": 10737418240,
        "expiryTime": 1780753200000
    }
    response = client.post("/api/inbounds/create", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    ib_id = response.json()["id"]

    # 2. List Inbounds and verify
    list_response = client.get("/panel/api/inbounds/list", headers=headers)
    assert list_response.status_code == 200
    inbounds = list_response.json()["obj"]
    test_ib = next((ib for ib in inbounds if ib["id"] == ib_id), None)
    assert test_ib is not None
    assert test_ib["remark"] == "API CRUD Inbound"
    assert test_ib["protocol"] == "vless"
    assert test_ib["total"] == 10737418240
    assert test_ib["expiryTime"] == 1780753200000

    # 3. Add Client to Inbound
    client_payload = {
        "id": ib_id,
        "settings": json.dumps({
            "clients": [{
                "id": "client-uuid-api",
                "email": "api_client@test.com",
                "enable": True,
                "limitIp": 0,
                "totalGB": 50,
                "expiryTime": 0
            }]
        })
    }
    client_response = client.post("/panel/api/inbounds/addClient", data=client_payload, headers=headers)
    assert client_response.status_code == 200
    assert client_response.json()["success"] is True

    # 4. Get Client Links
    links_response = client.get(f"/panel/api/inbounds/getClientLinks/{ib_id}/api_client@test.com", headers=headers)
    assert links_response.status_code == 200
    assert links_response.json()["success"] is True
    assert len(links_response.json()["obj"]) > 0
    assert "vless://client-uuid-api@" in links_response.json()["obj"][0]

    # 5. Update Client
    update_client_payload = {
        "id": ib_id,
        "settings": json.dumps({
            "clients": [{
                "id": "client-uuid-api",
                "email": "api_client@test.com",
                "enable": False,
                "limitIp": 2,
                "totalGB": 100,
                "expiryTime": 0
            }]
        })
    }
    update_client_response = client.post(
        f"/panel/api/inbounds/updateClient/client-uuid-api", 
        data=update_client_payload, 
        headers=headers
    )
    assert update_client_response.status_code == 200
    assert update_client_response.json()["success"] is True

    # Verify updated client list in lists
    list_response = client.get("/panel/api/inbounds/list", headers=headers)
    test_ib = next((ib for ib in list_response.json()["obj"] if ib["id"] == ib_id), None)
    assert test_ib is not None
    assert test_ib["clientStats"][0]["enable"] is False
    assert test_ib["clientStats"][0]["total"] == 100 * 1024 * 1024 * 1024

    # 6. Delete Client
    del_client_response = client.post(f"/panel/api/inbounds/{ib_id}/delClient/client-uuid-api", headers=headers)
    assert del_client_response.status_code == 200
    assert del_client_response.json()["success"] is True

    # Verify client is removed
    list_response = client.get("/panel/api/inbounds/list", headers=headers)
    test_ib = next((ib for ib in list_response.json()["obj"] if ib["id"] == ib_id), None)
    assert len(test_ib["clientStats"]) == 0

    # 7. Delete Inbound
    del_ib_response = client.post(f"/api/inbounds/delete/{ib_id}", headers=headers)
    assert del_ib_response.status_code == 200
    assert del_ib_response.json()["success"] is True

    # Verify inbound is removed
    list_response = client.get("/panel/api/inbounds/list", headers=headers)
    test_ib = next((ib for ib in list_response.json()["obj"] if ib["id"] == ib_id), None)
    assert test_ib is None


def test_config_endpoints_api(client, monkeypatch):
    """Test getting Xray and Hysteria configurations via API."""
    import backend.routes.xray
    import backend.routes.hysteria
    monkeypatch.setattr(backend.routes.xray, "check_auth", lambda r: True)
    monkeypatch.setattr(backend.routes.hysteria, "check_auth", lambda r: True)
    
    # 1. Test Xray config endpoint
    # Mock XRAY_CONFIG_PATH.exists to return False so it generates config on the fly
    from pathlib import Path
    orig_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self: False if "config.json" in str(self) else orig_exists(self))
    
    response = client.get("/api/xray/config")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "config" in response.json()
    assert "inbounds" in response.json()["config"]

    from tests.core_verifier import validate_xray_config
    valid, msg = validate_xray_config(response.json()["config"])
    assert valid is True, f"Real Xray binary validation failed: {msg}"
    
    # 2. Test Hysteria config endpoint
    response = client.get("/api/hysteria/config")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "configs" in response.json()


def test_inbound_port_collision_validation(client):
    """Test inbound port collision and overlap checks."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    from backend.config import settings

    # 1. Test conflict with Xray API port (10085)
    payload = {
        "remark": "Test collision 10085",
        "port": 10085,
        "protocol": "vless",
        "settings": {}
    }
    response = client.post("/api/inbounds/create", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "зарезервирован для Xray API" in response.json()["msg"]

    # 2. Test conflict with panel port
    payload["port"] = settings.PANEL_PORT
    payload["remark"] = "Test collision panel"
    response = client.post("/api/inbounds/create", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "занят веб-панелью управления" in response.json()["msg"]

    # 3. Test physical OS bind conflict (using socket bind)
    import socket
    # Bind a random available port on all interfaces (0.0.0.0) or loopback
    # Our OS bind check binds to 0.0.0.0, so we should bind to 0.0.0.0 to trigger collision
    temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    temp_sock.bind(("0.0.0.0", 0))
    bound_port = temp_sock.getsockname()[1]
    
    try:
        payload["port"] = bound_port
        payload["remark"] = "Test OS bind conflict"
        response = client.post("/api/inbounds/create", json=payload, headers=headers)
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "уже занят другим процессом в ОС" in response.json()["msg"]
    finally:
        temp_sock.close()


def test_xray_prerelease_version_fetching(client, monkeypatch):
    """Test fetching stable vs pre-release version info."""
    import backend.routes.xray
    import requests
    monkeypatch.setattr(backend.routes.xray, "check_auth", lambda r: True)

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
        def json(self):
            return self._json

    def mock_requests_get(url, **kwargs):
        if "releases/latest" in url:
            return MockResponse(200, {
                "tag_name": "v1.8.24",
                "prerelease": False,
                "assets": [{"name": "Xray-linux-64.zip", "browser_download_url": "https://github.com/XTLS/Xray-core/releases/download/v1.8.24/Xray-linux-64.zip"}]
            })
        elif "releases" in url:
            return MockResponse(200, [
                {
                    "tag_name": "v2.0.0-beta.1",
                    "prerelease": True,
                    "assets": [{"name": "Xray-linux-64.zip", "browser_download_url": "https://github.com/XTLS/Xray-core/releases/download/v2.0.0-beta.1/Xray-linux-64.zip"}]
                },
                {
                    "tag_name": "v1.8.24",
                    "prerelease": False,
                    "assets": [{"name": "Xray-linux-64.zip", "browser_download_url": "https://github.com/XTLS/Xray-core/releases/download/v1.8.24/Xray-linux-64.zip"}]
                }
            ])
        return MockResponse(404, {})

    monkeypatch.setattr(requests, "get", mock_requests_get)

    from backend.xray.core import get_latest_xray_version_info
    stable_info = get_latest_xray_version_info(include_prerelease=False)
    assert stable_info["version"] == "v1.8.24"
    assert stable_info["is_prerelease"] is False

    prerelease_info = get_latest_xray_version_info(include_prerelease=True)
    assert prerelease_info["version"] == "v2.0.0-beta.1"
    assert prerelease_info["is_prerelease"] is True

    res_stable = client.get("/api/xray/version")
    assert res_stable.status_code == 200
    assert res_stable.json()["latest"] == "v1.8.24"
    assert res_stable.json()["is_prerelease"] is False

    res_prerelease = client.get("/api/xray/version?include_prerelease=true")
    assert res_prerelease.status_code == 200
    assert res_prerelease.json()["latest"] == "v2.0.0-beta.1"
    assert res_prerelease.json()["is_prerelease"] is True



