import pytest
import time
import json
import httpx
import subprocess
from fastapi.testclient import TestClient

pytestmark = pytest.mark.xdist_group("core_ops")

from backend.database import db_session, get_session_db, add_session_db, delete_session_db
from backend.models import Inbound, SharedCache, UserSession, ClientStats
from backend.database.crud.shared_cache import (
    get_shared_cache,
    set_shared_cache,
    delete_shared_cache,
    clean_expired_shared_cache
)
from backend.auth_utils import ACTIVE_SESSIONS, CSRF_TOKENS
from backend.routes.auth_routes.login import LOGIN_ATTEMPTS, check_rate_limit, record_attempt
from backend.xray.service import start_xray, stop_xray, is_xray_running
from backend.hysteria.service import start_hysteria, stop_hysteria, is_hysteria_running

def test_shared_cache_crud():
    # Test setting and getting
    set_shared_cache("test_key", "test_val", 60)
    assert get_shared_cache("test_key") == "test_val"
    
    # Test overwriting
    set_shared_cache("test_key", "new_val", 60)
    assert get_shared_cache("test_key") == "new_val"
    
    # Test deleting
    delete_shared_cache("test_key")
    assert get_shared_cache("test_key") is None

def test_shared_cache_expiration():
    # Set with negative duration (expired)
    set_shared_cache("expired_key", "expired_val", -10)
    assert get_shared_cache("expired_key") is None
    
    # Clean up expired
    set_shared_cache("expired_key_2", "val", -10)
    set_shared_cache("valid_key", "val", 60)
    clean_expired_shared_cache()
    
    # expired should be gone, valid should remain
    assert get_shared_cache("expired_key_2") is None
    assert get_shared_cache("valid_key") == "val"
    delete_shared_cache("valid_key")

def test_db_csrf_tokens():
    # Clear existing
    CSRF_TOKENS.clear()
    
    # Setter / Getter
    CSRF_TOKENS["session123"] = "token_xyz"
    assert CSRF_TOKENS["session123"] == "token_xyz"
    assert CSRF_TOKENS.get("session123") == "token_xyz"
    assert "session123" in CSRF_TOKENS
    
    # Discard
    CSRF_TOKENS.discard("session123")
    assert "session123" not in CSRF_TOKENS
    assert CSRF_TOKENS.get("session123") is None
    
    # Pop
    CSRF_TOKENS["session456"] = "token_abc"
    val = CSRF_TOKENS.pop("session456")
    assert val == "token_abc"
    assert "session456" not in CSRF_TOKENS

def test_db_active_sessions():
    ACTIVE_SESSIONS.clear()
    
    # Session doesn't exist initially
    assert "sess_test" not in ACTIVE_SESSIONS
    
    # Add session to DB
    add_session_db("sess_test", "test_user", 1)
    
    # Now it should be in ACTIVE_SESSIONS
    assert "sess_test" in ACTIVE_SESSIONS
    
    # Discard (deletes from DB)
    ACTIVE_SESSIONS.discard("sess_test")
    assert "sess_test" not in ACTIVE_SESSIONS
    assert get_session_db("sess_test") is None

def test_rate_limiting_shared_cache():
    LOGIN_ATTEMPTS.clear()
    
    ip = "192.168.1.99"
    # Should be allowed
    assert check_rate_limit(ip) is True
    
    # Record 5 attempts
    for _ in range(5):
        record_attempt(ip)
        
    # Now it should be blocked
    assert check_rate_limit(ip) is False
    
    # Clear and verify it is allowed again
    LOGIN_ATTEMPTS.clear()
    assert check_rate_limit(ip) is True

from tests.core_verifier import get_xray_bin, get_hysteria_bin

_skip_no_xray     = pytest.mark.skipif(get_xray_bin() is None,     reason="xray binary not found")
_skip_no_hysteria = pytest.mark.skipif(get_hysteria_bin() is None, reason="hysteria binary not found")


@_skip_no_xray
@pytest.mark.xdist_group("core_ops")
def test_dynamic_xray_start():
    """Real xray binary: start/stop behaviour driven by DB state."""
    # 1. No xray inbounds — xray should stay stopped
    with db_session() as session:
        session.query(Inbound).delete()
        session.commit()

    import backend.utils.service_restart as s_rst
    if s_rst._pending_timer:
        s_rst._pending_timer.cancel()
        s_rst._pending_timer = None

    stop_xray()
    time.sleep(0.3)

    res = start_xray()
    assert res is True
    assert is_xray_running() is False

    # 2. Add a valid VLESS inbound + client — xray should start
    from tests.core_verifier import get_free_port
    x_port = get_free_port()
    with db_session() as session:
        ib = Inbound(
            remark="Xray Test Inbound",
            port=x_port,
            protocol="vless",
            # Minimal settings required by real xray: decryption must be "none"
            settings=json.dumps({"clients": [], "decryption": "none"}),
            stream_settings=json.dumps({"network": "tcp"}),
            sniffing="{}",
            enable=1,
        )
        session.add(ib)
        session.commit()
        session.refresh(ib)

        cs = ClientStats(
            inbound_id=ib.id,
            email="dynamic_xray_client",
            client_uuid_or_pwd="d6d0e37a-f497-4813-8d5c-9e3efa5d7c7d",
            enable=1,
        )
        session.add(cs)
        session.commit()

        stop_xray()
        time.sleep(0.5)
        res = start_xray()
        assert res is True
        assert is_xray_running() is True
        stop_xray()
        for _ in range(10):
            if not is_xray_running():
                break
            time.sleep(0.2)
        assert is_xray_running() is False


@_skip_no_xray
@pytest.mark.xdist_group("core_ops")
def test_dynamic_xray_start_via_hysteria_routing():
    """Real xray binary: starts when a Hysteria 2 inbound routes via xray."""
    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        hys_stream = {"hysteria": {"routingViaXray": True}}
        from tests.core_verifier import get_free_port
        xray_hys_port = get_free_port()
        ib = Inbound(
            remark="Hys Inbound routing via Xray",
            port=xray_hys_port,
            protocol="hysteria2",
            settings="{}",
            stream_settings=json.dumps(hys_stream),
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.commit()
        session.refresh(ib)

        cs = ClientStats(
            inbound_id=ib.id,
            email="hys_xray_client",
            client_uuid_or_pwd="testpassword123",
            enable=1
        )
        session.add(cs)
        session.commit()

    stop_xray()
    time.sleep(0.3)
    res = start_xray()
    assert res is True
    assert is_xray_running() is True
    stop_xray()
    assert is_xray_running() is False

@_skip_no_hysteria
@pytest.mark.xdist_group("core_ops")
def test_dynamic_hysteria_start():
    """Real hysteria binary: start/stop behaviour driven by DB state."""
    # 1. No active hysteria inbounds
    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.commit()

    stop_hysteria()
    time.sleep(0.2)
    res = start_hysteria()
    assert res is True
    assert is_hysteria_running() is False

    # 2. Add active hysteria inbound
    from tests.core_verifier import get_free_port
    hys_port = get_free_port()
    with db_session() as session:
        ib = Inbound(
            remark="Hys Inbound",
            port=hys_port,
            protocol="hysteria2",
            settings="{}",
            stream_settings=json.dumps({"hysteria": {"ignoreClientBandwidth": True}}),
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.flush()
        c = ClientStats(
            inbound_id=ib.id,
            email="hys_user@mail.com",
            client_uuid_or_pwd="pass123",
            enable=1
        )
        session.add(c)
        session.commit()
        from backend.hysteria import generate_self_signed_cert
        generate_self_signed_cert()

    res = start_hysteria()
    assert res is True
    assert is_hysteria_running() is True
    stop_hysteria()
    assert is_hysteria_running() is False


def test_decoy_verify_ssl_false(monkeypatch):
    verify_val = None
    
    original_init = httpx.AsyncClient.__init__
    def mock_init(self, *args, **kwargs):
        nonlocal verify_val
        verify_val = kwargs.get("verify", None)
        kwargs["transport"] = httpx.MockTransport(lambda req: httpx.Response(200, content=b"decoy content", headers={"content-type": "text/html"}))
        original_init(self, *args, **kwargs)
        
    monkeypatch.setattr("httpx.AsyncClient.__init__", mock_init)
    
    # Trigger proxy_decoy_request through handle_decoy_route
    from backend.auth_utils import handle_decoy_route
    from fastapi import Request
    
    # Mock get_setting for proxy decoy
    def mock_get_setting(key, default=""):
        if key == "decoy_type":
            return "proxy"
        if key == "decoy_value":
            return "https://decoy.site"
        return default
        
    monkeypatch.setattr("backend.auth_utils.get_setting", mock_get_setting)
    monkeypatch.setattr("backend.auth.decoy.get_setting", mock_get_setting)
    monkeypatch.setattr("socket.getaddrinfo", lambda host, port: [(2, 1, 6, '', ('93.184.215.14', 0))])
    
    # Build a mock request
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "query_string": b""
    }
    
    # Mock receive channel
    async def mock_receive():
        return {"type": "http.request", "body": b"", "more_body": False}
        
    req = Request(scope, receive=mock_receive)
    
    import anyio
    async def run():
        return await handle_decoy_route(req, "some-path")
        
    res = anyio.run(run)
    assert res.status_code == 200
    assert res.body == b"decoy content"
    assert verify_val is False

def test_status_endpoint_reads_from_cache(client, monkeypatch):
    # Set cached stats
    from backend.host_client import _cached_stats
    _cached_stats["cpu"] = 99.9
    _cached_stats["mem"]["current"] = 12345
    _cached_stats["mem"]["total"] = 54321
    _cached_stats["disk"] = {"current": 111, "total": 999, "percent": 11.1}
    
    monkeypatch.setattr("backend.host_client.host_client.send_command", lambda *args, **kwargs: {"success": False})
    
    # Request status
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.get("/panel/api/server/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["obj"]["cpu"] == 99.9
    assert data["obj"]["mem"]["current"] == 12345
    assert data["obj"]["mem"]["total"] == 54321
    assert data["obj"]["disk"]["current"] == 111
    assert data["obj"]["disk"]["total"] == 999
    assert data["obj"]["disk"]["percent"] == 11.1


def test_decoy_proxy_ssrf_block(monkeypatch):
    """
    Проверяет, что при попытке указать loopback или приватный IP в качестве proxy decoy,
    система блокирует запрос (возвращает 404).
    """
    from backend.auth_utils import handle_decoy_route
    from fastapi import Request
    
    # Mock get_setting to return a loopback url
    def mock_get_setting(key, default=""):
        if key == "decoy_type":
            return "proxy"
        if key == "decoy_value":
            return "http://127.0.0.1:8080"
        return default
        
    monkeypatch.setattr("backend.auth_utils.get_setting", mock_get_setting)
    
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "query_string": b""
    }
    
    async def mock_receive():
        return {"type": "http.request", "body": b"", "more_body": False}
        
    req = Request(scope, receive=mock_receive)
    
    import anyio
    async def run():
        return await handle_decoy_route(req, "some-path")
        
    res = anyio.run(run)
    # Должен сработать блок SSRF и вернуться стандартная 404 заглушка HTML
    assert res.status_code == 404
    assert b"404 Not Found" in res.body
