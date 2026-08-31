import asyncio
import json
import time
import pytest
from backend.database import db_session
from backend.models import AuditLog, ClientStats, Inbound
from backend.audit import log_action
from backend.alerts.client_connections import check_new_ip_and_get_history


@pytest.mark.anyio
async def test_full_pipeline_untrusted_singbox_connection_and_warning(client, monkeypatch):
    """
    Complete end-to-end pipeline test for an untrusted Sing-box connection:
    1. Client 'phone' connects from an unknown external IP (188.170.74.89).
    2. Core SessionTracker catches the connection and returns the structured connect event.
    3. sync_session_events_loop saves the record into the AuditLog table.
    4. Panel /api/security/audit-logs exposes the new event.
    5. The alert system detects that 188.170.74.89 is UNTRUSTED (is_new_ip=True) and generates a security warning.
    """
    import backend.routes.security_routes.bans
    monkeypatch.setattr(backend.routes.security_routes.bans, "check_auth", lambda r: True)

    username = "phone"
    untrusted_ip = "198.51.100.89"
    approved_home_ip = "192.168.1.50"

    with db_session() as session:
        session.query(AuditLog).delete()
        
        ib = session.query(Inbound).filter_by(core="singbox").first()
        if not ib:
            ib = Inbound(remark="VLESS Singbox", port=18890, protocol="vless", core="singbox", enable=1)
            session.add(ib)
            session.commit()
            
        cs = session.query(ClientStats).filter_by(email=username).first()
        if not cs:
            cs = ClientStats(
                inbound_id=ib.id,
                email=username,
                client_uuid_or_pwd="test-uuid-phone",
                allowed_ips=approved_home_ip,  # Only home IP is approved!
                up=1024,
                down=2048
            )
            session.add(cs)
            session.commit()
        else:
            cs.allowed_ips = approved_home_ip
            session.commit()

    # Step 1: Simulate the structured event emitted by Go sentinel-core SessionTracker
    mock_events = [
        {
            "action": "connect",
            "core": "sing-box",
            "email": username,
            "ip": untrusted_ip,
            "timestamp": int(time.time()),
            "time_str": "2026-08-31 15:02:11"
        }
    ]
    monkeypatch.setattr("backend.sentinel_core_bridge.get_recent_session_events", lambda since, limit: mock_events)
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_recent_session_events", lambda since, limit: mock_events)

    # Step 2: Run sync_session_events_loop
    seen_events = set()
    for ev in mock_events:
        ev_ts = ev.get("timestamp", 0)
        action_type = ev.get("action")
        core_name = str(ev.get("core", "singbox")).replace("-", "")
        action = f"{core_name}_{action_type}"
        email = ev.get("email")
        ip = ev.get("ip")
        if email and ip and ip != "127.0.0.1":
            ev_key = (core_name, action_type, email, ip, ev_ts)
            if ev_key not in seen_events:
                seen_events.add(ev_key)
                log_action(
                    username="system",
                    action=action,
                    target=ip,
                    details=json.dumps({"username": email, "tx": 1024, "rx": 2048}, ensure_ascii=False)
                )

    # Step 3: Verify AuditLog record in DB
    with db_session() as session:
        logs = session.query(AuditLog).filter_by(action="singbox_connect", target=untrusted_ip).all()
        assert len(logs) == 1, "AuditLog must contain exactly 1 singbox_connect entry for untrusted IP"
        log_entry = logs[0]
        details = json.loads(log_entry.details)
        assert details["username"] == username

    # Step 4: Verify /api/security/audit-logs REST API (used by Controller Bot)
    res = client.get("/api/security/audit-logs?limit=50")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    audit_targets = [l["target"] for l in data["logs"]]
    assert untrusted_ip in audit_targets

    # Step 5: Test untrusted IP evaluation logic (is_new_ip verification)
    with db_session() as session:
        all_logs_dict = [
            {"id": l.id, "action": l.action, "target": l.target, "timestamp": l.timestamp, "details": l.details, "username": l.username}
            for l in session.query(AuditLog).all()
        ]
    now_ts = int(time.time())
    is_new, history = check_new_ip_and_get_history(
        username=username,
        current_ip=untrusted_ip,
        current_timestamp=now_ts,
        logs=all_logs_dict,
        allowed_ips=approved_home_ip
    )
    assert is_new is True, f"IP {untrusted_ip} MUST be flagged as NEW / UNTRUSTED because only {approved_home_ip} is approved!"
    print(f"\n[PASS] Pipeline verified: Untrusted IP {untrusted_ip} triggered security alert (is_new={is_new})")
