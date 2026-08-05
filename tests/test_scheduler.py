import time
import datetime
from backend.database import db_session
from backend.models import ClientStats, Inbound, ClientTrafficDaily
from backend.scheduler import enforce_client_limits_and_rules, ACTIVE_IP_CACHE

def test_traffic_limit_enforcement(monkeypatch):
    """Test background limits checker blocks clients on traffic limit."""
    # Pre-populate db
    with db_session() as session:
        ib = Inbound(remark="Limit Inbound", port=60080, protocol="vless", enable=1)
        session.add(ib)
        session.flush()
        
        c1 = ClientStats(
            inbound_id=ib.id,
            email="traffic_exceeded@mail.com",
            client_uuid_or_pwd="pass1",
            up=10 * 1024 * 1024 * 1024,
            down=10 * 1024 * 1024 * 1024,
            total=15 * 1024 * 1024 * 1024,
            enable=1
        )
        c2 = ClientStats(
            inbound_id=ib.id,
            email="traffic_ok@mail.com",
            client_uuid_or_pwd="pass2",
            up=1 * 1024 * 1024 * 1024,
            down=1 * 1024 * 1024 * 1024,
            total=15 * 1024 * 1024 * 1024,
            enable=1
        )
        session.add(c1)
        session.add(c2)
        session.flush()
        ib_id = ib.id
        
    monkeypatch.setattr("backend.scheduler.remove_client_api", lambda *a: True)
    monkeypatch.setattr("backend.scheduler.kick_client_hysteria_api", lambda *a: True)
    monkeypatch.setattr("backend.scheduler.write_xray_config", lambda *a: None)
    monkeypatch.setattr("backend.scheduler.restart_hysteria", lambda *a: None)
    
    enforce_client_limits_and_rules()
    
    with db_session() as session:
        c1_db = session.query(ClientStats).filter_by(inbound_id=ib_id, email="traffic_exceeded@mail.com").first()
        c2_db = session.query(ClientStats).filter_by(inbound_id=ib_id, email="traffic_ok@mail.com").first()
        
        assert c1_db.enable == 0
        assert c1_db.block_reason == "Лимит трафика исчерпан"
        assert c2_db.enable == 1
        
        session.delete(c1_db)
        session.delete(c2_db)
        ib_obj = session.query(Inbound).filter_by(id=ib_id).first()
        session.delete(ib_obj)


def test_ip_limit_enforcement(monkeypatch):
    """Test background limits checker blocks clients on concurrent IP limit."""
    with db_session() as session:
        ib = Inbound(remark="IP Limit Inbound", port=60081, protocol="vless", enable=1)
        session.add(ib)
        session.flush()
        
        c = ClientStats(
            inbound_id=ib.id,
            email="ip_exceeded@mail.com",
            client_uuid_or_pwd="pass_ip",
            up=0,
            down=0,
            total=0,
            limit_ip=2,
            enable=1
        )
        session.add(c)
        session.flush()
        ib_id = ib.id
        
    now_ts = time.time()
    ACTIVE_IP_CACHE["ip_exceeded@mail.com"] = {
        "1.1.1.1": now_ts,
        "2.2.2.2": now_ts,
        "3.3.3.3": now_ts
    }
    
    monkeypatch.setattr("backend.scheduler.remove_client_api", lambda *a: True)
    monkeypatch.setattr("backend.scheduler.kick_client_hysteria_api", lambda *a: True)
    monkeypatch.setattr("backend.scheduler.write_xray_config", lambda *a: None)
    monkeypatch.setattr("backend.scheduler.restart_hysteria", lambda *a: None)
    monkeypatch.setattr("backend.scheduler.parse_recent_xray_ips", lambda: None)
    
    enforce_client_limits_and_rules()
    
    with db_session() as session:
        c_db = session.query(ClientStats).filter_by(inbound_id=ib_id, email="ip_exceeded@mail.com").first()
        assert c_db.enable == 0
        assert "Превышен лимит IP" in c_db.block_reason
        
        session.delete(c_db)
        ib_obj = session.query(Inbound).filter_by(id=ib_id).first()
        session.delete(ib_obj)


def test_daily_traffic_scheduler(client, monkeypatch):
    """Test daily traffic delta aggregation scheduler."""
    with db_session() as session:
        # Clear daily traffic table
        session.query(ClientTrafficDaily).delete()
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        
        # Create Inbound
        ib = Inbound(remark="test_ib", port=4433, protocol="vless", settings="{}")
        session.add(ib)
        session.flush()
        
        # Create client with stats
        c = ClientStats(
            inbound_id=ib.id,
            email="traffic_test@test.com",
            client_uuid_or_pwd="uuid-traffic",
            up=1000,
            down=2000,
            last_seen_up=0,
            last_seen_down=0,
            enable=1
        )
        session.add(c)
        
    # Run scheduler to aggregate traffic delta
    enforce_client_limits_and_rules()
    
    with db_session() as session:
        # Check ClientTrafficDaily has new record
        today = datetime.date.today().isoformat()
        daily = session.query(ClientTrafficDaily).filter_by(email="traffic_test@test.com", date=today).first()
        assert daily is not None
        assert daily.up == 1000
        assert daily.down == 2000
        
        # Verify client's last_seen is updated
        c_db = session.query(ClientStats).filter_by(email="traffic_test@test.com").first()
        assert c_db.last_seen_up == 1000
        assert c_db.last_seen_down == 2000
        
        # Simulate traffic increment
        c_db.up = 1500
        c_db.down = 2500
        
    # Run scheduler again
    enforce_client_limits_and_rules()
    
    with db_session() as session:
        daily = session.query(ClientTrafficDaily).filter_by(email="traffic_test@test.com", date=today).first()
        assert daily.up == 1500
        assert daily.down == 2500

    # Test API endpoint /api/clients/{email}/traffic
    import backend.routes.clients
    monkeypatch.setattr(backend.routes.clients, "check_auth", lambda r: True)
    response = client.get("/api/clients/traffic_test@test.com/traffic")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert len(res_data["obj"]) == 1
    assert res_data["obj"][0]["up"] == 1500
