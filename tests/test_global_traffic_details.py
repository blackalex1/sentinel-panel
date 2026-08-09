import pytest
import datetime
from unittest.mock import MagicMock
from backend.database import db_session
from backend.models import ClientTrafficDaily
from backend.routes.system.status import global_traffic_details_api

def test_global_traffic_details_api(monkeypatch):
    """
    Verifies that global_traffic_details_api returns correct per-client consumption,
    percentage breakdown, and daily traffic totals.
    """
    test_date_str = "2099-12-31"
    
    with db_session() as session:
        session.query(ClientTrafficDaily).filter_by(date=test_date_str).delete()
        
        # Insert client 1: 700 MB down, 70 MB up
        rec1 = ClientTrafficDaily(
            email="user1@test.com",
            date=test_date_str,
            up=70 * 1024 * 1024,
            down=700 * 1024 * 1024
        )
        # Insert client 2: 300 MB down, 30 MB up
        rec2 = ClientTrafficDaily(
            email="user2@test.com",
            date=test_date_str,
            up=30 * 1024 * 1024,
            down=300 * 1024 * 1024
        )
        session.add(rec1)
        session.add(rec2)
        session.commit()

    req_mock = MagicMock()
    monkeypatch.setattr("backend.routes.system.check_auth", lambda r: True)

    import asyncio
    res = asyncio.run(global_traffic_details_api(req_mock, date=test_date_str))

    assert res["success"] is True
    assert res["date"] == test_date_str
    
    expected_total_down = (700 + 300) * 1024 * 1024
    expected_total_up = (70 + 30) * 1024 * 1024
    expected_total_bytes = expected_total_down + expected_total_up

    assert res["total_up"] == expected_total_up
    assert res["total_down"] == expected_total_down
    assert res["total_bytes"] == expected_total_bytes
    assert len(res["clients"]) == 2

    # User 1 should be first (770 MB total = 70% share)
    top_client = res["clients"][0]
    assert top_client["email"] == "user1@test.com"
    assert top_client["total"] == 770 * 1024 * 1024
    assert top_client["percent"] == 70.0

    # User 2 should be second (330 MB total = 30% share)
    second_client = res["clients"][1]
    assert second_client["email"] == "user2@test.com"
    assert second_client["total"] == 330 * 1024 * 1024
    assert second_client["percent"] == 30.0
