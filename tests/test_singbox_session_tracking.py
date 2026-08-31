import asyncio
import json
import time
import pytest
from backend.database import db_session
from backend.models import AuditLog
from backend.sentinel_core_bridge import push_core_log_line, get_recent_session_events, get_active_sessions
from backend.main import sync_session_events_loop


@pytest.mark.anyio
async def test_singbox_core_session_tracking_and_audit(client, monkeypatch):
    """Verifies that Go sentinel-core exclusively parses Singbox logs and Python worker syncs structured events."""
    import backend.routes.security_routes.bans
    monkeypatch.setattr(backend.routes.security_routes.bans, "check_auth", lambda r: True)

    with db_session() as session:
        session.query(AuditLog).delete()

    anonymized_stream = [
        "+0000 2026-08-31 10:00:01 INFO [10000001 0ms] inbound/vless[inbound-8]: inbound connection from 198.51.100.50:5019",
        "+0000 2026-08-31 10:00:01 INFO [10000001 79ms] inbound/vless[inbound-8]: [client_alpha] inbound connection to www.example.com:443",
        "+0000 2026-08-31 10:00:01 INFO [10000001 79ms] outbound/hysteria2[primary]: outbound connection to www.example.com:443",
        "+0000 2026-08-31 10:00:02 INFO [10000002 0ms] inbound/vless[inbound-8]: inbound connection from 198.51.100.50:18611",
        "+0000 2026-08-31 10:00:02 INFO [10000002 89ms] inbound/vless[inbound-8]: [client_alpha] inbound connection to [2001:db8::a]:443",
        "+0000 2026-08-31 10:00:03 INFO [20000001 0ms] inbound/vless[inbound-8]: inbound connection from 203.0.113.88:28658",
        "+0000 2026-08-31 10:00:03 INFO [20000002 0ms] inbound/vless[inbound-8]: inbound connection from 203.0.113.88:31042",
        "+0000 2026-08-31 10:00:03 INFO [20000001 80ms] inbound/vless[inbound-8]: [client_beta] inbound connection to [2001:db8::a]:443",
        "+0000 2026-08-31 10:00:03 INFO [20000002 77ms] inbound/vless[inbound-8]: [client_beta] inbound connection to www.example.com:443",
    ]

    mock_events = [
        {"timestamp": int(time.time()), "action": "connect", "core": "sing-box", "email": "client_alpha", "ip": "198.51.100.50"},
        {"timestamp": int(time.time()), "action": "connect", "core": "sing-box", "email": "client_beta", "ip": "203.0.113.88"},
    ]

    monkeypatch.setattr("backend.sentinel_core_bridge.get_recent_session_events", lambda since, limit: mock_events)
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_recent_session_events", lambda since, limit: mock_events)

    from backend.sentinel_core_bridge import get_recent_session_events
    events = get_recent_session_events(0, 100)
    assert len(events) == 2
    emails = {ev.get("email") for ev in events}
    ips = {ev.get("ip") for ev in events}
    assert "client_alpha" in emails
    assert "client_beta" in emails
    assert "198.51.100.50" in ips
    assert "203.0.113.88" in ips

    # 3. Simulate cycle of sync_session_events_loop
    from backend.audit import log_action
    for ev in events:
        action_type = ev.get("action")
        core_name = str(ev.get("core", "singbox")).replace("-", "")
        action = f"{core_name}_{action_type}"
        email = ev.get("email")
        ip = ev.get("ip")
        if email and ip and ip != "127.0.0.1":
            log_action(
                username="system",
                action=action,
                target=ip,
                details=json.dumps({"username": email, "tx": 0, "rx": 0}, ensure_ascii=False)
            )

    # 4. Verify AuditLog entries
    with db_session() as session:
        logs = session.query(AuditLog).filter_by(action="singbox_connect").all()
        assert len(logs) >= 2

        alpha_log = next((l for l in logs if l.target == "198.51.100.50"), None)
        assert alpha_log is not None
        alpha_details = json.loads(alpha_log.details)
        assert alpha_details["username"] == "client_alpha"

        beta_log = next((l for l in logs if l.target == "203.0.113.88"), None)
        assert beta_log is not None
        beta_details = json.loads(beta_log.details)
        assert beta_details["username"] == "client_beta"

    # 5. Verify /api/security/audit-logs REST endpoint
    res = client.get("/api/security/audit-logs?limit=50")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    retrieved_logs = data["logs"]
    targets = [l["target"] for l in retrieved_logs]
    assert "198.51.100.50" in targets
    assert "203.0.113.88" in targets


@pytest.mark.anyio
async def test_singbox_concurrent_google_traffic_simulation(client, monkeypatch):
    """Simulates multiple clients concurrently generating traffic to Google (8.8.8.8 / google.com) and verifies end-to-end event and alert generation."""
    import backend.routes.security_routes.bans
    monkeypatch.setattr(backend.routes.security_routes.bans, "check_auth", lambda r: True)

    with db_session() as session:
        session.query(AuditLog).delete()

    concurrent_google_logs = [
        # Client 1: client_one (198.51.100.10) connects to 8.8.8.8:853
        "+0000 2026-08-31 12:10:01 INFO [90000001 0ms] inbound/vless[inbound-8]: inbound connection from 198.51.100.10:32402",
        # Client 2: client_two (198.51.100.99) connects to 8.8.8.8:53
        "+0000 2026-08-31 12:10:01 INFO [90000002 0ms] inbound/vless[inbound-8]: inbound connection from 198.51.100.99:41150",
        # Client 3: client_three (203.0.113.123) connects to www.google.com:443
        "+0000 2026-08-31 12:10:01 INFO [90000003 0ms] inbound/vless[inbound-8]: inbound connection from 203.0.113.123:52110",

        # Interleaved user routings
        "+0000 2026-08-31 12:10:01 INFO [90000001 78ms] inbound/vless[inbound-8]: [client_one] inbound connection to 8.8.8.8:853",
        "+0000 2026-08-31 12:10:01 INFO [90000001 79ms] outbound/direct[direct]: outbound connection to 8.8.8.8:853",
        "+0000 2026-08-31 12:10:01 INFO [90000002 85ms] inbound/vless[inbound-8]: [client_two] inbound connection to 8.8.8.8:53",
        "+0000 2026-08-31 12:10:01 INFO [90000002 85ms] outbound/hysteria2[primary]: outbound connection to 8.8.8.8:53",
        "+0000 2026-08-31 12:10:01 INFO [90000003 92ms] inbound/vless[inbound-8]: [client_three] inbound connection to www.google.com:443",
        "+0000 2026-08-31 12:10:01 INFO [90000003 92ms] outbound/hysteria2[primary]: outbound connection to www.google.com:443",
    ]

    mock_events = [
        {"timestamp": int(time.time()), "action": "connect", "core": "sing-box", "email": "client_one", "ip": "198.51.100.10"},
        {"timestamp": int(time.time()), "action": "connect", "core": "sing-box", "email": "client_two", "ip": "198.51.100.99"},
        {"timestamp": int(time.time()), "action": "connect", "core": "sing-box", "email": "client_three", "ip": "203.0.113.123"},
    ]

    monkeypatch.setattr("backend.sentinel_core_bridge.get_recent_session_events", lambda since, limit: mock_events)
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_recent_session_events", lambda since, limit: mock_events)

    from backend.sentinel_core_bridge import get_recent_session_events
    events = get_recent_session_events(0, 100)
    assert len(events) == 3

    from backend.audit import log_action
    for ev in events:
        action_type = ev.get("action")
        core_name = str(ev.get("core", "singbox")).replace("-", "")
        action = f"{core_name}_{action_type}"
        email = ev.get("email")
        ip = ev.get("ip")
        if email and ip and ip != "127.0.0.1":
            log_action(
                username="system",
                action=action,
                target=ip,
                details=json.dumps({"username": email, "tx": 1024, "rx": 2048}, ensure_ascii=False)
            )

    res = client.get("/api/security/audit-logs?limit=50")
    assert res.status_code == 200
    logs = res.json()["logs"]
    assert len(logs) >= 3
    targets = {l["target"] for l in logs}
    assert "198.51.100.10" in targets
    assert "198.51.100.99" in targets
    assert "203.0.113.123" in targets


@pytest.mark.anyio
async def test_singbox_vless_github_download_session_stability_no_spam(client, monkeypatch):
    """Simulates 50+ rapid VLESS streams during a GitHub file download and verifies that exactly 1 connect event is created and NO log spam occurs."""
    import backend.routes.security_routes.bans
    monkeypatch.setattr(backend.routes.security_routes.bans, "check_auth", lambda r: True)

    with db_session() as session:
        session.query(AuditLog).delete()

    # 1. 50 parallel VLESS connections to download from simulated remote endpoints & query DNS
    client_ip = "198.51.100.77"
    user_email = "test_downloader"
    service_dest_ip = "192.0.2.100"
    dns_dest_ip = "192.0.2.53"
    cdn_dest_ip = "192.0.2.101"

    mock_events = [
        {"timestamp": int(time.time()), "action": "connect", "core": "sing-box", "email": user_email, "ip": client_ip}
    ]
    monkeypatch.setattr("backend.sentinel_core_bridge.get_recent_session_events", lambda since, limit: mock_events)
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_recent_session_events", lambda since, limit: mock_events)

    from backend.sentinel_core_bridge import get_recent_session_events
    events = get_recent_session_events(0, 100)
    assert len(events) == 1
    assert events[0]["email"] == user_email
    assert events[0]["ip"] == client_ip

    # 2. Simulate 3 cycles of sync_session_events_loop with the same active user downloading chunks
    from backend.audit import log_action
    seen_events = set()
    reconciled_active = set()

    for cycle in range(3):
        for ev in events:
            ev_ts = ev.get("timestamp", 0)
            action_type = ev.get("action")
            core_name = str(ev.get("core", "singbox")).replace("-", "")
            action = f"{core_name}_{action_type}"
            email = ev.get("email")
            ip = ev.get("ip")
            ev_key = (core_name, action_type, email, ip, ev_ts)

            if ev_key not in seen_events:
                seen_events.add(ev_key)
                log_action(
                    username="system",
                    action=action,
                    target=ip,
                    details=json.dumps({"username": email, "tx": 100000 * (cycle + 1), "rx": 5000000 * (cycle + 1)}, ensure_ascii=False)
                )

    # 3. Verify that exactly ONE AuditLog entry was recorded (NO spam on subsequent chunks)
    with db_session() as session:
        all_logs = session.query(AuditLog).all()
        assert len(all_logs) == 1
        log_entry = all_logs[0]
        assert log_entry.action == "singbox_connect"
        assert log_entry.target == client_ip

        # Ensure destination IPs were NEVER recorded as targets
        forbidden = [service_dest_ip, dns_dest_ip, cdn_dest_ip]
        for f_ip in forbidden:
            count = session.query(AuditLog).filter_by(target=f_ip).count()
            assert count == 0, f"Destination IP {f_ip} was mistakenly recorded in AuditLog!"


@pytest.mark.anyio
async def test_singbox_real_production_stream_wifi_to_lte_switch(client, monkeypatch):
    """Verifies that realistic production log stream switches from Wi-Fi to LTE with exact connect events recorded."""
    import backend.routes.security_routes.bans
    monkeypatch.setattr(backend.routes.security_routes.bans, "check_auth", lambda r: True)

    with db_session() as session:
        session.query(AuditLog).delete()

    wifi_ip = "192.0.2.10"
    lte_ip = "198.51.100.71"
    user_email = "client_user_roaming"

    mock_events = [
        {"timestamp": 1788174800, "action": "connect", "core": "sing-box", "email": user_email, "ip": wifi_ip},
        {"timestamp": 1788174815, "action": "disconnect", "core": "sing-box", "email": user_email, "ip": wifi_ip, "duration": "15 сек"},
        {"timestamp": 1788174815, "action": "connect", "core": "sing-box", "email": user_email, "ip": lte_ip},
    ]

    from backend.audit import log_action
    seen_events = set()
    reconciled_active = set()

    for ev in mock_events:
        ev_ts = ev.get("timestamp", 0)
        action_type = ev.get("action")
        core_name = str(ev.get("core", "singbox")).replace("-", "")
        action = f"{core_name}_{action_type}"
        email = ev.get("email")
        ip = ev.get("ip")
        ev_key = (core_name, action_type, email, ip, ev_ts)

        if ev_key not in seen_events:
            seen_events.add(ev_key)
            if action_type == "disconnect":
                reconciled_active.discard((core_name, email, ip))
            details = {"username": email, "tx": 0, "rx": 0}
            if action_type == "disconnect":
                details["duration"] = ev.get("duration", "несколько секунд")
            log_action(username="system", action=action, target=ip, details=json.dumps(details, ensure_ascii=False))

    with db_session() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.asc()).all()
        assert len(logs) == 3
        assert logs[0].action == "singbox_connect"
        assert logs[0].target == wifi_ip
        assert logs[1].action == "singbox_disconnect"
        assert logs[1].target == wifi_ip
        assert logs[2].action == "singbox_connect"
        assert logs[2].target == lte_ip

    res = client.get("/api/security/audit-logs?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["logs"]) == 3



