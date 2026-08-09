import json
import pytest
from backend.singbox import (
    is_singbox_running, start_singbox, stop_singbox, restart_singbox,
    get_installed_singbox_version, get_latest_singbox_version_info
)

def test_singbox_version_info_fetching(monkeypatch):
    """Test fetching sing-box stable vs pre-release version info."""
    import requests

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
        def json(self):
            return self._json

    def mock_requests_get(url, **kwargs):
        if "releases/latest" in url:
            return MockResponse(200, {
                "tag_name": "v1.8.0",
                "prerelease": False,
                "assets": [{"name": "sing-box-1.8.0-linux-amd64.tar.gz", "browser_download_url": "https://github.com/SagerNet/sing-box/releases/download/v1.8.0/sing-box-1.8.0-linux-amd64.tar.gz"}]
            })
        elif "releases" in url:
            return MockResponse(200, [
                {
                    "tag_name": "v1.9.0-rc.1",
                    "prerelease": True,
                    "assets": [{"name": "sing-box-1.9.0-rc.1-linux-amd64.tar.gz", "browser_download_url": "https://github.com/SagerNet/sing-box/releases/download/v1.9.0-rc.1/sing-box-1.9.0-rc.1-linux-amd64.tar.gz"}]
                },
                {
                    "tag_name": "v1.8.0",
                    "prerelease": False,
                    "assets": [{"name": "sing-box-1.8.0-linux-amd64.tar.gz", "browser_download_url": "https://github.com/SagerNet/sing-box/releases/download/v1.8.0/sing-box-1.8.0-linux-amd64.tar.gz"}]
                }
            ])
        return MockResponse(404, {})

    monkeypatch.setattr(requests, "get", mock_requests_get)

    stable_info = get_latest_singbox_version_info(include_prerelease=False)
    assert stable_info is not None
    assert stable_info["version"] == "v1.8.0"
    assert stable_info["is_prerelease"] is False

    prerelease_info = get_latest_singbox_version_info(include_prerelease=True)
    assert prerelease_info is not None
    assert prerelease_info["version"] == "v1.9.0-rc.1"
    assert prerelease_info["is_prerelease"] is True

def test_singbox_api_endpoints(client, monkeypatch):
    """Test sing-box API endpoints."""
    import backend.routes.singbox
    monkeypatch.setattr(backend.routes.singbox, "check_auth", lambda r: True)
    monkeypatch.setattr("backend.routes.singbox.is_singbox_running", lambda: True)

    # 1. Status
    res_status = client.get("/api/singbox/status")
    assert res_status.status_code == 200
    assert res_status.json()["running"] is True

    # 2. Config GET
    res_config = client.get("/api/singbox/config")
    assert res_config.status_code == 200
    assert res_config.json()["success"] is True
    assert "config" in res_config.json()

    # 3. Config SAVE
    new_cfg = {"log": {"level": "debug"}, "inbounds": [], "outbounds": []}
    res_save = client.post("/api/singbox/config/save", json={"config": new_cfg})
    assert res_save.status_code == 200
    assert res_save.json()["success"] is True

    # 4. Logs GET & CLEAR
    res_logs = client.get("/api/singbox/logs")
    assert res_logs.status_code == 200
    assert res_logs.json()["success"] is True

    res_clear = client.post("/api/singbox/logs/clear")
    assert res_clear.status_code == 200
    assert res_clear.json()["success"] is True

def test_singbox_config_generation_with_hysteria_and_rules(monkeypatch):
    """Test generating sing-box config with hysteria/hysteria2 outbounds and detailed routing rules."""
    from backend.singbox.config import generate_singbox_config_json

    mock_inbounds = [
        {
            "id": 1,
            "port": 10000,
            "protocol": "vless",
            "enable": 1,
            "core": "singbox",
            "settings": json.dumps({"decryption": "none"}),
            "stream_settings": json.dumps({"security": "none"})
        }
    ]

    mock_outbounds = [
        {
            "id": 1,
            "remark": "Direct",
            "protocol": "freedom",
            "tag": "direct",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 2,
            "remark": "Hysteria 2 Out",
            "protocol": "hysteria2",
            "tag": "hysteria2-out",
            "settings": json.dumps({
                "address": "1.2.3.4",
                "port": 443,
                "password": "secretpassword",
                "obfs_type": "salamander",
                "obfs_password": "obfspassword"
            }),
            "stream_settings": json.dumps({
                "security": "tls",
                "tlsSettings": {"serverName": "example.com", "allowInsecure": False}
            }),
            "enable": 1
        }
    ]

    mock_rules = [
        {
            "id": 1,
            "remark": "Route OpenAI via Hysteria",
            "outbound_tag": "hysteria2-out",
            "inbound_tags": json.dumps(["inbound-1"]),
            "users": json.dumps(["test@example.com"]),
            "domains": json.dumps(["geosite:openai", "domain:chatgpt.com", "regexp:.*\\.ai"]),
            "ips": json.dumps(["geoip:us", "1.1.1.1/32"]),
            "protocols": json.dumps(["tcp", "bittorrent"]),
            "enable": 1
        }
    ]

    monkeypatch.setattr("backend.singbox.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.singbox.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.database.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.database.get_all_routing_rules", lambda: mock_rules)
    monkeypatch.setattr("backend.singbox.config.get_setting", lambda key: "true" if key in ("block_bittorrent", "block_ads") else "false")

    config = generate_singbox_config_json()
    from tests.core_verifier import validate_singbox_config
    valid, msg = validate_singbox_config(config)
    assert valid is True, f"Real sing-box binary validation failed: {msg}"
    assert len(config["inbounds"]) == 1
    assert config["inbounds"][0]["tag"] == "inbound-1"

    assert "outbounds" in config
    hysteria_ob = next((ob for ob in config["outbounds"] if ob.get("tag") == "hysteria2-out"), None)
    assert hysteria_ob is not None
    assert hysteria_ob["type"] == "hysteria2"
    assert hysteria_ob["server"] == "1.2.3.4"
    assert hysteria_ob["server_port"] == 443
    assert hysteria_ob["password"] == "secretpassword"
    assert hysteria_ob["tls"]["enabled"] is True
    assert hysteria_ob["tls"]["server_name"] == "example.com"
    assert hysteria_ob["obfs"]["type"] == "salamander"

    assert "route" in config
    rules = config["route"]["rules"]
    assert len(rules) >= 2  # User rule + system API rule

    user_rule = next((r for r in rules if r.get("outbound") == "hysteria2-out"), None)
    assert user_rule is not None
    assert user_rule["inbound"] == ["inbound-1"]
    assert user_rule["user"] == ["test@example.com"]
    assert "geosite-openai" in user_rule["rule_set"]
    assert "chatgpt.com" in user_rule["domain"]
    assert ".*\\.ai" in user_rule["domain_regex"]
    assert "geoip-us" in user_rule["rule_set"]
    assert "1.1.1.1/32" in user_rule["ip_cidr"]
    assert "tcp" in user_rule["network"]
    assert "bittorrent" in user_rule["protocol"]


def test_update_online_emails_singbox(monkeypatch):
    """Test update_online_emails properly detects Sing-box online clients via Clash API and active IP cache."""
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
        def json(self):
            return self._json

    mock_clash_data = {
        "connections": [
            {
                "download": 1024,
                "upload": 512,
                "metadata": {
                    "user": "singbox_user1@test.com",
                    "sourceIP": "192.168.1.10"
                }
            }
        ]
    }

    import requests
    import backend.routes.clients.actions
    from backend.routes.clients.actions import update_online_emails
    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE

    ACTIVE_IP_CACHE.clear()

    monkeypatch.setattr("backend.xray.is_xray_running", lambda: False)
    monkeypatch.setattr("backend.singbox.is_singbox_running", lambda: True)
    monkeypatch.setattr("backend.singbox.service.is_singbox_running", lambda: True)
    monkeypatch.setattr(requests, "get", lambda url, timeout=2: MockResponse(200, mock_clash_data))

    class MockClient:
        def __init__(self, email):
            self.email = email

    class MockQuery:
        def filter_by(self, **kwargs):
            return self
        def order_by(self, *args):
            return self
        def all(self):
            return [MockClient("singbox_user1@test.com")]

    class MockSession:
        def query(self, model):
            return MockQuery()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr("backend.database.get_all_inbounds", lambda: [])
    monkeypatch.setattr("backend.database.db_session", lambda: MockSession())

    update_online_emails()

    assert "singbox_user1@test.com" in backend.routes.clients.actions._online_emails


