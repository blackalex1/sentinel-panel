import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.version import PANEL_VERSION
from backend.routes.system.settings_routes.update import _detect_installed_core_version, _get_bin_dir

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

def test_core_update_standalone_fallback(client, monkeypatch):
    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    
    # Simulate updater module failure
    def mock_broken_mgr(*args, **kwargs):
        raise ImportError("No module named 'updater'")
    
    monkeypatch.setattr("updater.core.sentinel_core.SentinelCoreManager", mock_broken_mgr)
    
    # Mock standalone fallback to succeed
    monkeypatch.setattr(
        "backend.routes.system.settings_routes.update._standalone_download_core_sync",
        lambda bin_dir, tag, force: (True, tag or "v0.0.15", f"Sentinel-Core {tag} успешно установлен."),
    )
    
    resp = client.post("/api/system/settings/update/core/apply", json={"version": "v0.0.15", "force": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["version"] == "v0.0.15"
    assert "успешно" in data["msg"]

def test_detect_installed_core_version():
    bin_dir = _get_bin_dir()
    is_inst, ver = _detect_installed_core_version(bin_dir)
    assert isinstance(is_inst, bool)
    assert isinstance(ver, str)
