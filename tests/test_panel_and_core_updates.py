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

def test_core_update_progress_endpoint(client, monkeypatch):
    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    resp = client.get("/api/system/settings/update/core/progress")
    assert resp.status_code == 200
    data = resp.json()
    assert "active" in data
    assert "percent" in data
    assert "stage" in data
    assert "downloaded_bytes" in data
    assert "total_bytes" in data


def test_docker_manager_cleanup_build_artifacts(monkeypatch):
    from updater.panel.docker import DockerManager
    executed_commands = []

    def mock_run_command(cmd, **kwargs):
        executed_commands.append(cmd)
        return None

    monkeypatch.setattr("updater.panel.docker.run_command", mock_run_command)
    mgr = DockerManager(project_dir="/tmp/test")
    mgr.cleanup_build_artifacts()

    assert any(cmd == ["docker", "image", "prune", "-f"] for cmd in executed_commands)
    assert any("builder" in cmd and "prune" in cmd for cmd in executed_commands)




def test_dynamic_panel_version_resolution(tmp_path, monkeypatch):
    from backend.version import _resolve_panel_version, PANEL_VERSION_FALLBACK

    # 1. Test environment variable priority
    monkeypatch.setenv("PANEL_VERSION", "v2.5.0")
    assert _resolve_panel_version() == "2.5.0"

    # 2. Test VERSION file detection
    monkeypatch.delenv("PANEL_VERSION", raising=False)
    fake_version_file = tmp_path / "VERSION"
    fake_version_file.write_text("3.1.4\n")

    monkeypatch.setattr(
        "backend.version.Path.is_file",
        lambda p: str(p).endswith("VERSION"),
    )
    monkeypatch.setattr(
        "backend.version.Path.read_text",
        lambda p, **kwargs: "3.1.4\n",
    )
    assert _resolve_panel_version() == "3.1.4"
