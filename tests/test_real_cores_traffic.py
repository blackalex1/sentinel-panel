import pytest
import time
import datetime

pytestmark = pytest.mark.xdist_group("core_ops")

from unittest.mock import patch, MagicMock
from backend.database import db_session, Inbound, ClientStats
from backend.models import ClientTrafficDaily
from backend.xray.service import query_traffic_stats, process_stats_deltas, stop_xray
from backend.hysteria.service import query_hysteria_traffic, stop_hysteria
from backend.singbox.service import query_singbox_traffic, stop_singbox
from backend.scheduler_jobs.limits import enforce_client_limits_and_rules
from backend.routes.system.status import global_traffic_api
from backend.routes.security_routes.management import get_top_traffic
from backend.sentinel_core_bridge.traffic_sessions import reset_unified_traffic_stats

@pytest.fixture(autouse=True)
def cleanup_cores():
    reset_unified_traffic_stats()
    yield
    stop_xray()
    stop_hysteria()
    stop_singbox()
    reset_unified_traffic_stats()

def test_real_cores_traffic_accounting_and_dashboard_aggregation(client, monkeypatch):
    """
    Integration test verifying that:
    1. Traffic is recorded accurately for Xray, Hysteria 2, and Sing-box cores.
    2. No multi-inbound duplication occurs for users with multiple inbounds.
    3. Closed connections in Sing-box retain all accumulated bytes.
    4. Main page / dashboard statistics APIs (/panel/api/system/global-traffic and /api/security/top-traffic)
       correctly display the exact total aggregated traffic across ALL core types.
    """
    today_str = datetime.date.today().isoformat()
    
    email_xray = "user_xray@domain.com"
    email_hysteria = "user_hysteria@domain.com"
    email_singbox = "user_singbox@domain.com"

    # Setup database records for each core type
    with db_session() as session:
        session.query(ClientTrafficDaily).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.commit()

        ib_xray_1 = Inbound(remark="Xray VLESS", port=21001, protocol="vless", core="xray", enable=1)
        ib_xray_2 = Inbound(remark="Xray VMess", port=21002, protocol="vmess", core="xray", enable=1)
        ib_hysteria = Inbound(remark="Hysteria 2", port=21003, protocol="hysteria2", core="hysteria", enable=1)
        ib_singbox = Inbound(remark="Singbox TUIC", port=21004, protocol="tuic", core="singbox", enable=1)

        session.add_all([ib_xray_1, ib_xray_2, ib_hysteria, ib_singbox])
        session.commit()

        # User Xray is attached to TWO Xray inbounds
        c_x1 = ClientStats(inbound_id=ib_xray_1.id, email=email_xray, client_uuid_or_pwd="uuid-xray", up=0, down=0, enable=1)
        c_x2 = ClientStats(inbound_id=ib_xray_2.id, email=email_xray, client_uuid_or_pwd="uuid-xray", up=0, down=0, enable=1)
        # User Hysteria
        c_h = ClientStats(inbound_id=ib_hysteria.id, email=email_hysteria, client_uuid_or_pwd="pwd-hysteria", up=0, down=0, enable=1)
        # User Singbox
        c_s = ClientStats(inbound_id=ib_singbox.id, email=email_singbox, client_uuid_or_pwd="pwd-singbox", up=0, down=0, enable=1)

        session.add_all([c_x1, c_x2, c_h, c_s])
        session.commit()
        
        ib_xray_1_id = ib_xray_1.id
        ib_hysteria_id = ib_hysteria.id
        ib_singbox_id = ib_singbox.id

    # -------------------------------------------------------------
    # 1. SIMULATE TRAFFIC FOR XRAY
    # -------------------------------------------------------------
    # Xray returns 500 MB down, 50 MB up for user_xray@domain.com
    xray_stats = [
        {"name": f"user>>>{email_xray}>>>traffic>>>downlink", "value": 500 * 1024 * 1024},
        {"name": f"user>>>{email_xray}>>>traffic>>>uplink", "value": 50 * 1024 * 1024},
        {"name": f"inbound>>>inbound-{ib_xray_1_id}>>>traffic>>>downlink", "value": 500 * 1024 * 1024},
        {"name": f"inbound>>>inbound-{ib_xray_1_id}>>>traffic>>>uplink", "value": 50 * 1024 * 1024}
    ]
    process_stats_deltas(xray_stats)

    # Verify Xray stats (No N-fold multiplication!)
    with db_session() as session:
        x_records = session.query(ClientStats).filter_by(email=email_xray).all()
        x_total_down = sum(r.down for r in x_records)
        x_total_up = sum(r.up for r in x_records)
        assert x_total_down == 500 * 1024 * 1024, f"Xray down expected 500MB, got {x_total_down}"
        assert x_total_up == 50 * 1024 * 1024, f"Xray up expected 50MB, got {x_total_up}"

    # -------------------------------------------------------------
    # 2. SIMULATE TRAFFIC FOR HYSTERIA 2
    # -------------------------------------------------------------
    monkeypatch.setattr("backend.hysteria.service.is_hysteria_running", lambda: True)
    monkeypatch.setattr("backend.sentinel_core_bridge.get_unified_traffic", lambda: {
        email_hysteria: {"downBytes": 300 * 1024 * 1024, "upBytes": 30 * 1024 * 1024}
    })
    query_hysteria_traffic()

    with db_session() as session:
        h_rec = session.query(ClientStats).filter_by(email=email_hysteria).first()
        assert h_rec.down == 300 * 1024 * 1024, f"Hysteria down expected 300MB, got {h_rec.down}"
        assert h_rec.up == 30 * 1024 * 1024, f"Hysteria up expected 30MB, got {h_rec.up}"

    # -------------------------------------------------------------
    # 3. SIMULATE TRAFFIC FOR SING-BOX (WITH CLOSED CONNECTIONS)
    # _process_singbox_connection_data removed; sentinel-core (Go) handles
    # all Clash API parsing. query_singbox_traffic() reads cumulative totals
    # from SentinelGetUnifiedTraffic and calculates deltas in Python.
    # -------------------------------------------------------------
    monkeypatch.setattr("backend.singbox.service.is_singbox_running", lambda: True)
    reset_unified_traffic_stats()

    # Phase 1: sentinel-core reports cumulative 200 MB down, 20 MB up
    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic",
               return_value={email_singbox: {"downBytes": 200 * 1024 * 1024, "upBytes": 20 * 1024 * 1024}}), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=[]), \
         patch("backend.sentinel_core_bridge.traffic_sessions.register_external_connect"):
        query_singbox_traffic()

    # Phase 2: old connection closed, new one opens — cumulative resets to 100 MB
    # (sentinel-core resets counters when connections drop, Python treats as new delta)
    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic",
               return_value={email_singbox: {"downBytes": 100 * 1024 * 1024, "upBytes": 10 * 1024 * 1024}}), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=[]), \
         patch("backend.sentinel_core_bridge.traffic_sessions.register_external_connect"):
        query_singbox_traffic()

    with db_session() as session:
        s_rec = session.query(ClientStats).filter_by(email=email_singbox).first()
        # Total: 200 MB (phase 1) + 100 MB (phase 2, counter wrap = new delta) = 300 MB
        assert s_rec.down == 300 * 1024 * 1024, f"Singbox down expected 300MB, got {s_rec.down}"
        assert s_rec.up == 30 * 1024 * 1024, f"Singbox up expected 30MB, got {s_rec.up}"

    # -------------------------------------------------------------
    # 4. RUN LIMITS & DAILY TRAFFIC AGGREGATOR
    # -------------------------------------------------------------
    enforce_client_limits_and_rules()

    # Expected Total Across All Cores:
    # Xray: 500 MB down, 50 MB up
    # Hysteria 2: 300 MB down, 30 MB up
    # Sing-box: 300 MB down, 30 MB up
    # GRAND TOTAL: Down = 1100 MB, Up = 110 MB
    expected_total_down = (500 + 300 + 300) * 1024 * 1024
    expected_total_up = (50 + 30 + 30) * 1024 * 1024

    # -------------------------------------------------------------
    # 5. VERIFY MAIN PAGE / DASHBOARD STATISTICS APIs
    # -------------------------------------------------------------

    req_mock = MagicMock()
    req_mock.cookies.get.return_value = None
    monkeypatch.setattr("backend.routes.system.check_auth", lambda r: True)
    monkeypatch.setattr("backend.routes.security_routes.management.check_auth", lambda r: True)

    import asyncio
    global_traffic_res = asyncio.run(global_traffic_api(req_mock))
    assert global_traffic_res["success"] is True

    today_entry = next((item for item in global_traffic_res["obj"] if item["date"] == today_str), None)
    assert today_entry is not None, f"Today's entry ({today_str}) missing from global traffic API"
    assert today_entry["down"] == expected_total_down, f"Dashboard global traffic down expected {expected_total_down}, got {today_entry['down']}"
    assert today_entry["up"] == expected_total_up, f"Dashboard global traffic up expected {expected_total_up}, got {today_entry['up']}"

    # B) Test Top Traffic API (/api/security/top-traffic?period=today)
    top_traffic_res = asyncio.run(get_top_traffic(req_mock, period="today"))
    assert top_traffic_res["success"] is True
    top_users = {u["email"]: u for u in top_traffic_res["users"]}

    assert email_xray in top_users
    assert top_users[email_xray]["down"] == 500 * 1024 * 1024
    assert top_users[email_xray]["up"] == 50 * 1024 * 1024

    assert email_hysteria in top_users
    assert top_users[email_hysteria]["down"] == 300 * 1024 * 1024
    assert top_users[email_hysteria]["up"] == 30 * 1024 * 1024

    assert email_singbox in top_users
    assert top_users[email_singbox]["down"] == 300 * 1024 * 1024
    assert top_users[email_singbox]["up"] == 30 * 1024 * 1024

    sum_all_top_down = sum(u["down"] for u in top_users.values())
    sum_all_top_up = sum(u["up"] for u in top_users.values())

    assert sum_all_top_down == expected_total_down, f"Sum of top traffic down expected {expected_total_down}, got {sum_all_top_down}"
    assert sum_all_top_up == expected_total_up, f"Sum of top traffic up expected {expected_total_up}, got {sum_all_top_up}"


def test_custom_token_uuid_and_bot_search_client_traffic_integration(monkeypatch):
    """
    Verifies that clients connecting via custom UUIDs, passwords, or tokens (not matching full email)
    accumulate traffic correctly in ClientStats and are found by the /api/security/search-client endpoint.
    """
    from backend.routes.security_routes.management import search_client
    import asyncio

    with db_session() as session:
        ib_hy = Inbound(remark="Hysteria Dynamic IB", port=21010, protocol="hysteria2", core="hysteria", enable=1)
        session.add(ib_hy)
        session.commit()

        # Client 1: Registered with email 'test_user_alpha@vpn.internal' and client_uuid_or_pwd 'token_alpha'
        c1 = ClientStats(inbound_id=ib_hy.id, email="test_user_alpha@vpn.internal", client_uuid_or_pwd="token_alpha", up=0, down=0, enable=1)
        # Client 2: Registered with email 'token_beta@vpn.internal' and password 'pwd_beta'
        c2 = ClientStats(inbound_id=ib_hy.id, email="token_beta@vpn.internal", client_uuid_or_pwd="pwd_beta", up=0, down=0, enable=1)
        session.add_all([c1, c2])
        session.commit()

    # 1. Simulate Hysteria 2 traffic arriving for tokens 'token_alpha' and 'token_beta'
    monkeypatch.setattr("backend.hysteria.service.is_hysteria_running", lambda: True)
    monkeypatch.setattr("backend.sentinel_core_bridge.get_unified_traffic", lambda: {
        "token_alpha": {"downBytes": 45 * 1024 * 1024, "upBytes": 5 * 1024 * 1024},
        "token_beta": {"downBytes": 80 * 1024 * 1024, "upBytes": 12 * 1024 * 1024}
    })
    query_hysteria_traffic()

    # 2. Verify database records are updated non-zero
    with db_session() as session:
        rec1 = session.query(ClientStats).filter_by(client_uuid_or_pwd="token_alpha").first()
        assert rec1.down == 45 * 1024 * 1024, f"Expected 45MB down, got {rec1.down}"
        assert rec1.up == 5 * 1024 * 1024, f"Expected 5MB up, got {rec1.up}"

        rec2 = session.query(ClientStats).filter_by(client_uuid_or_pwd="pwd_beta").first()
        assert rec2.down == 80 * 1024 * 1024, f"Expected 80MB down, got {rec2.down}"
        assert rec2.up == 12 * 1024 * 1024, f"Expected 12MB up, got {rec2.up}"

    # 3. Simulate Telegram Bot calling GET /api/security/search-client?key=token_alpha
    req_mock = MagicMock()
    req_mock.cookies.get.return_value = None
    monkeypatch.setattr("backend.routes.security_routes.management.check_auth", lambda r: True)

    res_alpha = asyncio.run(search_client(req_mock, key="token_alpha"))
    assert res_alpha.get("success") is True, f"Search for 'token_alpha' failed: {res_alpha}"
    assert len(res_alpha.get("clients", [])) > 0
    client_item = res_alpha["clients"][0]["client"]
    assert client_item["down"] == 45 * 1024 * 1024
    assert client_item["up"] == 5 * 1024 * 1024

    # 4. Simulate Telegram Bot calling GET /api/security/search-client?key=token_beta
    res_beta = asyncio.run(search_client(req_mock, key="token_beta"))
    assert res_beta.get("success") is True, f"Search for 'token_beta' failed: {res_beta}"
    assert len(res_beta.get("clients", [])) > 0
    client_item_2 = res_beta["clients"][0]["client"]
    assert client_item_2["down"] == 80 * 1024 * 1024
    assert client_item_2["up"] == 12 * 1024 * 1024


def test_hysteria2_multi_poll_and_client_reset_isolation(client, monkeypatch):
    """
    Verifies that:
    1. Consecutive polls of Hysteria 2 traffic with static cumulative stats DO NOT compound (no N*traffic inflation).
    2. Incremental traffic increases (e.g. 50MB -> 60MB) are recorded as accurate deltas (10MB).
    3. Resetting traffic for client A synchronizes their baseline and leaves client B completely intact.
    4. sanitize_anomalous_traffic_db() safely detects and repairs impossible Petabyte values.
    """
    from backend.sentinel_core_bridge.traffic_sessions import (
        reset_unified_traffic_stats,
        sync_client_traffic_baseline,
        query_all_cores_traffic,
    )
    from backend.database.crud.clients import (
        reset_client_traffic_globally_db,
        sanitize_anomalous_traffic_db,
    )

    reset_unified_traffic_stats()
    user_a = "user_a@hysteria.test"
    user_b = "user_b@hysteria.test"

    with db_session() as session:
        session.query(ClientTrafficDaily).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.commit()

        ib = Inbound(remark="Hysteria MultiPoll", port=21050, protocol="hysteria2", core="hysteria", enable=1)
        session.add(ib)
        session.commit()

        ca = ClientStats(inbound_id=ib.id, email=user_a, client_uuid_or_pwd="pwd-a", up=0, down=0, enable=1)
        cb = ClientStats(inbound_id=ib.id, email=user_b, client_uuid_or_pwd="pwd-b", up=0, down=0, enable=1)
        session.add_all([ca, cb])
        session.commit()

    # 1. Simulate 5 consecutive 5-second polling intervals where core cumulative stats remain static at 50 MB / 5 MB
    simulated_traffic = {
        user_a: {"downBytes": 50 * 1024 * 1024, "upBytes": 5 * 1024 * 1024},
        user_b: {"downBytes": 100 * 1024 * 1024, "upBytes": 10 * 1024 * 1024},
    }
    for poll in range(5):
        query_all_cores_traffic(traffic_data_override=simulated_traffic)

    # Verify NO compounding occurred! user_a must have 50MB (not 250MB), user_b must have 100MB (not 500MB)
    with db_session() as session:
        rec_a = session.query(ClientStats).filter_by(email=user_a).first()
        rec_b = session.query(ClientStats).filter_by(email=user_b).first()
        assert rec_a.down == 50 * 1024 * 1024, f"Expected 50MB down for user_a, got {rec_a.down}"
        assert rec_a.up == 5 * 1024 * 1024, f"Expected 5MB up for user_a, got {rec_a.up}"
        assert rec_b.down == 100 * 1024 * 1024, f"Expected 100MB down for user_b, got {rec_b.down}"
        assert rec_b.up == 10 * 1024 * 1024, f"Expected 10MB up for user_b, got {rec_b.up}"

    # 2. Incremental download: user_a transfers 10MB more (cumulative: 60MB), user_b idle (cumulative: 100MB)
    simulated_traffic[user_a] = {"downBytes": 60 * 1024 * 1024, "upBytes": 6 * 1024 * 1024}
    query_all_cores_traffic(traffic_data_override=simulated_traffic)

    with db_session() as session:
        rec_a = session.query(ClientStats).filter_by(email=user_a).first()
        rec_b = session.query(ClientStats).filter_by(email=user_b).first()
        assert rec_a.down == 60 * 1024 * 1024, f"Expected 60MB down for user_a, got {rec_a.down}"
        assert rec_a.up == 6 * 1024 * 1024, f"Expected 6MB up for user_a, got {rec_a.up}"
        assert rec_b.down == 100 * 1024 * 1024, f"Expected 100MB down for user_b, got {rec_b.down}"

    # 3. Reset user_a traffic in DB and sync baseline
    reset_client_traffic_globally_db(user_a)
    sync_client_traffic_baseline(user_a)

    # Next poll with same cumulative data from cores
    query_all_cores_traffic(traffic_data_override=simulated_traffic)

    with db_session() as session:
        rec_a = session.query(ClientStats).filter_by(email=user_a).first()
        rec_b = session.query(ClientStats).filter_by(email=user_b).first()
        # user_a must remain at 0 (not re-polluted with old 60MB)
        assert rec_a.down == 0, f"Expected 0MB down for reset user_a, got {rec_a.down}"
        assert rec_a.up == 0, f"Expected 0MB up for reset user_a, got {rec_a.up}"
        # user_b must NOT be doubled (stays at 100MB)
        assert rec_b.down == 100 * 1024 * 1024, f"Expected user_b to stay at 100MB, got {rec_b.down}"

    # 4. Corrupted Petabyte traffic remediation
    with db_session() as session:
        rec_b = session.query(ClientStats).filter_by(email=user_b).first()
        rec_b.down = 5 * 1024 * 1024 * 1024 * 1024 * 1024  # 5 PB!
        session.commit()

    repaired = sanitize_anomalous_traffic_db()
    assert repaired == 1

    with db_session() as session:
        rec_b = session.query(ClientStats).filter_by(email=user_b).first()
        assert rec_b.down == 0


def test_singbox_clash_api_direct_traffic_and_closed_connections(monkeypatch):
    """
    Verifies that:
    1. Direct Sing-box Clash API traffic (/connections) correctly attributes active connection deltas.
    2. Closed connections (uploadTotal/downloadTotal - active deltas) are credited without byte loss.
    3. Multi-polling with static cumulative stats does not produce compounding inflation.
    4. Client resets properly clear local cumulative and baseline stats.
    """
    import json
    from backend.sentinel_core_bridge.traffic_sessions import (
        reset_unified_traffic_stats,
        sync_client_traffic_baseline,
        query_all_cores_traffic,
    )
    from backend.database.crud.clients import reset_client_traffic_globally_db
    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE

    reset_unified_traffic_stats()
    client_email = "test_user_singbox"
    ACTIVE_IP_CACHE.clear()
    ACTIVE_IP_CACHE[client_email] = {"192.168.1.100": time.time()}

    with db_session() as session:
        session.query(ClientTrafficDaily).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.commit()

        ib_sb = Inbound(remark="VLESS (fallback)", port=21099, protocol="vless", core="singbox", enable=1)
        session.add(ib_sb)
        session.commit()

        c_stat = ClientStats(inbound_id=ib_sb.id, email=client_email, client_uuid_or_pwd="uuid-test-user", up=0, down=0, enable=1)
        session.add(c_stat)
        session.commit()

    # Mock Clash API responses
    current_clash_payload = {
        "downloadTotal": 1024 * 1024,
        "uploadTotal": 256 * 1024,
        "connections": [
            {
                "id": "conn-test-1",
                "upload": 256 * 1024,
                "download": 1024 * 1024,
                "metadata": {
                    "sourceIP": "192.168.1.100",
                    "sourcePort": 49152,
                    "type": "vless-fallback",
                }
            }
        ]
    }

    class MockHTTPResponse:
        def __init__(self, data):
            self.data = data
            self.status = 200
        def read(self):
            return json.dumps(self.data).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: MockHTTPResponse(current_clash_payload))
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", lambda: {})
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", lambda: [
        {"email": client_email, "core": "singbox", "ip": "192.168.1.100"}
    ])

    # Poll 1: Active connection with 1MB down, 256KB up
    query_all_cores_traffic()

    with db_session() as session:
        rec = session.query(ClientStats).filter_by(email=client_email).first()
        assert rec.down == 1024 * 1024, f"Expected 1MB down, got {rec.down}"
        assert rec.up == 256 * 1024, f"Expected 256KB up, got {rec.up}"

    # Poll 2: Connection closed! Total climbed to 3MB down, 768KB up
    current_clash_payload["downloadTotal"] = 3 * 1024 * 1024
    current_clash_payload["uploadTotal"] = 768 * 1024
    current_clash_payload["connections"] = []  # No active connections!

    query_all_cores_traffic()

    with db_session() as session:
        rec = session.query(ClientStats).filter_by(email=client_email).first()
        assert rec.down == 3 * 1024 * 1024, f"Expected 3MB down, got {rec.down}"
        assert rec.up == 768 * 1024, f"Expected 768KB up, got {rec.up}"

    # Poll 3: Idle multi-polling - no new traffic
    for _ in range(3):
        query_all_cores_traffic()

    with db_session() as session:
        rec = session.query(ClientStats).filter_by(email=client_email).first()
        assert rec.down == 3 * 1024 * 1024, f"Expected 3MB down after idle poll, got {rec.down}"
        assert rec.up == 768 * 1024, f"Expected 768KB up after idle poll, got {rec.up}"

    # Poll 4: Reset user stats and verify baseline isolation
    reset_client_traffic_globally_db(client_email)
    sync_client_traffic_baseline(client_email)

    query_all_cores_traffic()

    with db_session() as session:
        rec = session.query(ClientStats).filter_by(email=client_email).first()
        assert rec.down == 0, f"Expected 0 down after reset, got {rec.down}"
        assert rec.up == 0, f"Expected 0 up after reset, got {rec.up}"


def test_multiple_concurrent_clients_pushing_traffic_singbox(monkeypatch):
    """
    Simulates multiple concurrent clients streaming and downloading traffic simultaneously on Sing-box.
    Verifies:
    1. Independent per-client counters with multiple concurrent connections.
    2. Connection close attribution without cross-user leakage.
    3. Idempotent multi-polling without compounding inflation.
    4. Client reset baseline isolation.
    """
    import json
    from backend.sentinel_core_bridge.traffic_sessions import (
        reset_unified_traffic_stats,
        sync_client_traffic_baseline,
        query_all_cores_traffic,
    )
    from backend.database.crud.clients import reset_client_traffic_globally_db
    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE

    reset_unified_traffic_stats()
    user_alpha = "client_alpha@vpn.lan"
    user_beta = "client_beta@vpn.lan"
    user_gamma = "client_gamma@vpn.lan"

    ACTIVE_IP_CACHE.clear()
    ACTIVE_IP_CACHE[user_alpha] = {"198.51.100.10": time.time()}
    ACTIVE_IP_CACHE[user_beta] = {"198.51.100.20": time.time()}
    ACTIVE_IP_CACHE[user_gamma] = {"198.51.100.30": time.time()}

    with db_session() as session:
        session.query(ClientTrafficDaily).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.commit()

        ib_sb = Inbound(remark="VLESS (fallback)", port=21099, protocol="vless", core="singbox", enable=1)
        session.add(ib_sb)
        session.commit()

        c1 = ClientStats(inbound_id=ib_sb.id, email=user_alpha, client_uuid_or_pwd="pwd-alpha", up=0, down=0, enable=1)
        c2 = ClientStats(inbound_id=ib_sb.id, email=user_beta, client_uuid_or_pwd="pwd-beta", up=0, down=0, enable=1)
        c3 = ClientStats(inbound_id=ib_sb.id, email=user_gamma, client_uuid_or_pwd="pwd-gamma", up=0, down=0, enable=1)
        session.add_all([c1, c2, c3])
        session.commit()

    current_clash_payload = {
        "downloadTotal": 0,
        "uploadTotal": 0,
        "connections": []
    }

    class MockHTTPResponse:
        def __init__(self, data):
            self.data = data
            self.status = 200
        def read(self):
            return json.dumps(self.data).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: MockHTTPResponse(current_clash_payload))
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic", lambda: {})
    monkeypatch.setattr("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", lambda: [
        {"email": user_alpha, "core": "singbox", "ip": "198.51.100.10"},
        {"email": user_beta, "core": "singbox", "ip": "198.51.100.20"},
        {"email": user_gamma, "core": "singbox", "ip": "198.51.100.30"},
    ])

    # -------------------------------------------------------------
    # PHASE 1: Concurrent streaming (Alpha 2 conns, Beta 1 conn, Gamma 1 conn)
    # Alpha: 7MB + 3MB = 10MB down, 1MB up
    # Beta: 5MB down, 500KB up
    # Gamma: 2MB down, 200KB up
    # Grand Total: 17MB down, 1.7MB up
    # -------------------------------------------------------------
    current_clash_payload["downloadTotal"] = 17 * 1024 * 1024
    current_clash_payload["uploadTotal"] = 1700 * 1024
    current_clash_payload["connections"] = [
        {"id": "conn-a1", "download": 7 * 1024 * 1024, "upload": 700 * 1024, "metadata": {"sourceIP": "198.51.100.10", "sourcePort": 10001, "type": "vless-fallback"}},
        {"id": "conn-a2", "download": 3 * 1024 * 1024, "upload": 300 * 1024, "metadata": {"sourceIP": "198.51.100.10", "sourcePort": 10002, "type": "vless-fallback"}},
        {"id": "conn-b1", "download": 5 * 1024 * 1024, "upload": 500 * 1024, "metadata": {"sourceIP": "198.51.100.20", "sourcePort": 20001, "type": "vless-fallback"}},
        {"id": "conn-g1", "download": 2 * 1024 * 1024, "upload": 200 * 1024, "metadata": {"sourceIP": "198.51.100.30", "sourcePort": 30001, "type": "vless-fallback"}},
    ]

    query_all_cores_traffic()

    with db_session() as session:
        rec_a = session.query(ClientStats).filter_by(email=user_alpha).first()
        rec_b = session.query(ClientStats).filter_by(email=user_beta).first()
        rec_c = session.query(ClientStats).filter_by(email=user_gamma).first()

        assert rec_a.down == 10 * 1024 * 1024, f"Phase 1 Alpha expected 10MB down, got {rec_a.down}"
        assert rec_a.up == 1000 * 1024, f"Phase 1 Alpha expected 1MB up, got {rec_a.up}"

        assert rec_b.down == 5 * 1024 * 1024, f"Phase 1 Beta expected 5MB down, got {rec_b.down}"
        assert rec_b.up == 500 * 1024, f"Phase 1 Beta expected 500KB up, got {rec_b.up}"

        assert rec_c.down == 2 * 1024 * 1024, f"Phase 1 Gamma expected 2MB down, got {rec_c.down}"
        assert rec_c.up == 200 * 1024, f"Phase 1 Gamma expected 200KB up, got {rec_c.up}"

    # -------------------------------------------------------------
    # PHASE 2: Alpha adds +5MB, Beta adds +5MB, Gamma transfers +3MB and DISCONNECTS!
    # Alpha total = 15MB down, 1.5MB up
    # Beta total = 10MB down, 1.0MB up
    # Gamma total = 5MB down, 500KB up
    # Grand Total: 30MB down, 3.0MB up
    # -------------------------------------------------------------
    current_clash_payload["downloadTotal"] = 30 * 1024 * 1024
    current_clash_payload["uploadTotal"] = 3000 * 1024
    current_clash_payload["connections"] = [
        {"id": "conn-a1", "download": 10 * 1024 * 1024, "upload": 1000 * 1024, "metadata": {"sourceIP": "198.51.100.10", "sourcePort": 10001, "type": "vless-fallback"}},
        {"id": "conn-a2", "download": 5 * 1024 * 1024, "upload": 500 * 1024, "metadata": {"sourceIP": "198.51.100.10", "sourcePort": 10002, "type": "vless-fallback"}},
        {"id": "conn-b1", "download": 10 * 1024 * 1024, "upload": 1000 * 1024, "metadata": {"sourceIP": "198.51.100.20", "sourcePort": 20001, "type": "vless-fallback"}},
        # conn-g1 is closed/gone
    ]

    query_all_cores_traffic()

    with db_session() as session:
        rec_a = session.query(ClientStats).filter_by(email=user_alpha).first()
        rec_b = session.query(ClientStats).filter_by(email=user_beta).first()
        rec_c = session.query(ClientStats).filter_by(email=user_gamma).first()

        assert rec_a.down == 15 * 1024 * 1024, f"Phase 2 Alpha expected 15MB down, got {rec_a.down}"
        assert rec_a.up == 1500 * 1024, f"Phase 2 Alpha expected 1.5MB up, got {rec_a.up}"

        assert rec_b.down == 10 * 1024 * 1024, f"Phase 2 Beta expected 10MB down, got {rec_b.down}"
        assert rec_b.up == 1000 * 1024, f"Phase 2 Beta expected 1MB up, got {rec_b.up}"

        assert rec_c.down == 5 * 1024 * 1024, f"Phase 2 Gamma expected 5MB down, got {rec_c.down}"
        assert rec_c.up == 500 * 1024, f"Phase 2 Gamma expected 500KB up, got {rec_c.up}"

    # -------------------------------------------------------------
    # PHASE 3: Idempotent multi-polling (no new traffic)
    # -------------------------------------------------------------
    for _ in range(3):
        query_all_cores_traffic()

    with db_session() as session:
        rec_a = session.query(ClientStats).filter_by(email=user_alpha).first()
        rec_b = session.query(ClientStats).filter_by(email=user_beta).first()
        rec_c = session.query(ClientStats).filter_by(email=user_gamma).first()

        assert rec_a.down == 15 * 1024 * 1024
        assert rec_b.down == 10 * 1024 * 1024
        assert rec_c.down == 5 * 1024 * 1024

    # -------------------------------------------------------------
    # PHASE 4: Reset Alpha only, ensure Beta & Gamma remain unchanged
    # -------------------------------------------------------------
    reset_client_traffic_globally_db(user_alpha)
    sync_client_traffic_baseline(user_alpha)

    query_all_cores_traffic()

    with db_session() as session:
        rec_a = session.query(ClientStats).filter_by(email=user_alpha).first()
        rec_b = session.query(ClientStats).filter_by(email=user_beta).first()
        rec_c = session.query(ClientStats).filter_by(email=user_gamma).first()

        assert rec_a.down == 0, f"Expected Alpha reset to 0, got {rec_a.down}"
        assert rec_a.up == 0, f"Expected Alpha reset to 0, got {rec_a.up}"

        assert rec_b.down == 10 * 1024 * 1024, f"Expected Beta unchanged at 10MB, got {rec_b.down}"
        assert rec_b.up == 1000 * 1024, f"Expected Beta unchanged at 1MB, got {rec_b.up}"

        assert rec_c.down == 5 * 1024 * 1024, f"Expected Gamma unchanged at 5MB, got {rec_c.down}"
        assert rec_c.up == 500 * 1024, f"Expected Gamma unchanged at 500KB, got {rec_c.up}"



