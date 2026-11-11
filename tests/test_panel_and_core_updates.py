import os
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


def test_semver_sort_and_prerelease_detection():
    from backend.routes.system.settings_routes import update as update_routes

    assert update_routes._is_prerelease_tag("v0.0.26") is False
    assert update_routes._is_prerelease_tag("v0.0.26-beta") is True
    assert update_routes._is_prerelease_tag("0.0.26-rc.1") is True
    assert update_routes._is_prerelease_tag("v0.0.26", prerelease_flag=True) is True

    assert update_routes._is_newer_version("v0.0.26", "v0.0.26-beta") is True
    assert update_routes._is_newer_version("v0.0.26-beta.2", "v0.0.26-beta.1") is True
    assert update_routes._is_newer_version("v0.0.26-beta", "v0.0.25") is True
    assert update_routes._is_newer_version("v0.0.25", "v0.0.26-beta") is False
    assert update_routes._is_newer_version("v0.0.26-beta", "v0.0.26-beta") is False
    assert update_routes._is_newer_version("v0.0.26-beta", "v0.0.26") is False


def test_update_channel_endpoint_and_filtering(client, monkeypatch):
    from backend.routes.system.settings_routes import update as update_routes

    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    store = {"update_channel": "stable"}
    monkeypatch.setattr(
        "backend.database.crud.settings.get_setting",
        lambda key, default="": store.get(key, default),
    )
    monkeypatch.setattr(
        "backend.database.crud.settings.set_setting",
        lambda key, value: store.__setitem__(key, value),
    )

    update_routes._invalidate_update_caches()

    # Default channel is stable
    r_get = client.get("/api/system/settings/update/channel")
    assert r_get.status_code == 200
    assert r_get.json()["channel"] == "stable"

    # Reject unknown channel
    r_bad = client.post("/api/system/settings/update/channel", json={"channel": "nightly"})
    assert r_bad.status_code == 400

    # Mock releases for both panel and core (v0.0.26-beta prerelease + v0.0.25 stable)
    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fake_requests_get(url, **kwargs):
        if "sentinel-panel/releases/latest" in url:
            return FakeResp(200, {"tag_name": "v0.0.25", "prerelease": False, "body": "Stable panel"})
        if "sentinel-panel/releases" in url:
            return FakeResp(200, [
                {"tag_name": "v0.0.26-beta", "prerelease": True, "body": "Beta panel"},
                {"tag_name": "v0.0.25", "prerelease": False, "body": "Stable panel"},
            ])
        if "sentinel-core/releases" in url:
            return FakeResp(200, [
                {"tag_name": "v0.0.26-beta", "name": "Beta Core", "prerelease": True, "published_at": "2026-11-11T00:00:00Z", "body": "Beta core"},
                {"tag_name": "v0.0.25", "name": "Stable Core", "prerelease": False, "published_at": "2026-11-10T00:00:00Z", "body": "Stable core"},
            ])
        return FakeResp(404, {})

    monkeypatch.setattr("requests.get", fake_requests_get)
    monkeypatch.setattr(update_routes, "PANEL_VERSION", "0.0.25")
    monkeypatch.setattr(update_routes, "_detect_installed_core_version", lambda bin_dir: (True, "v0.0.25"))
    monkeypatch.setattr(update_routes, "_get_loaded_core_version_safe", lambda: "0.0.25")

    # Under stable channel, neither panel nor core advertises beta v0.0.26-beta
    panel_stable = client.get("/api/system/settings/update/check?force=true").json()
    assert panel_stable["channel"] == "stable"
    assert panel_stable["has_update"] is False
    assert panel_stable["latest_version"] == "0.0.25"

    core_stable = client.get("/api/system/settings/update/core/check?force=true").json()
    assert core_stable["channel"] == "stable"
    assert core_stable["has_update"] is False
    assert core_stable["latest_version"] == "v0.0.25"
    assert [r["tag"] for r in core_stable["releases"]] == ["v0.0.25"]

    # Switch to beta channel -> advertises v0.0.26-beta for both
    r_set = client.post("/api/system/settings/update/channel", json={"channel": "beta"})
    assert r_set.status_code == 200
    assert r_set.json()["channel"] == "beta"
    assert store["update_channel"] == "beta"

    panel_beta = client.get("/api/system/settings/update/check").json()
    assert panel_beta["channel"] == "beta"
    assert panel_beta["has_update"] is True
    assert panel_beta["latest_version"] == "0.0.26-beta"
    assert panel_beta["is_prerelease"] is True

    core_beta = client.get("/api/system/settings/update/core/check").json()
    assert core_beta["channel"] == "beta"
    assert core_beta["has_update"] is True
    assert core_beta["latest_version"] == "v0.0.26-beta"
    assert core_beta["latest_is_prerelease"] is True
    assert [r["tag"] for r in core_beta["releases"]] == ["v0.0.26-beta", "v0.0.25"]

    # Switching back to stable when disk already has v0.0.26-beta must NOT prompt downgrade
    client.post("/api/system/settings/update/channel", json={"channel": "stable"})
    monkeypatch.setattr(update_routes, "_detect_installed_core_version", lambda bin_dir: (True, "v0.0.26-beta"))
    monkeypatch.setattr(update_routes, "_get_loaded_core_version_safe", lambda: "0.0.26-beta")
    core_after_beta = client.get("/api/system/settings/update/core/check?force=true").json()
    assert core_after_beta["has_update"] is False
    assert core_after_beta["restart_required"] is False


def test_core_restart_required_detection_and_restart_endpoint(client, monkeypatch):
    from backend.routes.system.settings_routes import update as update_routes

    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    update_routes._invalidate_update_caches()

    class FakeResp:
        status_code = 200

        def json(self):
            return [{"tag_name": "v0.0.25", "name": "v0.0.25", "prerelease": False, "published_at": "", "body": ""}]

    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp())
    monkeypatch.setattr("backend.database.crud.settings.get_setting", lambda k, d="": "stable")
    monkeypatch.setattr(update_routes, "_detect_installed_core_version", lambda bin_dir: (True, "v0.0.26-beta"))

    # RAM loaded older version vs newer disk version -> restart_required True
    monkeypatch.setattr(update_routes, "_get_loaded_core_version_safe", lambda: "0.0.25")
    resp = client.get("/api/system/settings/update/core/check?force=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["loaded_version"] == "0.0.25"
    assert data["restart_required"] is True

    # No library loaded in RAM yet -> restart_required False
    monkeypatch.setattr(update_routes, "_get_loaded_core_version_safe", lambda: None)
    resp_none = client.get("/api/system/settings/update/core/check")
    assert resp_none.json()["restart_required"] is False

    # Manual restart endpoint delegates cleanly to runtime.schedule_panel_restart
    calls = []
    monkeypatch.setattr("backend.runtime.schedule_panel_restart", lambda delay_seconds=1.0, reason="": calls.append((delay_seconds, reason)) or True)
    r_restart = client.post("/api/system/settings/panel/restart")
    assert r_restart.status_code == 200
    assert r_restart.json()["restarting"] is True
    assert len(calls) == 1


def test_core_apply_respects_channel_triggers_restart_and_stale_hostagent_fallback(client, monkeypatch):
    from backend.routes.system.settings_routes import update as update_routes
    from updater.core.sentinel_core import SentinelCoreManager

    monkeypatch.setattr("backend.routes.system.settings_routes.update.check_auth", lambda req: True)
    store = {"update_channel": "stable"}
    monkeypatch.setattr("backend.database.crud.settings.get_setting", lambda k, d="": store.get(k, d))

    downloaded_tags = []
    monkeypatch.setattr(SentinelCoreManager, "fetch_releases", lambda self: ("v0.0.25", "v0.0.26-beta", "v0.0.26-beta"))
    monkeypatch.setattr(SentinelCoreManager, "download_core", lambda self, tag: downloaded_tags.append(tag) or True)
    monkeypatch.setattr(SentinelCoreManager, "get_installed_version", lambda self: (True, downloaded_tags[-1]))

    restart_calls = []
    monkeypatch.setattr("backend.runtime.schedule_panel_restart", lambda delay_seconds=1.2, reason="": restart_calls.append(reason) or True)
    monkeypatch.setattr(update_routes, "_get_loaded_core_version_safe", lambda: "0.0.24")

    # Empty version on stable channel selects v0.0.25 and schedules panel restart
    r1 = client.post("/api/system/settings/update/core/apply", json={"version": "", "force": False})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["success"] is True
    assert downloaded_tags[-1] == "v0.0.25"
    assert d1["restarting"] is True
    assert d1["restart_required"] is True
    assert len(restart_calls) == 1

    # Simulate stale HostAgent reporting success while disk still has v0.0.25 when v0.0.26-beta requested
    host_agent_calls = []
    monkeypatch.setattr(
        update_routes,
        "_query_host_agent",
        lambda payload, timeout=3.0: (host_agent_calls.append(payload) or {"success": True, "version": "v0.0.25", "msg": "old agent"}),
    )
    monkeypatch.setattr(update_routes, "_detect_installed_core_version", lambda bin_dir: (True, "v0.0.25"))

    r2 = client.post("/api/system/settings/update/core/apply", json={"version": "v0.0.26-beta", "force": True, "channel": "beta"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["success"] is True
    assert len(host_agent_calls) == 1
    assert host_agent_calls[0]["channel"] == "beta"
    assert downloaded_tags[-1] == "v0.0.26-beta"


def test_atomic_staging_and_sha256_verification(tmp_path, monkeypatch):
    import hashlib
    import platform as _plat
    from updater.core.sentinel_core import SentinelCoreManager
    from backend.routes.system.settings_routes import update as update_routes

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    system = _plat.system().lower()
    machine = _plat.machine().lower()
    os_name = "windows" if "windows" in system else ("darwin" if "darwin" in system else "linux")
    arch = "arm64" if ("arm64" in machine or "aarch64" in machine) else ("armv7" if "arm" in machine else "amd64")
    lib_ext = ".dll" if os_name == "windows" else (".dylib" if os_name == "darwin" else ".so")
    exe_ext = ".exe" if os_name == "windows" else ""

    target_lib = bin_dir / f"libsentinel-core{lib_ext}"
    target_lib.write_bytes(b"ORIGINAL_WORKING_CORE")

    lib_asset = f"libsentinel-core-{os_name}-{arch}{lib_ext}"
    cli_asset = f"sentinel-core-{os_name}-{arch}{exe_ext}"
    new_lib_bytes = b"NEW_CORE_V0_0_26_BETA_BINARY"
    new_cli_bytes = b"NEW_CLI_BINARY"
    good_sha = hashlib.sha256(new_lib_bytes).hexdigest()
    cli_sha = hashlib.sha256(new_cli_bytes).hexdigest()

    mgr = SentinelCoreManager(bin_dir=str(bin_dir), auto_mode=True, force=True)

    # 1. Mismatched checksum via SentinelCoreManager must fail and NOT touch ORIGINAL_WORKING_CORE
    def fake_dl_bad(asset_url, dest_path, **kw):
        with open(dest_path, "wb") as f:
            f.write(b"CORRUPTED_BYTES" if lib_asset in asset_url else new_cli_bytes)
        return True

    monkeypatch.setattr(mgr.downloader, "download_file_with_mirrors", fake_dl_bad)
    monkeypatch.setattr(
        mgr,
        "_fetch_release_metadata",
        lambda tag: (
            {lib_asset: good_sha, cli_asset: cli_sha},
            {lib_asset: len(new_lib_bytes), cli_asset: len(new_cli_bytes)},
        ),
    )

    assert mgr.download_core("v0.0.26-beta") is False
    assert target_lib.read_bytes() == b"ORIGINAL_WORKING_CORE"

    # 2. Matching checksum via SentinelCoreManager atomically swaps target_lib and refreshes alias
    def fake_dl_good(asset_url, dest_path, **kw):
        with open(dest_path, "wb") as f:
            f.write(new_lib_bytes if lib_asset in asset_url else new_cli_bytes)
        return True

    monkeypatch.setattr(mgr.downloader, "download_file_with_mirrors", fake_dl_good)
    assert mgr.download_core("v0.0.26-beta") is True
    assert target_lib.read_bytes() == new_lib_bytes
    assert (bin_dir / f"sentinel-core{lib_ext}").exists()
    assert (bin_dir / f"sentinel-core{exe_ext}").read_bytes() == new_cli_bytes

    # 3. Standalone downloader staging & checksum verification also preserves existing lib on mismatch
    target_lib.write_bytes(b"PREVIOUS_LIB")
    monkeypatch.setattr(update_routes.platform, "system", lambda: "Windows" if os_name == "windows" else "Linux")

    class FakeStreamResp:
        def __init__(self, status_code, payload_bytes=b"", text_val=""):
            self.status_code = status_code
            self._payload = payload_bytes
            self.text = text_val
            self.headers = {"Content-Length": str(len(payload_bytes))} if payload_bytes else {}

        def iter_content(self, chunk_size=65536):
            for i in range(0, len(self._payload), chunk_size):
                yield self._payload[i:i + chunk_size]

    corrupt_mode = {"bad": True}

    def fake_requests_get(url, **kwargs):
        if url.endswith(lib_asset):
            return FakeStreamResp(200, b"BAD_LIB" if corrupt_mode["bad"] else new_lib_bytes)
        if url.endswith("checksums.txt"):
            return FakeStreamResp(200, text_val=f"{good_sha}  {lib_asset}\n{cli_sha}  {cli_asset}\n")
        if url.endswith(cli_asset):
            return FakeStreamResp(200, new_cli_bytes)
        return FakeStreamResp(404)

    monkeypatch.setattr("requests.get", fake_requests_get)
    monkeypatch.setattr(update_routes, "_detect_installed_core_version", lambda bd: (True, "v0.0.26-beta"))

    ok_bad, _, msg_bad = update_routes._standalone_download_core_sync(str(bin_dir), "v0.0.26-beta", force=True, channel="beta")
    assert ok_bad is False
    assert "SHA-256" in msg_bad
    assert target_lib.read_bytes() == b"PREVIOUS_LIB"

    corrupt_mode["bad"] = False
    ok_good, ver_good, _ = update_routes._standalone_download_core_sync(str(bin_dir), "v0.0.26-beta", force=True, channel="beta")
    assert ok_good is True
    assert ver_good == "v0.0.26-beta"
    assert target_lib.read_bytes() == new_lib_bytes


def test_runtime_restart_skips_under_pytest_and_ffi_tracks_loaded_version(monkeypatch):
    import sys as _sys
    from backend import runtime as rt
    from backend.sentinel_core_bridge import ffi

    # Never terminates pytest
    assert rt.schedule_panel_restart(delay_seconds=0.1, reason="test") is False

    monkeypatch.setattr(_sys, "orig_argv", ["python3", "-m", "backend.main", "--port", "8443"], raising=False)
    assert rt.build_exec_argv() == [_sys.executable, "-m", "backend.main", "--port", "8443"]

    class DummyCFunc:
        def __call__(self):
            return b"0.0.26-beta"

    class DummyLib:
        SentinelGetEngineVersion = DummyCFunc()

    prev_lib = ffi._SENTINEL_LIB
    prev_tried = ffi._SENTINEL_LIB_TRIED
    prev_ver = ffi._SENTINEL_LOADED_VERSION
    prev_path = ffi._SENTINEL_LIB_PATH
    try:
        ffi.set_sentinel_lib(DummyLib(), lib_path="/opt/sentinel-panel/bin/libsentinel-core.so")
        assert ffi.get_loaded_core_version() == "v0.0.26-beta"
        assert ffi.get_loaded_core_path() == "/opt/sentinel-panel/bin/libsentinel-core.so"
    finally:
        ffi._SENTINEL_LIB = prev_lib
        ffi._SENTINEL_LIB_TRIED = prev_tried
        ffi._SENTINEL_LOADED_VERSION = prev_ver
        ffi._SENTINEL_LIB_PATH = prev_path


def test_git_manager_forces_fetch_and_ignores_filemode(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import updater.core.git as git_mod

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_mod.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)

    recorded_cmds = []
    rev_parse_calls = {"head": 0}

    def fake_run_command(cmd, cwd=None, env=None, capture=False, check=False, timeout=None):
        recorded_cmds.append(list(cmd))
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout=" M update.sh\n", stderr="")
        if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            rev_parse_calls["head"] += 1
            sha = "1111111\n" if rev_parse_calls["head"] == 1 else "2222222\n"
            return SimpleNamespace(returncode=0, stdout=sha, stderr="")
        if "fetch" in cmd:
            if "--tags" in cmd:
                return SimpleNamespace(returncode=1, stdout="", stderr=" ! [rejected] v0.0.1 -> v0.0.1 (would clobber existing tag)")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:4] == ["git", "-c", "safe.directory=*", "describe"]:
            return SimpleNamespace(returncode=0, stdout="v0.0.27\n", stderr="")
        if cmd[:3] == ["git", "stash", "pop"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="CONFLICT (content): Merge conflict in update.sh")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(git_mod, "run_command", fake_run_command)

    mgr = git_mod.GitManager(str(tmp_path))
    assert git_mod.OFFICIAL_REPO_URL in mgr._get_candidate_remotes()

    ok = mgr.update_codebase(silent_if_uptodate=True)
    assert ok is True
    assert ["git", "config", "core.filemode", "false"] in recorded_cmds
    assert any("--tags" in c and "--force" in c for c in recorded_cmds if "fetch" in c)
    assert any("fetch" in c and "--force" in c and "--tags" not in c for c in recorded_cmds)
    assert ["git", "reset", "--hard", "FETCH_HEAD"] in recorded_cmds
    assert ["git", "reset", "--hard", "HEAD"] in recorded_cmds
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == "0.0.27"
