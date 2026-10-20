import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.version import PANEL_VERSION

@pytest.fixture
def client():
    return TestClient(app)

def test_panel_update_check(client, monkeypatch):
    # Mock authenticated user
    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    
    resp = client.get("/api/system/settings/update/check?force=true")
    assert resp.status_code == 200
    data = resp.json()
    assert "current_version" in data
    assert data["current_version"] == PANEL_VERSION
    assert "latest_version" in data
    assert "has_update" in data

def test_core_update_check(client, monkeypatch):
    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    
    resp = client.get("/api/system/settings/update/core/check?force=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "current_version" in data
    assert "latest_version" in data
    assert "releases" in data
    assert isinstance(data["releases"], list)
    assert "has_update" in data

def test_core_update_apply_dry(client, monkeypatch):
    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    
    # Mock download_core so we don't actually download gigabytes during test
    from updater.core.sentinel_core import SentinelCoreManager
    monkeypatch.setattr(SentinelCoreManager, "download_core", lambda self, tag: True)
    monkeypatch.setattr(SentinelCoreManager, "get_installed_version", lambda self: (True, "v0.0.15"))
    
    resp = client.post("/api/system/settings/update/core/apply", json={"version": "v0.0.15", "force": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["version"] == "v0.0.15"
    assert "успешно" in data["msg"]
