import pytest
from backend.config import settings
from backend.database import set_setting
from backend.links_generator import get_base_host
from updater.core.common import free_port


def test_hysteria_auth_rejects_static_secret_fallback(client):
    """Verifies that hysteria auth rejects the static 'secret' string and accepts internal_secret."""
    # 1. Non-local request with static "secret" -> 404 decoy
    res = client.post("/api/hysteria/auth?secret=secret", json={"auth": "user:pwd"})
    assert res.status_code == 404

    # 2. Request with generated hysteria_internal_secret -> passes auth check (200 with ok: False since user doesn't exist)
    set_setting("hysteria_internal_secret", "test_internal_secret_998877")
    res = client.post("/api/hysteria/auth?secret=test_internal_secret_998877", json={"auth": "user:pwd"})
    assert res.status_code == 200
    assert res.json() == {"ok": False}


def test_ssl_generation_domain_validation(client):
    """Verifies that SSL certificate generation strictly validates domain and email format."""
    headers = {"Authorization": "Bearer test_bearer_token"}

    # Missing domain
    res = client.post("/api/ssl/generate", json={"domain": "", "email": "admin@example.com"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is False

    # Invalid domain format
    for bad_domain in ["bad_domain", "domain..com", "http://domain.com", "domain.com/path", "domain.com; rm -rf /"]:
        res = client.post("/api/ssl/generate", json={"domain": bad_domain, "email": "admin@example.com"}, headers=headers)
        assert res.status_code == 200
        assert res.json()["success"] is False

    # Invalid email format
    res = client.post("/api/ssl/generate", json={"domain": "example.com", "email": "not-an-email"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is False


def test_get_base_host_input_sanitization():
    """Verifies get_base_host sanitizes hostnames and rejects injection payloads."""
    # Normal domain
    assert get_base_host("https://sub.domain.com:443") == "sub.domain.com"
    # Normal IP
    assert get_base_host("http://198.51.100.1:8080") == "198.51.100.1"

    # Injections / invalid characters fall back to LAN IP or safe string
    assert get_base_host("http://domain.com/evil/path") == "domain.com"
    res_bad = get_base_host("http://domain.com\r\nHost: evil.com")
    # Must not contain newlines or control characters
    assert "\r" not in res_bad and "\n" not in res_bad


def test_updater_free_port_isolation(monkeypatch):
    """Verifies that free_port on panel ports (8000, 8080, 5432) does not kill failover tunnels."""
    killed_cmds = []

    def mock_run(cmd, *args, **kwargs):
        killed_cmds.append(cmd)
        class MockRes:
            returncode = 0
            stdout = b""
            stderr = b""
        return MockRes()

    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("shutil.which", lambda x: "fuser")

    # Free panel port 8000
    free_port(8000)
    # Ensure no pkill _failover_ was executed for port 8000
    failover_kills = [c for c in killed_cmds if "_failover_" in str(c)]
    assert len(failover_kills) == 0

    # Free rotator port 10818
    free_port(10818)
    # Ensure pkill _failover_ WAS executed for port 10818
    failover_kills_10818 = [c for c in killed_cmds if "_failover_" in str(c)]
    assert len(failover_kills_10818) > 0
