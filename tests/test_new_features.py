import pytest
import backend.watchdog_state
from backend.database import db_session, set_setting, get_setting
from backend.models import Inbound, ClientStats
from backend.scheduler import run_service_watchdog
from backend.watchdog_state import reset_xray_watchdog, reset_hysteria_watchdog

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

def test_watchdog_restart_behavior(monkeypatch):
    """Test that watchdog attempts to restart core service when it is dead and active inbounds exist."""
    # Reset watchdog counters
    backend.watchdog_state.reset_xray_watchdog()
    backend.watchdog_state.reset_hysteria_watchdog()
    
    # 1. Create active xray inbound in the db
    with db_session() as session:
        # Clear existing to be sure
        session.query(Inbound).delete()
        ib = Inbound(
            remark="Watchdog test inbound",
            port=31244,
            protocol="vless",
            settings="{}",
            stream_settings="{}",
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.commit()

    # 2. Mock state and functions
    monkeypatch.setattr("backend.scheduler.is_xray_running", lambda: False)
    
    restarts_called = 0
    def mock_restart_xray():
        nonlocal restarts_called
        restarts_called += 1
        
    monkeypatch.setattr("backend.scheduler.restart_xray", mock_restart_xray)
    
    # 3. Trigger watchdog
    run_service_watchdog()
    assert restarts_called == 1
    assert backend.watchdog_state.consecutive_xray_restarts == 1

    # 4. Trigger again, should call restart again
    run_service_watchdog()
    assert restarts_called == 2
    assert backend.watchdog_state.consecutive_xray_restarts == 2

    # 5. Trigger again, should call restart again (restarts_called = 3, counter = 3)
    run_service_watchdog()
    assert restarts_called == 3
    assert backend.watchdog_state.consecutive_xray_restarts == 3

    # 6. Trigger again, should NOT call restart (max 3 consecutive attempts)
    run_service_watchdog()
    assert restarts_called == 3
    assert backend.watchdog_state.consecutive_xray_restarts == 3

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
    
    # 1. Enable blocking settings
    set_setting("block_bittorrent", "true")
    set_setting("block_ads", "true")
    set_setting("block_cn", "true")
    set_setting("block_ru", "false")
    set_setting("block_us", "true")
    
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
        country_rule = next((r for r in rules if any("cn" in ip for ip in r.get("ip", []))), None)
        assert country_rule is not None
        assert country_rule["outboundTag"] == "blocked"
        assert "geoip:cn" in country_rule["ip"]
        assert "geoip:us" in country_rule["ip"]
        assert "geoip:ru" not in country_rule["ip"]
        
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
    """Test client connection and disconnection log parsing and inactivity timeouts."""
    from backend.client_alerts import (
        process_xray_log_line,
        process_hysteria_log_line,
        check_xray_inactivity_timeouts,
        active_xray_sessions
    )
    from backend.models import AuditLog
    from backend.database import db_session
    import json
    import time

    # Clear state and database
    active_xray_sessions.clear()
    with db_session() as session:
        session.query(AuditLog).delete()
        session.commit()

    # 1. Test Xray log line parsing (connection)
    xray_log_line = "2026/06/13 03:00:00 [Info] accepted connection from 198.51.100.1:54321 email: test_user@example.com"
    process_xray_log_line(xray_log_line)

    with db_session() as session:
        logs = session.query(AuditLog).all()
        assert len(logs) == 1
        assert logs[0].action == "xray_connect"
        assert logs[0].target == "198.51.100.1"
        details = json.loads(logs[0].details)
        assert details["username"] == "test_user@example.com"

    # Call again with same connection, should NOT produce duplicate event
    process_xray_log_line(xray_log_line)
    with db_session() as session:
        logs = session.query(AuditLog).all()
        assert len(logs) == 1

    # 2. Test Xray inactivity timeout
    key = ("test_user@example.com", "198.51.100.1")
    assert key in active_xray_sessions
    # Force last seen time to be 4 minutes ago
    active_xray_sessions[key]["last_seen_at"] = time.time() - 240
    # Force started_at
    active_xray_sessions[key]["started_at"] = time.time() - 300

    check_xray_inactivity_timeouts()

    assert key not in active_xray_sessions
    with db_session() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.asc()).all()
        assert len(logs) == 2
        assert logs[1].action == "xray_disconnect"
        assert logs[1].target == "198.51.100.1"
        details = json.loads(logs[1].details)
        assert details["username"] == "test_user@example.com"
        assert "duration" in details

    # 3. Test Hysteria 2 connection log parsing
    hysteria_connect_line = '2026-06-13T03:00:00.000Z INFO client connected {"id": "test_hysteria_user", "addr": "198.51.100.1:1234"}'
    process_hysteria_log_line(hysteria_connect_line)

    with db_session() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.asc()).all()
        assert len(logs) == 3
        assert logs[2].action == "hysteria_connect"
        assert logs[2].target == "198.51.100.1"
        details = json.loads(logs[2].details)
        assert details["username"] == "test_hysteria_user"

    # 3b. Test Hysteria 2 IPv6 connection log parsing
    hysteria_connect_line_ipv6 = '2026-06-13T03:01:00.000Z INFO client connected {"id": "test_hysteria_user", "addr": "[2001:db8::1]:1234"}'
    process_hysteria_log_line(hysteria_connect_line_ipv6)

    with db_session() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.asc()).all()
        assert len(logs) == 4
        assert logs[3].action == "hysteria_connect"
        assert logs[3].target == "2001:db8::1"
        details = json.loads(logs[3].details)
        assert details["username"] == "test_hysteria_user"

    # 4. Test Hysteria 2 disconnection log parsing
    hysteria_disconnect_line = '2026-06-13T03:05:00.000Z INFO client disconnected {"id": "test_hysteria_user", "addr": "[2001:db8::1]:1234"}'
    process_hysteria_log_line(hysteria_disconnect_line)

    with db_session() as session:
        logs = session.query(AuditLog).order_by(AuditLog.id.asc()).all()
        assert len(logs) == 5
        assert logs[4].action == "hysteria_disconnect"
        assert logs[4].target == "2001:db8::1"
        details = json.loads(logs[4].details)
        assert details["username"] == "test_hysteria_user"


def test_new_ip_security_alerts():
    """Test new IP detection logic using simulated audit logs."""
    from backend.telegram_alerts import check_new_ip_and_get_history

    # Mock logs (descending order by timestamp)
    mock_logs = [
        {"timestamp": 100, "username": "system", "action": "xray_connect", "target": "192.168.1.1", "details": '{"username": "svatex", "tx": 100, "rx": 100}'},
        {"timestamp": 90, "username": "system", "action": "xray_disconnect", "target": "192.168.1.2", "details": '{"username": "svatex", "duration": "50 сек"}'},
        {"timestamp": 50, "username": "system", "action": "xray_connect", "target": "192.168.1.2", "details": '{"username": "svatex"}'},
        {"timestamp": 40, "username": "system", "action": "xray_connect", "target": "10.0.0.1", "details": '{"username": "other_user"}'},
    ]

    # Current connection from 192.168.1.1 at t=100.
    # The previous connection for svatex was from 192.168.1.2 at t=50.
    # So 192.168.1.1 is indeed a new IP!
    is_new_ip, history = check_new_ip_and_get_history(
        username="svatex",
        current_ip="192.168.1.1",
        current_timestamp=100,
        logs=mock_logs
    )

    assert is_new_ip is True
    assert len(history) == 1
    assert history[0]["ip"] == "192.168.1.2"
    assert history[0]["duration"] == "50 сек"

    # Current connection from 192.168.1.2 at t=100.
    # The previous connection was also from 192.168.1.2.
    # So 192.168.1.2 is NOT a new IP!
    is_new_ip, history = check_new_ip_and_get_history(
        username="svatex",
        current_ip="192.168.1.2",
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
    """Test that process_xray_log_line parses different log formats correctly."""
    from backend.client_alerts import process_xray_log_line, active_xray_sessions
    
    # Mock log_action to verify connection registration
    logged_actions = []
    def mock_log_action(username, action, target, details):
        logged_actions.append({
            "username": username,
            "action": action,
            "target": target,
            "details": details
        })
    monkeypatch.setattr("backend.client_alerts.log_action", mock_log_action)
    
    # Mock database traffic lookup
    monkeypatch.setattr("backend.client_alerts.get_xray_user_traffic", lambda email: (100, 200))
    
    # Reset session state
    active_xray_sessions.clear()
    
    # 1. Test new log line format (IPv4)
    line_new = "2026/06/13 14:55:36.505111 from 192.168.1.50:40020 accepted tcp:mozilla.cloudflare-dns.com:443 [inbound-2 >> direct] email: phone"
    process_xray_log_line(line_new)
    assert len(logged_actions) == 1
    assert logged_actions[0]["action"] == "xray_connect"
    assert logged_actions[0]["target"] == "192.168.1.50"
    assert "test_client" in logged_actions[0]["details"]
    
    # 2. Test new log line format (IPv6)
    logged_actions.clear()
    line_new_ipv6 = "2026/06/13 14:55:38.571331 from [2001:db8::1]:40084 accepted tcp:[2001:67c:4e8:f004::a]:443 [inbound-2 >> direct] email: phone2"
    process_xray_log_line(line_new_ipv6)
    assert len(logged_actions) == 1
    assert logged_actions[0]["action"] == "xray_connect"
    assert logged_actions[0]["target"] == "2001:db8::1"
    assert "phone2" in logged_actions[0]["details"]



