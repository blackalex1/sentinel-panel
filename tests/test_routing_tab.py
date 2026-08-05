from backend.database import get_all_outbounds, get_all_routing_rules, add_outbound, get_outbound_by_id, delete_outbound, add_routing_rule, get_routing_rule_by_id, delete_routing_rule

def test_routing_tab_features(client):
    """Test custom outbounds, routing rules, config builder integration, and API routes."""
    # 1. Verify default outbounds and rules seeded
    outbounds = get_all_outbounds()
    rules = get_all_routing_rules()
    
    assert len(outbounds) >= 2  # direct, blocked
    
    # Verify Direct (Freedom) exists
    direct_ob = next((ob for ob in outbounds if ob["tag"] == "direct"), None)
    assert direct_ob is not None
    assert direct_ob["protocol"] == "freedom"
    assert direct_ob["is_system"] == 1
    
    # 2. Test Outbounds Database CRUD
    ob_id = add_outbound(remark="Test SOCKS", protocol="socks", tag="test-socks", settings_dict={"servers": [{"address": "1.1.1.1", "port": 1080}]})
    assert ob_id is not None
    
    ob = get_outbound_by_id(ob_id)
    assert ob["remark"] == "Test SOCKS"
    assert ob["tag"] == "test-socks"
    
    # Try deleting system outbound (should fail)
    assert delete_outbound(direct_ob["id"]) is False
    
    # 3. Test Routing Rules Database CRUD
    rule_id = add_routing_rule(remark="Test Rule", outbound_tag="test-socks", domains=["domain:google.com"], ips=["8.8.8.8"])
    assert rule_id is not None
    
    rule = get_routing_rule_by_id(rule_id)
    assert rule["remark"] == "Test Rule"
    assert rule["outbound_tag"] == "test-socks"
    assert "domain:google.com" in rule["domains"]
    
    # 4. Test API routing endpoints
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # Get outbounds
    response = client.get("/api/routing/outbounds", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Create custom outbound
    payload = {
        "remark": "My Custom SOCKS",
        "protocol": "socks",
        "tag": "my-custom-socks",
        "settings": {"servers": [{"address": "2.2.2.2", "port": 1080}]},
        "enable": 1
    }
    response = client.post("/api/routing/outbounds/create", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    new_ob_id = response.json()["id"]
    
    # Delete custom outbound
    response = client.post(f"/api/routing/outbounds/delete/{new_ob_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Create custom routing rule
    rule_payload = {
        "remark": "My Custom Rule",
        "outbound_tag": "direct",
        "domains": ["geosite:google"],
        "users": ["client@example.com"],
        "enable": 1
    }
    response = client.post("/api/routing/rules/create", json=rule_payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    new_rule_id = response.json()["id"]
    
    rule = get_routing_rule_by_id(new_rule_id)
    assert rule["users"] == ["client@example.com"]
    
    # Check Xray configuration includes user
    from backend.xray import generate_xray_config_json
    xray_config = generate_xray_config_json()
    rule_found = next((r for r in xray_config["routing"]["rules"] if r.get("outboundTag") == "direct" and "geosite:google" in r.get("domain", [])), None)
    assert rule_found is not None
    assert rule_found["user"] == ["client@example.com"]
    
    # Update sorting order
    response = client.post("/api/routing/rules/sort", json={"rule_ids": [new_rule_id, rule_id]}, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Clean up DB
    delete_routing_rule(rule_id)
    delete_routing_rule(new_rule_id)
    delete_outbound(ob_id)


def test_outbound_new_features(client, monkeypatch):
    """Test outbound traffic tracking, gRPC stats delta integration, and test endpoints."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Test outbound traffic increment helper in crud/outbounds
    from backend.database import add_outbound, get_outbound_by_id, update_outbound_traffic, delete_outbound
    ob_id = add_outbound(
        remark="Traffic Test SOCKS",
        protocol="socks",
        tag="traffic-socks",
        settings_dict={"servers": [{"address": "1.1.1.1", "port": 1080}]}
    )
    assert ob_id is not None
    
    # Initial traffic should be 0
    ob = get_outbound_by_id(ob_id)
    assert ob["up"] == 0
    assert ob["down"] == 0
    
    # Update traffic
    update_outbound_traffic("traffic-socks", 1000, 2000)
    ob = get_outbound_by_id(ob_id)
    assert ob["up"] == 1000
    assert ob["down"] == 2000
    
    # 2. Test integration with process_stats_deltas
    from backend.xray.service import process_stats_deltas, _last_session_stats
    _last_session_stats.clear() # clear mock session stats
    
    stats_list = [
        {"name": "outbound>>>traffic-socks>>>traffic>>>uplink", "value": "1500"},
        {"name": "outbound>>>traffic-socks>>>traffic>>>downlink", "value": "3500"}
    ]
    process_stats_deltas(stats_list)
    
    ob = get_outbound_by_id(ob_id)
    # 1000 + 1500 = 2500, 2000 + 3500 = 5500
    assert ob["up"] == 2500
    assert ob["down"] == 5500
    
    # 3. Test outbound test endpoint (TCP mock)
    # Mock tcp_ping in backend.routes.routing
    monkeypatch.setattr("backend.routes.routing.tcp_ping", lambda host, port: {"success": True, "ping": 12.34})
    
    payload = {
        "protocol": "socks",
        "settings": {"servers": [{"address": "1.1.1.1", "port": 1080}]},
        "test_type": "tcp"
    }
    response = client.post("/api/routing/outbounds/test", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ping"] == 12.34
    
    # 4. Test outbound test endpoint (HTTP mock)
    monkeypatch.setattr(
        "backend.routes.routing.test_outbound_transit",
        lambda protocol, settings, stream_settings=None: {"success": True, "ping": 56.78}
    )
    
    payload["test_type"] = "http"
    response = client.post("/api/routing/outbounds/test", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ping"] == 56.78
    
    # 5. Test outbound test by id endpoint
    response = client.post(f"/api/routing/outbounds/test/{ob_id}?test_type=tcp", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ping"] == 12.34
    
    response = client.post(f"/api/routing/outbounds/test/{ob_id}?test_type=http", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["ping"] == 56.78
    
    # Clean up
    delete_outbound(ob_id)


def test_cascade_delete_inbound_and_outbound_safety():
    """Test that deleting an inbound or outbound cleans up matching orphan rules selectively while leaving unrelated entities untouched."""
    from backend.database import add_inbound, delete_inbound, add_outbound, delete_outbound, add_routing_rule, get_routing_rule_by_id, get_all_inbounds, get_all_outbounds, get_all_routing_rules

    # 1. Create Inbound A (id A) and Inbound B (id B)
    ib_a_id = add_inbound(remark="Inbound A", port=59001, protocol="vless", settings_dict={})
    ib_b_id = add_inbound(remark="Inbound B", port=59002, protocol="vless", settings_dict={})
    assert ib_a_id is not None
    assert ib_b_id is not None

    tag_a = f"inbound-{ib_a_id}"
    tag_b = f"inbound-{ib_b_id}"

    # 2. Create Outbound X and Outbound Y
    ob_x_id = add_outbound(remark="Outbound X", protocol="socks", tag="out-x", settings_dict={"servers": [{"address": "1.1.1.1", "port": 1080}]})
    ob_y_id = add_outbound(remark="Outbound Y", protocol="socks", tag="out-y", settings_dict={"servers": [{"address": "2.2.2.2", "port": 1080}]})
    assert ob_x_id is not None
    assert ob_y_id is not None

    # 3. Create Routing Rules
    # Rule 1: Inbound A only -> Outbound X
    r1_id = add_routing_rule(remark="Rule A->X", outbound_tag="out-x", inbound_tags=[tag_a], domains=["domain:a.com"])
    # Rule 2: Shared Inbound A & B -> Outbound Y
    r2_id = add_routing_rule(remark="Rule A&B->Y", outbound_tag="out-y", inbound_tags=[tag_a, tag_b], domains=["domain:ab.com"])
    # Rule 3: Inbound B only -> Outbound Y
    r3_id = add_routing_rule(remark="Rule B->Y", outbound_tag="out-y", inbound_tags=[tag_b], domains=["domain:b.com"])

    # Verify initial creation
    assert get_routing_rule_by_id(r1_id) is not None
    assert get_routing_rule_by_id(r2_id) is not None
    assert get_routing_rule_by_id(r3_id) is not None

    # 4. Delete Inbound A
    assert delete_inbound(ib_a_id) is True

    # Assertions for Inbound A deletion:
    # - Inbound A is deleted from inbounds list
    inbound_ids = [ib["id"] for ib in get_all_inbounds()]
    assert ib_a_id not in inbound_ids
    # - Inbound B STILL EXISTS! (Nothing extra deleted!)
    assert ib_b_id in inbound_ids

    # - Rule 1 (specific ONLY to Inbound A) IS DELETED
    assert get_routing_rule_by_id(r1_id) is None

    # - Rule 2 (shared A & B) IS PRESERVED, with Inbound A removed and Inbound B kept!
    r2_updated = get_routing_rule_by_id(r2_id)
    assert r2_updated is not None
    assert r2_updated["inbound_tags"] == [tag_b]

    # - Rule 3 (specific ONLY to Inbound B) IS 100% UNTOUCHED
    r3_check = get_routing_rule_by_id(r3_id)
    assert r3_check is not None
    assert r3_check["inbound_tags"] == [tag_b]

    # 5. Delete Outbound Y
    assert delete_outbound(ob_y_id) is True

    # Assertions for Outbound Y deletion:
    # - Outbound Y is deleted from outbounds list
    outbound_ids = [ob["id"] for ob in get_all_outbounds()]
    assert ob_y_id not in outbound_ids
    # - Outbound X STILL EXISTS! (Nothing extra deleted!)
    assert ob_x_id in outbound_ids

    # - Rule 2 and Rule 3 (pointing to Outbound Y) ARE DELETED
    assert get_routing_rule_by_id(r2_id) is None
    assert get_routing_rule_by_id(r3_id) is None

    # Clean up remaining entities
    delete_outbound(ob_x_id)
    delete_inbound(ib_b_id)


def test_outbound_failover_backup_system(client):
    """Test outbound backup failover system across Xray (observatory/balancer) and Sing-box (urltest)."""
    from backend.database import add_outbound, delete_outbound, add_routing_rule, delete_routing_rule, get_outbound_by_id
    from backend.xray import generate_xray_config_json
    from backend.singbox.outbounds import generate_singbox_outbounds

    # 1. Create Backup Outbound B
    ob_b_id = add_outbound(
        remark="Backup VPS B",
        protocol="socks",
        tag="vps-b",
        settings_dict={"servers": [{"address": "2.2.2.2", "port": 1080}]}
    )
    assert ob_b_id is not None

    # 2. Create Primary Outbound A with backup_outbounds = ["vps-b", "direct"]
    ob_a_id = add_outbound(
        remark="Primary VPS A",
        protocol="vless",
        tag="vps-a",
        settings_dict={
            "vnext": [{"address": "1.1.1.1", "port": 443, "users": [{"id": "uuid-a"}]}],
            "backup_outbounds": ["vps-b", "direct"],
            "health_check_url": "https://www.gstatic.com/generate_204",
            "health_check_interval": 15
        }
    )
    assert ob_a_id is not None

    # 3. Create Routing Rule for Primary Outbound A
    rule_id = add_routing_rule(
        remark="Route to VPS A",
        outbound_tag="vps-a",
        domains=["domain:google.com"]
    )
    assert rule_id is not None

    # 4. Verify Xray Config Generation
    xray_cfg = generate_xray_config_json()
    assert "observatory" in xray_cfg
    assert set(xray_cfg["observatory"]["subjectSelector"]) == {"vps-a", "vps-b", "direct"}
    assert xray_cfg["observatory"]["probeUrl"] == "https://www.gstatic.com/generate_204"

    assert "balancers" in xray_cfg["routing"]
    balancer = next((b for b in xray_cfg["routing"]["balancers"] if b["tag"] == "balancer-vps-a"), None)
    assert balancer is not None
    assert balancer["selector"] == ["vps-a"]
    assert balancer["fallbackTag"] == "vps-b"
    assert balancer["strategy"] == {"type": "leastPing"}

    # Verify rule transformed outboundTag -> balancerTag
    rule_found = next((r for r in xray_cfg["routing"]["rules"] if r.get("balancerTag") == "balancer-vps-a"), None)
    assert rule_found is not None
    assert "domain:google.com" in rule_found["domain"]

    # 5. Verify Sing-box Config Generation
    sb_outbounds = generate_singbox_outbounds()
    sb_primary = next((ob for ob in sb_outbounds if ob["tag"] == "vps-a-primary"), None)
    assert sb_primary is not None
    assert sb_primary["type"] == "vless"

    sb_urltest = next((ob for ob in sb_outbounds if ob["tag"] == "vps-a"), None)
    assert sb_urltest is not None
    assert sb_urltest["type"] == "urltest"
    assert sb_urltest["outbounds"] == ["vps-a-primary", "vps-b", "direct"]
    assert sb_urltest["url"] == "https://www.gstatic.com/generate_204"
    assert sb_urltest["tolerance"] in (0, 500)

    # 6. Test Cascade Deletion of Backup Outbound B
    delete_outbound(ob_b_id)

    ob_a_updated = get_outbound_by_id(ob_a_id)
    import json
    settings_a = json.loads(ob_a_updated["settings"])
    assert "vps-b" not in settings_a["backup_outbounds"]
    assert settings_a["backup_outbounds"] == ["direct"]

    # Cleanup
    delete_routing_rule(rule_id)
    delete_outbound(ob_a_id)



