import json
import pytest
from backend.singbox.service import get_singbox_client_traffic_stats

def test_singbox_traffic_stats_parsing(monkeypatch):
    """Test parsing Sing-box traffic stats via sentinel_core_bridge get_unified_traffic."""
    mock_traffic_data = {
        "client1@test.com": {
            "downBytes": 3096576,
            "upBytes": 1548288,
            "online": True
        },
        "client2@test.com": {
            "downBytes": 500000,
            "upBytes": 100000,
            "online": True
        }
    }

    monkeypatch.setattr("backend.sentinel_core_bridge.get_unified_traffic", lambda: mock_traffic_data)

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


def test_get_preset_details_from_core_api(client, monkeypatch):
    """Test fetching specific preset details dynamically from sentinel-core."""
    import backend.routes.routing_routes.rules
    monkeypatch.setattr(backend.routes.routing_routes.rules, "check_auth", lambda r: True)

    res = client.get("/api/v1/routing/presets/ru")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    obj = data["obj"]
    assert obj["id"] == "ru"
    assert "geosite:yandex" in obj["domains"]
    assert "geoip:ru" in obj["ips"]

