import pytest
from backend.database import db_session, set_setting, get_setting
from backend.models import Inbound, ClientStats

def test_free_port_selection(client):
    """Test that free port API successfully searches and returns a free port."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.get("/api/system/free-port", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert 20000 <= data["port"] <= 65535

def test_backup_settings_update(client):
    """Test that settings GET and POST API endpoints support backup options."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Update settings with backup options
    payload = {
        "backup_enable": True,
        "backup_interval": "hourly",
        "backup_rotation": 5,
        "backup_telegram": True
    }
    response = client.post("/api/settings/update", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 2. Get settings and verify
    response = client.get("/api/settings", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["backup_enable"] is True
    assert data["backup_interval"] == "hourly"
    assert data["backup_rotation"] == 5
    assert data["backup_telegram"] is True

def test_global_traffic_history_endpoint(client):
    """Test global traffic history API endpoint."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.get("/panel/api/system/global-traffic", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["obj"]) == 30

def test_acme_challenge_endpoint(client):
    """Test the ACME HTTP-01 challenge response route."""
    from backend.acme_client import ACME_CHALLENGES
    
    token = "test-acme-token-123"
    auth_val = "test-key-authorization-xyz"
    
    ACME_CHALLENGES[token] = auth_val
    try:
        # Request non-existing token
        resp_404 = client.get("/.well-known/acme-challenge/non-existent-token")
        assert resp_404.status_code == 404
        
        # Request existing token
        resp_200 = client.get(f"/.well-known/acme-challenge/{token}")
        assert resp_200.status_code == 200
        assert resp_200.text == auth_val
        assert resp_200.headers["content-type"].startswith("text/plain")
    finally:
        ACME_CHALLENGES.pop(token, None)


def test_quick_block_rules_injection():
    """Test that quick blocking rules are successfully injected into Xray config."""
    from backend.xray.config import generate_xray_config_json
    from backend.database import set_setting
    
    from backend.database import sync_quick_security_rules
    sync_quick_security_rules({
        "block_bittorrent": "true",
        "block_ads": "true",
        "block_cn": "true",
        "block_ru": "false",
        "block_us": "true"
    })
    
    try:
        config = generate_xray_config_json()
        routing = config.get("routing", {})
        rules = routing.get("rules", [])
        
        # Verify bittorrent blocks
        bt_proto_rule = next((r for r in rules if r.get("protocol") == ["bittorrent"]), None)
        assert bt_proto_rule is not None
        assert bt_proto_rule["outboundTag"] == "blocked"
        
        bt_domain_rule = next((r for r in rules if any("torrent" in d for d in r.get("domain", []))), None)
        assert bt_domain_rule is not None
        assert bt_domain_rule["outboundTag"] == "blocked"
        
        # Verify ads block
        ads_rule = next((r for r in rules if "geosite:category-ads-all" in r.get("domain", [])), None)
        assert ads_rule is not None
        assert ads_rule["outboundTag"] == "blocked"
        
        # Verify country blocks (cn, us enabled; ru disabled)
        cn_rule = next((r for r in rules if "geoip:cn" in r.get("ip", [])), None)
        assert cn_rule is not None
        assert cn_rule["outboundTag"] == "blocked"

        us_rule = next((r for r in rules if "geoip:us" in r.get("ip", [])), None)
        assert us_rule is not None
        assert us_rule["outboundTag"] == "blocked"

        ru_rule = next((r for r in rules if "geoip:ru" in r.get("ip", [])), None)
        assert ru_rule is None or ru_rule.get("enable") == 0
        
    finally:
        # Reset settings
        set_setting("block_bittorrent", "false")
        set_setting("block_ads", "false")
        set_setting("block_cn", "false")
        set_setting("block_ru", "false")
        set_setting("block_us", "false")


def test_warp_registration_mock(client, monkeypatch):
    """Test the WARP outbound generation endpoint."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # Mock register_warp helper
    mock_warp_data = {
        "private_key": "mock_priv_key",
        "public_key": "mock_pub_key",
        "address_v4": "172.16.0.2/32",
        "address_v6": "2606:4700::1/128",
        "peer_public_key": "mock_peer_pub_key",
        "endpoint": "engage.cloudflareclient.com:2408",
        "reserved": [1, 2, 3]
    }
    
    monkeypatch.setattr("backend.utils.warp.register_warp", lambda: mock_warp_data)
    
    response = client.post("/api/routing/outbounds/generate-warp", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["obj"] == mock_warp_data




def test_client_alerts_logging(monkeypatch):
    """Test client alert helpers and audit logging."""
    from backend.client_alerts import (
        get_singbox_user_traffic,
        get_xray_user_traffic,
        parse_ip_from_addr
    )
    from backend.models import AuditLog
    from backend.database import db_session
    from backend.audit import log_action
    import json

    # 1. Test IP address parsing
    assert parse_ip_from_addr("198.51.100.1:54321") == "198.51.100.1"
    assert parse_ip_from_addr("[2001:db8::1]:1234") == "2001:db8::1"
    assert parse_ip_from_addr("203.0.113.5") == "203.0.113.5"

    # 2. Test audit log creation
    with db_session() as session:
        session.query(AuditLog).delete()
        session.commit()

    log_action(username="system", action="singbox_connect", target="198.51.100.1", details=json.dumps({"username": "test_user"}))

    with db_session() as session:
        logs = session.query(AuditLog).all()
        assert len(logs) == 1
        assert logs[0].action == "singbox_connect"
        assert logs[0].target == "198.51.100.1"
        details = json.loads(logs[0].details)
        assert details["username"] == "test_user"


def test_new_ip_security_alerts():
    """Test new IP detection logic using simulated audit logs."""
    from backend.telegram_alerts import check_new_ip_and_get_history

    # Mock logs (descending order by timestamp)
    mock_logs = [
        {"timestamp": 100, "username": "system", "action": "xray_connect", "target": "198.51.100.1", "details": '{"username": "client_user_1", "tx": 100, "rx": 100}'},
        {"timestamp": 90, "username": "system", "action": "xray_disconnect", "target": "198.51.100.2", "details": '{"username": "client_user_1", "duration": "50 сек"}'},
        {"timestamp": 50, "username": "system", "action": "xray_connect", "target": "198.51.100.2", "details": '{"username": "client_user_1"}'},
        {"timestamp": 40, "username": "system", "action": "xray_connect", "target": "203.0.113.1", "details": '{"username": "other_user"}'},
    ]

    # Current connection from 198.51.100.1 at t=100.
    # The previous connection for client_user_1 was from 198.51.100.2 at t=50.
    # So 198.51.100.1 is indeed a new IP!
    is_new_ip, history = check_new_ip_and_get_history(
        username="client_user_1",
        current_ip="198.51.100.1",
        current_timestamp=100,
        logs=mock_logs
    )

    assert is_new_ip is True
    assert len(history) == 1
    assert history[0]["ip"] == "198.51.100.2"
    assert history[0]["duration"] == "50 сек"

    # Current connection from 198.51.100.2 at t=100.
    # The previous connection was also from 198.51.100.2.
    # So 198.51.100.2 is NOT a new IP!
    is_new_ip, history = check_new_ip_and_get_history(
        username="client_user_1",
        current_ip="198.51.100.2",
        current_timestamp=100,
        logs=mock_logs
    )
    assert is_new_ip is False
    assert len(history) == 1


def test_auto_trim_emails():
    """Test that startup database trim migration automatically strips client emails."""
    from backend.database.seeding import init_db
    from backend.models import Inbound, ClientStats
    import json
    
    with db_session() as session:
        # Create an inbound with a trailing space in settings JSON
        ib = Inbound(
            remark="Trim test inbound",
            port=31999,
            protocol="vless",
            settings=json.dumps({"clients": [{"email": "bad_email ", "id": "uuid-1234"}]}),
            stream_settings="{}",
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.flush()
        
        # Create a client stat with leading space
        cl = ClientStats(
            inbound_id=ib.id,
            email=" bad_email",
            client_uuid_or_pwd="uuid-1234",
            enable=1
        )
        session.add(cl)
        session.commit()
        
        ib_id = ib.id
        cl_id = cl.id
        
    # Run init_db to invoke auto-trim migration
    init_db()
    
    # Query again from the DB in a fresh session to verify
    with db_session() as session2:
        db_ib = session2.query(Inbound).filter_by(id=ib_id).first()
        db_cl = session2.query(ClientStats).filter_by(id=cl_id).first()
        
        # Verify
        assert db_cl.email == "bad_email"
        settings_dict = json.loads(db_ib.settings)
        assert settings_dict["clients"][0]["email"] == "bad_email"
        
        # Clean up
        session2.delete(db_cl)
        session2.delete(db_ib)
        session2.commit()


def test_rename_client_and_uuid():
    """Test that update_client_db successfully updates both the email and the UUID/password."""
    from backend.database.crud.clients import update_client_db
    from backend.models import Inbound, ClientStats
    import json
    
    with db_session() as session:
        ib = Inbound(
            remark="Rename test inbound",
            port=31998,
            protocol="vless",
            settings=json.dumps({"clients": [{"email": "old_name", "id": "old-uuid"}]}),
            stream_settings="{}",
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.flush()
        
        cl = ClientStats(
            inbound_id=ib.id,
            email="old_name",
            client_uuid_or_pwd="old-uuid",
            enable=1
        )
        session.add(cl)
        session.commit()
        
        ib_id = ib.id
        cl_id = cl.id
        
    # Perform update changing both name and UUID
    success = update_client_db(
        inbound_id=ib_id,
        old_email="old_name",
        new_email="new_name",
        client_uuid_or_pwd="new-uuid",
        enable=1
    )
    assert success is True
    
    # Verify in a fresh session
    with db_session() as session2:
        db_ib = session2.query(Inbound).filter_by(id=ib_id).first()
        db_cl = session2.query(ClientStats).filter_by(id=cl_id).first()
        
        assert db_cl.email == "new_name"
        assert db_cl.client_uuid_or_pwd == "new-uuid"
        
        # Clean up
        session2.delete(db_cl)
        session2.delete(db_ib)
        session2.commit()


def test_xray_log_parsing_alert(monkeypatch):
    """Test parse_ip_from_addr and audit log format."""
    from backend.client_alerts import parse_ip_from_addr
    
    assert parse_ip_from_addr("192.168.1.50:40020") == "192.168.1.50"
    assert parse_ip_from_addr("[2001:db8::1]:40084") == "2001:db8::1"




