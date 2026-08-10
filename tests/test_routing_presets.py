import json
import pytest
from backend.singbox.service import get_singbox_client_traffic_stats

def test_singbox_traffic_stats_parsing(monkeypatch):
    """Test parsing Sing-box Clash API connections response over loopback."""
    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
        def json(self):
            return self._json

    mock_clash_data = {
        "connections": [
            {
                "download": 1048576,
                "upload": 524288,
                "metadata": {"user": "client1@test.com"}
            },
            {
                "download": 2048000,
                "upload": 1024000,
                "metadata": {"user": "client1@test.com"}
            },
            {
                "download": 500000,
                "upload": 100000,
                "metadata": {"user": "client2@test.com"}
            }
        ]
    }

    import requests
    monkeypatch.setattr("backend.singbox.service.is_singbox_running", lambda: True)
    monkeypatch.setattr(requests, "get", lambda url, timeout=2: MockResponse(200, mock_clash_data))

    stats = get_singbox_client_traffic_stats()
    assert "client1@test.com" in stats
    assert stats["client1@test.com"]["down"] == 3096576
    assert stats["client1@test.com"]["up"] == 1548288
    assert stats["client2@test.com"]["down"] == 500000
    assert stats["client2@test.com"]["up"] == 100000


def test_routing_rules_export_import_api(client, monkeypatch):
    """Test exporting and importing routing rules presets via API."""
    import backend.routes.routing_routes.rules
    monkeypatch.setattr(backend.routes.routing_routes.rules, "check_auth", lambda r: True)

    # 1. Export rules
    res_export = client.get("/api/routing/rules/export")
    assert res_export.status_code == 200
    assert res_export.json()["success"] is True
    assert "preset" in res_export.json()
    assert "rules" in res_export.json()["preset"]

    # 2. Import preset rules (Append mode)
    preset_payload = {
        "mode": "append",
        "preset": {
            "version": 1,
            "rules": [
                {
                    "remark": "Test Imported Rule 1",
                    "outbound_tag": "direct",
                    "domains": ["geosite:test"],
                    "enable": 1
                }
            ]
        }
    }
    res_import = client.post("/api/routing/rules/import", json=preset_payload)
    assert res_import.status_code == 200
    assert res_import.json()["success"] is True
    assert res_import.json()["imported"] == 1

    # Verify rule was added
    res_rules = client.get("/api/routing/rules")
    assert res_rules.status_code == 200
    imported_rule = next((r for r in res_rules.json()["obj"] if r["remark"] == "Test Imported Rule 1"), None)
    assert imported_rule is not None
    assert imported_rule["outbound_tag"] == "direct"
    assert "geosite:test" in imported_rule["domains"]

    # Clean up imported rule
    client.post(f"/api/routing/rules/delete/{imported_rule['id']}")
