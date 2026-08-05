import pytest
from unittest.mock import patch, MagicMock
from backend.database import db_session, Inbound, ClientStats, get_all_inbounds
from backend.singbox.service import query_singbox_traffic, _last_singbox_conn_stats, stop_singbox
from backend.xray.service import process_stats_deltas, _last_session_stats, stop_xray

def test_singbox_traffic_calculation_per_connection(monkeypatch):
    """
    Verifies that Sing-box traffic calculation tracks per-connection IDs
    and does not lose traffic when connections close or drop.
    """
    stop_singbox()
    
    # 1. Setup mock database records
    email = "test_user_singbox@example.com"
    with db_session() as session:
        session.query(ClientStats).filter_by(email=email).delete()
        ib = session.query(Inbound).first()
        if not ib:
            ib = Inbound(remark="Singbox Test Inbound", port=19090, protocol="vless", core="singbox")
            session.add(ib)
            session.commit()
        
        ib_id = ib.id
        c = ClientStats(inbound_id=ib_id, email=email, client_uuid_or_pwd="uuid-test-sb", up=0, down=0)
        session.add(c)
        session.commit()

    monkeypatch.setattr("backend.singbox.service.is_singbox_running", lambda: True)

    # 2. Poll 1: Active Connection 1 (100MB down, 10MB up)
    mock_resp_1 = MagicMock()
    mock_resp_1.status_code = 200
    mock_resp_1.json.return_value = {
        "connections": [
            {
                "id": "conn-1",
                "metadata": {"user": email, "inboundName": f"inbound-{ib_id}"},
                "download": 100 * 1024 * 1024,
                "upload": 10 * 1024 * 1024
            }
        ]
    }

    with patch("requests.get", return_value=mock_resp_1):
        query_singbox_traffic()

    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=email).first()
        assert c.down == 100 * 1024 * 1024
        assert c.up == 10 * 1024 * 1024

    # 3. Poll 2: Connection 1 updates to (300MB down, 30MB up)
    mock_resp_2 = MagicMock()
    mock_resp_2.status_code = 200
    mock_resp_2.json.return_value = {
        "connections": [
            {
                "id": "conn-1",
                "metadata": {"user": email, "inboundName": f"inbound-{ib_id}"},
                "download": 300 * 1024 * 1024,
                "upload": 30 * 1024 * 1024
            }
        ]
    }

    with patch("requests.get", return_value=mock_resp_2):
        query_singbox_traffic()

    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=email).first()
        assert c.down == 300 * 1024 * 1024
        assert c.up == 30 * 1024 * 1024

    # 4. Poll 3: Connection 1 CLOSED, new Connection 2 opens (50MB down, 5MB up)
    mock_resp_3 = MagicMock()
    mock_resp_3.status_code = 200
    mock_resp_3.json.return_value = {
        "connections": [
            {
                "id": "conn-2",
                "metadata": {"user": email, "inboundName": f"inbound-{ib_id}"},
                "download": 50 * 1024 * 1024,
                "upload": 5 * 1024 * 1024
            }
        ]
    }

    with patch("requests.get", return_value=mock_resp_3):
        query_singbox_traffic()

    # The user's total traffic must be 300MB (from closed conn-1) + 50MB (from conn-2) = 350MB!
    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=email).first()
        assert c.down == 350 * 1024 * 1024
        assert c.up == 35 * 1024 * 1024

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
