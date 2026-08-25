import time
import pytest
from backend.database import db_session
from backend.models import Inbound, ClientStats
from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE, sync_active_ips_from_core
from backend.routes.clients.actions import update_online_emails

def test_singbox_exhaustive_all_protocols_online_status(monkeypatch):
    """
    Exhaustively tests online status tracking for protocols supported by Sing-box.
    """
    with db_session() as session:
        ib = Inbound(remark="Singbox Full IB", port=31001, protocol="vless", core="singbox", enable=1)
        session.add(ib)
        session.commit()
        ib_id = ib.id

        protocols = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2", "tuic", "wireguard"]
        for p in protocols:
            c = ClientStats(inbound_id=ib_id, email=f"sb_{p}_user@test.com", client_uuid_or_pwd=f"pwd_{p}", enable=1)
            session.add(c)
        session.commit()

    # Mock sentinel-core returning active sessions
    mock_sessions = [
        {"core": "sing-box", "email": f"sb_{p}_user@test.com", "ip": f"198.51.100.{i+1}", "last_seen_at": time.time()}
        for i, p in enumerate(protocols)
    ]
    monkeypatch.setattr("backend.sentinel_core_bridge.get_active_sessions", lambda: mock_sessions)
    monkeypatch.setattr("backend.sentinel_core_bridge.get_online_emails_core", lambda: [s["email"] for s in mock_sessions])

    sync_active_ips_from_core()
    for i, p in enumerate(protocols):
        email = f"sb_{p}_user@test.com"
        assert email in ACTIVE_IP_CACHE
        assert f"198.51.100.{i+1}" in ACTIVE_IP_CACHE[email]

    onlines = update_online_emails()
    for p in protocols:
        assert f"sb_{p}_user@test.com" in onlines


def test_xray_exhaustive_all_protocols_online_status(monkeypatch):
    """
    Exhaustively tests online status tracking for protocols supported by Xray.
    """
    with db_session() as session:
        ib = Inbound(remark="Xray Full IB", port=31002, protocol="vless", core="xray", enable=1)
        session.add(ib)
        session.commit()
        ib_id = ib.id

        protocols = ["vless", "vmess", "trojan", "shadowsocks", "socks"]
        for p in protocols:
            c = ClientStats(inbound_id=ib_id, email=f"xr_{p}_user@test.com", client_uuid_or_pwd=f"pwd_{p}", enable=1)
            session.add(c)
        session.commit()

    mock_sessions = [
        {"core": "xray", "email": f"xr_{p}_user@test.com", "ip": f"203.0.113.{i*10+10}", "last_seen_at": time.time()}
        for i, p in enumerate(protocols)
    ]
    monkeypatch.setattr("backend.sentinel_core_bridge.get_active_sessions", lambda: mock_sessions)
    monkeypatch.setattr("backend.sentinel_core_bridge.get_online_emails_core", lambda: [s["email"] for s in mock_sessions])

    sync_active_ips_from_core()
    onlines = update_online_emails()
    for p in protocols:
        assert f"xr_{p}_user@test.com" in onlines


def test_hysteria_auth_endpoint_populates_active_ip_cache_for_unlimited_clients():
    """
    Verifies that authenticating via /api/hysteria/auth immediately registers client as online
    in ACTIVE_IP_CACHE even when limit_ip == 0 (unlimited).
    """
    import asyncio
    from backend.routes.hysteria_routes.auth import hysteria_client_auth
    from starlette.requests import Request

    email = "unlimited_hy2_user@test.com"
    with db_session() as session:
        ib = Inbound(remark="Hysteria Unlim IB", port=31004, protocol="hysteria2", core="hysteria", enable=1)
        session.add(ib)
        session.commit()

        c = ClientStats(inbound_id=ib.id, email=email, client_uuid_or_pwd="pwd_unlimited", enable=1, limit_ip=0)
        session.add(c)
        session.commit()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/hysteria/auth",
        "headers": [],
        "client": ("127.0.0.1", 54321),
    }
    request = Request(scope)
    payload = {
        "auth": f"{email}:pwd_unlimited",
        "addr": "198.51.100.99:43210"
    }

    res = asyncio.run(hysteria_client_auth(request, payload))
    assert res.get("ok") is True
    assert res.get("id") == email
    assert email in ACTIVE_IP_CACHE
    assert "198.51.100.99" in ACTIVE_IP_CACHE[email]

    onlines = update_online_emails()
    assert email in onlines


def test_end_to_end_multiclient_multicore_online_status(monkeypatch):
    """
    Creates multiple clients across Sing-box, Xray, and Hysteria 2,
    simulates core session tracker output, and verifies
    that all clients are accurately marked as online in update_online_emails.
    """
    singbox_clients = ["phone", "laptop_singbox", "tablet_singbox"]
    xray_clients = ["user_xray_vless", "user_xray_vmess", "user_xray_trojan"]
    hy2_clients = ["user_hy2_fast", "user_hy2_mobile"]

    with db_session() as session:
        # Inbound 1: Sing-box VLESS
        ib_sb = Inbound(remark="Singbox VLESS", port=32001, protocol="vless", core="singbox", enable=1)
        session.add(ib_sb)
        session.commit()
        for u in singbox_clients:
            session.add(ClientStats(inbound_id=ib_sb.id, email=u, client_uuid_or_pwd=f"pwd_{u}", enable=1))

        # Inbound 2: Xray VMess
        ib_xr = Inbound(remark="Xray VMess", port=32002, protocol="vmess", core="xray", enable=1)
        session.add(ib_xr)
        session.commit()
        for u in xray_clients:
            session.add(ClientStats(inbound_id=ib_xr.id, email=u, client_uuid_or_pwd=f"pwd_{u}", enable=1))

        # Inbound 3: Hysteria 2
        ib_hy = Inbound(remark="Hysteria 2", port=32003, protocol="hysteria2", core="hysteria", enable=1)
        session.add(ib_hy)
        session.commit()
        for u in hy2_clients:
            session.add(ClientStats(inbound_id=ib_hy.id, email=u, client_uuid_or_pwd=f"pwd_{u}", enable=1))
        session.commit()

    all_users = singbox_clients + xray_clients + hy2_clients
    mock_sessions = [
        {"core": "sing-box" if u in singbox_clients else "xray" if u in xray_clients else "hysteria2",
         "email": u, "ip": f"198.51.100.{i+1}", "last_seen_at": time.time()}
        for i, u in enumerate(all_users)
    ]
    monkeypatch.setattr("backend.sentinel_core_bridge.get_active_sessions", lambda: mock_sessions)
    monkeypatch.setattr("backend.sentinel_core_bridge.get_online_emails_core", lambda: [s["email"] for s in mock_sessions])

    sync_active_ips_from_core()
    onlines = update_online_emails()

    for u in singbox_clients:
        assert u in onlines, f"Expected '{u}' to be online, got: {onlines}"
    for u in xray_clients:
        assert u in onlines, f"Expected '{u}' to be online, got: {onlines}"
    for u in hy2_clients:
        assert u in onlines, f"Expected '{u}' to be online, got: {onlines}"
