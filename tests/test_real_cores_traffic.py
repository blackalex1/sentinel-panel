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

@pytest.fixture(autouse=True)
def cleanup_cores():
    yield
    stop_xray()
    stop_hysteria()
    stop_singbox()

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
    from backend.singbox.service import _last_singbox_conn_stats
    _last_singbox_conn_stats.clear()

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

