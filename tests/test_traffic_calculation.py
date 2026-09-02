import pytest
from unittest.mock import patch, MagicMock
from backend.database import db_session, Inbound, ClientStats, get_all_inbounds
from backend.singbox.service import query_singbox_traffic, stop_singbox
from backend.xray.service import process_stats_deltas, _last_session_stats, stop_xray
from backend.sentinel_core_bridge.traffic_sessions import reset_unified_traffic_stats

def test_singbox_traffic_calculation_cumulative_deltas(monkeypatch):
    """
    Verifies that Sing-box traffic delta calculation correctly uses cumulative
    bytes from sentinel-core get_unified_traffic() across multiple poll cycles.
    """
    stop_singbox()
    reset_unified_traffic_stats()

    email = "test_user_singbox@example.com"
    with db_session() as session:
        session.query(ClientStats).filter_by(email=email).delete()
        ib = session.query(Inbound).filter_by(core="singbox").first()
        if not ib:
            ib = Inbound(remark="Singbox Test Inbound", port=19090, protocol="vless", core="singbox", enable=1)
            session.add(ib)
            session.commit()
        ib_id = ib.id
        c = ClientStats(inbound_id=ib_id, email=email, client_uuid_or_pwd="uuid-test-sb", up=0, down=0)
        session.add(c)
        session.commit()

    monkeypatch.setattr("backend.singbox.service.is_singbox_running", lambda: True)

    # Poll 1: sentinel-core reports 100 MB down, 10 MB up (cumulative)
    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic",
               return_value={email: {"downBytes": 100 * 1024 * 1024, "upBytes": 10 * 1024 * 1024}}), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=[]), \
         patch("backend.sentinel_core_bridge.traffic_sessions.register_external_connect"):
        query_singbox_traffic()

    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=email).first()
        assert c.down == 100 * 1024 * 1024, f"Poll 1 down: expected 100MB got {c.down}"
        assert c.up == 10 * 1024 * 1024, f"Poll 1 up: expected 10MB got {c.up}"

    # Poll 2: cumulative totals increase to 300 MB down, 30 MB up → delta = +200MB / +20MB
    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic",
               return_value={email: {"downBytes": 300 * 1024 * 1024, "upBytes": 30 * 1024 * 1024}}), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=[]), \
         patch("backend.sentinel_core_bridge.traffic_sessions.register_external_connect"):
        query_singbox_traffic()

    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=email).first()
        assert c.down == 300 * 1024 * 1024, f"Poll 2 down: expected 300MB got {c.down}"
        assert c.up == 30 * 1024 * 1024, f"Poll 2 up: expected 30MB got {c.up}"

    # Poll 3: new connection cycle; sentinel-core resets counter to 50 MB (counter wrap)
    # delta must be treated as 50 MB (not -250 MB), so total becomes 300+50=350 MB
    with patch("backend.sentinel_core_bridge.traffic_sessions.get_unified_traffic",
               return_value={email: {"downBytes": 50 * 1024 * 1024, "upBytes": 5 * 1024 * 1024}}), \
         patch("backend.sentinel_core_bridge.traffic_sessions.get_active_sessions", return_value=[]), \
         patch("backend.sentinel_core_bridge.traffic_sessions.register_external_connect"):
        query_singbox_traffic()

    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=email).first()
        assert c.down == 350 * 1024 * 1024, f"Poll 3 down: expected 350MB got {c.down}"
        assert c.up == 35 * 1024 * 1024, f"Poll 3 up: expected 35MB got {c.up}"

    stop_singbox()



def test_xray_traffic_calculation_single_update_per_email():
    """
    Verifies that Xray user stats update a user's client traffic once per email
    instead of multiplying traffic by N inbounds.
    """
    stop_xray()
    email = "multi_inbound_user@example.com"
    
    with db_session() as session:
        session.query(ClientStats).filter_by(email=email).delete()
        inbounds = session.query(Inbound).limit(2).all()
        if len(inbounds) < 2:
            ib1 = Inbound(remark="IB 1", port=40001, protocol="vless")
            ib2 = Inbound(remark="IB 2", port=40002, protocol="vmess")
            session.add_all([ib1, ib2])
            session.commit()
            inbounds = [ib1, ib2]

        c1 = ClientStats(inbound_id=inbounds[0].id, email=email, client_uuid_or_pwd="pwd1", up=0, down=0)
        c2 = ClientStats(inbound_id=inbounds[1].id, email=email, client_uuid_or_pwd="pwd2", up=0, down=0)
        session.add_all([c1, c2])
        session.commit()

    stats_list = [
        {"name": f"user>>>{email}>>>traffic>>>downlink", "value": 500 * 1024 * 1024},
        {"name": f"user>>>{email}>>>traffic>>>uplink", "value": 50 * 1024 * 1024}
    ]

    process_stats_deltas(stats_list)

    # Check that sum across all ClientStats records for email equals EXACTLY 500MB down / 50MB up (not 1000MB / 100MB)
    with db_session() as session:
        records = session.query(ClientStats).filter_by(email=email).all()
        total_down = sum(r.down for r in records)
        total_up = sum(r.up for r in records)
        assert total_down == 500 * 1024 * 1024
        assert total_up == 50 * 1024 * 1024

    stop_xray()
