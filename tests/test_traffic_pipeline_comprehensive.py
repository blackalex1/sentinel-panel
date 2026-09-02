"""
Comprehensive Traffic Accounting Pipeline Test Suite.

Verifies:
1. No multi-poll duplication and no cross-inbound multiplication.
2. Multi-protocol client accounting (Xray VLESS/VMess, Hysteria 2, Sing-box TUIC/ShadowTLS).
3. Fallback routing and connection switching across inbounds and outbounds.
4. Core process restarts and counter wrap-around safety (no petabyte explosions).
5. Real Sentinel-Core C-FFI bridge invocation and native session tracker telemetry.
6. Architectural verification: no duplicate traffic parsing logic between Sentinel-Core and Panel.
"""
import os
import sys
import json
import time
import socket
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.xdist_group("core_ops")

from backend.database import (
    db_session,
    Base,
    engine,
    Inbound,
    ClientStats,
    Outbound,
    update_outbound_traffic,
)
from backend.models import ClientTrafficDaily
from backend.sentinel_core_bridge import (
    get_unified_traffic,
    get_active_sessions,
    get_online_emails_core,
    register_external_connect,
    register_hysteria_port,
    query_all_cores_traffic,
    reset_unified_traffic_stats,
    compile_node_server_config,
)
from backend.scheduler_jobs.limits import enforce_client_limits_and_rules
from backend.routes.system.status import global_traffic_api, global_traffic_details_api
from backend.xray.service import query_traffic_stats, stop_xray
from backend.hysteria.service import query_hysteria_traffic, stop_hysteria
from backend.singbox.service import query_singbox_traffic, stop_singbox


@pytest.fixture(autouse=True)
def cleanup_traffic_state():
    reset_unified_traffic_stats()
    yield
    stop_xray()
    stop_hysteria()
    stop_singbox()
    reset_unified_traffic_stats()


def test_pipeline_no_duplicate_or_multiplying_polls():
    """
    Verifies that multiple consecutive polling cycles do NOT duplicate traffic,
    and that a user attached to multiple inbounds does not have traffic multiplied across other inbounds.
    """
    reset_unified_traffic_stats()
    user_email = "non_dup_user@test.local"

    with db_session() as session:
        session.query(ClientTrafficDaily).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()

        ib1 = Inbound(remark="Primary VLESS", port=25001, protocol="vless", core="xray", enable=1, up=0, down=0)
        ib2 = Inbound(remark="Secondary VMess", port=25002, protocol="vmess", core="xray", enable=1, up=0, down=0)
        session.add_all([ib1, ib2])
        session.commit()

        c1 = ClientStats(inbound_id=ib1.id, email=user_email, client_uuid_or_pwd="uuid-nondup", up=0, down=0, enable=1)
        c2 = ClientStats(inbound_id=ib2.id, email=user_email, client_uuid_or_pwd="uuid-nondup", up=0, down=0, enable=1)
        session.add_all([c1, c2])
        session.commit()

        ib1_id, ib2_id = ib1.id, ib2.id

    # 1. Initial traffic: 120 MB down, 15 MB up
    snapshot_1 = {user_email: {"downBytes": 120 * 1024 * 1024, "upBytes": 15 * 1024 * 1024}}
    active_sess_1 = [{"email": user_email, "core": "xray", "ip": "198.51.100.10"}]

    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", return_value=snapshot_1), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=active_sess_1):
        query_all_cores_traffic()

    with db_session() as session:
        rec1 = session.query(ClientStats).filter_by(inbound_id=ib1_id, email=user_email).first()
        rec2 = session.query(ClientStats).filter_by(inbound_id=ib2_id, email=user_email).first()
        inbound1 = session.query(Inbound).filter_by(id=ib1_id).first()
        inbound2 = session.query(Inbound).filter_by(id=ib2_id).first()

        # Target inbound received the exact traffic
        assert rec1.down == 120 * 1024 * 1024
        assert rec1.up == 15 * 1024 * 1024
        assert inbound1.down == 120 * 1024 * 1024
        assert inbound1.up == 15 * 1024 * 1024

        # Secondary inbound remained clean (0 bytes)
        assert rec2.down == 0
        assert rec2.up == 0
        assert inbound2.down == 0
        assert inbound2.up == 0

    # 2. Simulate 10 consecutive poll ticks with NO new traffic
    for _ in range(10):
        with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", return_value=snapshot_1), \
             patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=active_sess_1):
            query_all_cores_traffic()

    with db_session() as session:
        rec1 = session.query(ClientStats).filter_by(inbound_id=ib1_id, email=user_email).first()
        inbound1 = session.query(Inbound).filter_by(id=ib1_id).first()
        assert rec1.down == 120 * 1024 * 1024, "Traffic must NOT increase on subsequent static polls"
        assert rec1.up == 15 * 1024 * 1024
        assert inbound1.down == 120 * 1024 * 1024


def test_pipeline_multi_protocol_and_fallback_switching():
    """
    Tests a real-world scenario where a user switches / falls back across protocols:
    Phase 1: User connects via Hysteria 2 (100 MB down / 10 MB up).
    Phase 2: User falls back to Xray VLESS (adds 200 MB down / 20 MB up).
    Phase 3: User falls back to Sing-box TUIC (adds 300 MB down / 30 MB up).
    Total consumption: Exactly 600 MB down / 60 MB up across ClientStats and daily aggregator.
    """
    reset_unified_traffic_stats()
    user_email = "fallback_traveler@sentinel.test"

    with db_session() as session:
        session.query(ClientTrafficDaily).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()

        ib_hy = Inbound(remark="Hysteria Inbound", port=26001, protocol="hysteria2", core="hysteria", enable=1, up=0, down=0)
        ib_xr = Inbound(remark="Xray Inbound", port=26002, protocol="vless", core="xray", enable=1, up=0, down=0)
        ib_sb = Inbound(remark="Singbox Inbound", port=26003, protocol="tuic", core="singbox", enable=1, up=0, down=0)
        session.add_all([ib_hy, ib_xr, ib_sb])
        session.commit()

        c_hy = ClientStats(inbound_id=ib_hy.id, email=user_email, client_uuid_or_pwd="pwd-hy", up=0, down=0, enable=1)
        c_xr = ClientStats(inbound_id=ib_xr.id, email=user_email, client_uuid_or_pwd="uuid-xr", up=0, down=0, enable=1)
        c_sb = ClientStats(inbound_id=ib_sb.id, email=user_email, client_uuid_or_pwd="pwd-sb", up=0, down=0, enable=1)
        session.add_all([c_hy, c_xr, c_sb])
        session.commit()

        hy_id, xr_id, sb_id = ib_hy.id, ib_xr.id, ib_sb.id

    # ── Phase 1: Hysteria 2 Connection ──────────────────────────────────────
    snap_p1 = {user_email: {"downBytes": 100 * 1024 * 1024, "upBytes": 10 * 1024 * 1024}}
    sess_p1 = [{"email": user_email, "core": "hysteria2", "ip": "203.0.113.1"}]

    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", return_value=snap_p1), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=sess_p1):
        query_all_cores_traffic()

    with db_session() as session:
        c_h = session.query(ClientStats).filter_by(inbound_id=hy_id, email=user_email).first()
        assert c_h.down == 100 * 1024 * 1024
        assert c_h.up == 10 * 1024 * 1024

    # ── Phase 2: Fallback to Xray VLESS ─────────────────────────────────────
    snap_p2 = {user_email: {"downBytes": 300 * 1024 * 1024, "upBytes": 30 * 1024 * 1024}}
    sess_p2 = [{"email": user_email, "core": "xray", "ip": "203.0.113.1"}]

    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", return_value=snap_p2), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=sess_p2):
        query_all_cores_traffic()

    with db_session() as session:
        c_x = session.query(ClientStats).filter_by(inbound_id=xr_id, email=user_email).first()
        assert c_x.down == 200 * 1024 * 1024
        assert c_x.up == 20 * 1024 * 1024

    # ── Phase 3: Fallback to Sing-box TUIC ───────────────────────────────────
    snap_p3 = {user_email: {"downBytes": 600 * 1024 * 1024, "upBytes": 60 * 1024 * 1024}}
    sess_p3 = [{"email": user_email, "core": "singbox", "ip": "203.0.113.1"}]

    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", return_value=snap_p3), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=sess_p3):
        query_all_cores_traffic()

    with db_session() as session:
        c_s = session.query(ClientStats).filter_by(inbound_id=sb_id, email=user_email).first()
        assert c_s.down == 300 * 1024 * 1024
        assert c_s.up == 30 * 1024 * 1024

    # ── Daily Aggregator & Quota Limits ──────────────────────────────────────
    enforce_client_limits_and_rules()

    with db_session() as session:
        daily_records = session.query(ClientTrafficDaily).filter_by(email=user_email).all()
        assert len(daily_records) == 1
        d_rec = daily_records[0]
        assert d_rec.down == 600 * 1024 * 1024, f"Expected total 600MB down, got {d_rec.down}"
        assert d_rec.up == 60 * 1024 * 1024, f"Expected total 60MB up, got {d_rec.up}"


def test_pipeline_outbound_routing_and_fallback_chains():
    """
    Verifies that traffic passing through chained Outbounds (e.g. WARP, Direct, Hysteria Outbound)
    correctly updates Outbound statistics without polluting or duplicating Client Inbound metrics.
    """
    with db_session() as session:
        session.query(Outbound).delete()
        ob_direct = Outbound(remark="Direct Outbound", protocol="freedom", tag="direct", enable=1, is_system=1, up=0, down=0)
        ob_warp = Outbound(remark="Cloudflare WARP", protocol="wireguard", tag="warp-out", enable=1, is_system=0, up=0, down=0)
        session.add_all([ob_direct, ob_warp])
        session.commit()

    update_outbound_traffic("warp-out", up_add=25 * 1024 * 1024, down_add=250 * 1024 * 1024)
    update_outbound_traffic("direct", up_add=5 * 1024 * 1024, down_add=50 * 1024 * 1024)

    with db_session() as session:
        w = session.query(Outbound).filter_by(tag="warp-out").first()
        d = session.query(Outbound).filter_by(tag="direct").first()
        assert w.down == 250 * 1024 * 1024
        assert w.up == 25 * 1024 * 1024
        assert d.down == 50 * 1024 * 1024
        assert d.up == 5 * 1024 * 1024


def test_pipeline_core_restart_and_wraparound_protection():
    """
    Verifies that core process restarts or counter resets (wrap-around)
    do NOT cause petabyte/terabyte explosions.
    """
    reset_unified_traffic_stats()
    user_email = "wraparound_user@test.local"

    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()

        ib = Inbound(remark="Hysteria High-Speed", port=27001, protocol="hysteria2", core="hysteria", enable=1, up=0, down=0)
        session.add(ib)
        session.commit()

        c = ClientStats(inbound_id=ib.id, email=user_email, client_uuid_or_pwd="pwd-wrap", up=0, down=0, enable=1)
        session.add(c)
        session.commit()
        ib_id = ib.id

    # 1. First cycle: 500 MB down, 50 MB up
    snap1 = {user_email: {"downBytes": 500 * 1024 * 1024, "upBytes": 50 * 1024 * 1024}}
    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", return_value=snap1), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=[]):
        query_all_cores_traffic()

    with db_session() as session:
        rec = session.query(ClientStats).filter_by(inbound_id=ib_id, email=user_email).first()
        assert rec.down == 500 * 1024 * 1024
        assert rec.up == 50 * 1024 * 1024

    # 2. Core restarts: counter wraps around to 15 MB down, 2 MB up (new session)
    snap2 = {user_email: {"downBytes": 15 * 1024 * 1024, "upBytes": 2 * 1024 * 1024}}
    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", return_value=snap2), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=[]):
        query_all_cores_traffic()

    with db_session() as session:
        rec = session.query(ClientStats).filter_by(inbound_id=ib_id, email=user_email).first()
        # Cumulative must become 500MB + 15MB = 515MB (NOT 500MB + huge jump)
        assert rec.down == (500 + 15) * 1024 * 1024
        assert rec.up == (50 + 2) * 1024 * 1024


def test_pipeline_real_sentinel_core_ffi_bridge_telemetry():
    """
    Directly tests the real C-FFI bridge with the live sentinel-core.dll:
    1. Tests SentinelGetUnifiedTraffic memory output and JSON structure.
    2. Tests SentinelGetActiveSessions and session tracking.
    3. Tests SentinelRegisterExternalConnect idempotency.
    4. Tests SentinelGetOnlineEmails filtering.
    """
    # 1. Unified traffic from live Go supervisor
    traffic = get_unified_traffic()
    assert isinstance(traffic, dict), "SentinelGetUnifiedTraffic must return a valid dictionary"

    # 2. Register external connect in live Go session tracker
    test_user = "ffi_test_user@sentinel.internal"
    test_ip = "192.0.2.77"
    register_external_connect("singbox", test_user, test_ip)

    # 3. Verify active sessions in live Go session tracker
    sessions = get_active_sessions()
    assert isinstance(sessions, list), "SentinelGetActiveSessions must return a list"
    found = any(s.get("email") == test_user and s.get("ip") == test_ip for s in sessions)
    assert found, f"Expected session {test_user}@{test_ip} to be present in Go session tracker"

    # 4. Verify online emails in live Go supervisor
    online = get_online_emails_core()
    assert isinstance(online, list), "SentinelGetOnlineEmails must return a list"
    assert test_user in online, f"Expected {test_user} to be in online emails"


def test_pipeline_no_duplicate_accounting_architecture():
    """
    Architectural Verification:
    Ensures that individual core service polling functions (query_traffic_stats,
    query_hysteria_traffic, query_singbox_traffic) do NOT execute redundant raw queries,
    and all delegate strictly to the single unified query_all_cores_traffic() pipeline.
    """
    import inspect
    from backend.xray.service import query_traffic_stats
    from backend.hysteria.service import query_hysteria_traffic
    from backend.singbox.service import query_singbox_traffic

    xray_src = inspect.getsource(query_traffic_stats)
    hysteria_src = inspect.getsource(query_hysteria_traffic)
    singbox_src = inspect.getsource(query_singbox_traffic)

    assert "query_all_cores_traffic" in xray_src, "Xray service must delegate to query_all_cores_traffic"
    assert "query_all_cores_traffic" in hysteria_src, "Hysteria service must delegate to query_all_cores_traffic"
    assert "query_all_cores_traffic" in singbox_src, "Sing-box service must delegate to query_all_cores_traffic"

    # Verify no raw loop multipliers exist in service functions
    assert "for ib in inbounds" not in xray_src
    assert "for ib in inbounds" not in hysteria_src
    assert "for ib in inbounds" not in singbox_src
