import time
import json
import hashlib
import hmac
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ed25519

from backend.database import db_session
from backend.models import Node, NodeJoinCode, ClientStats
from backend.auth_utils import verify_node_token, decoy_response
from backend.node_agent import load_node_config, save_node_config, generate_keypair, sign_payload, register_with_master, send_report_to_master, auto_investigate_and_resolve

def test_nodes_lifecycle_and_stealth(client, monkeypatch):
    """Test the complete Nodes lifecycle: Join Code, Registration, Decoy Masking, and Signed Reporting."""
    
    # 1. Test Admin Authentication bypass for join-code generation
    # When not logged in/unauthorized, should return Nginx 404 decoy response
    import backend.routes.nodes
    monkeypatch.setattr(backend.routes.nodes, "check_auth", lambda r: False)
    
    response = client.post("/api/nodes/join-code")
    assert response.status_code == 404
    assert "nginx" in response.text.lower()
    
    # Authorize admin for the next tests
    monkeypatch.setattr(backend.routes.nodes, "check_auth", lambda r: True)
    
    # 2. Generate a Join Code
    response = client.post("/api/nodes/join-code")
    assert response.status_code == 200
    join_data = response.json()
    assert "code" in join_data
    join_code = join_data["code"]
    
    # 3. Test Decoy masking on registration with invalid Join Code
    response = client.post("/api/nodes/register", json={
        "join_code": "INVALID-CODE",
        "public_key": "some_pubkey_hex"
    })
    assert response.status_code == 404
    assert "nginx" in response.text.lower()
    
    # 4. Register node using valid Join Code and locally generated Ed25519 keys
    node_pub, node_priv = generate_keypair()
    
    response = client.post("/api/nodes/register", json={
        "join_code": join_code,
        "public_key": node_pub
    })
    assert response.status_code == 200
    reg_data = response.json()
    assert "node_id" in reg_data
    assert "node_api_token" in reg_data
    assert "master_public_key" in reg_data
    
    node_id = reg_data["node_id"]
    node_token = reg_data["node_api_token"]
    master_pub = reg_data["master_public_key"]
    
    # Verify node is in database and status is active
    with db_session() as session:
        db_node = session.query(Node).filter_by(id=node_id).first()
        assert db_node is not None
        assert db_node.status == "active"
        assert db_node.public_key == node_pub
        
        # Verify join code was consumed
        db_code = session.query(NodeJoinCode).filter_by(code=join_code).first()
        assert db_code is None

    # 5. Test Decoy masking on Node Report with missing/invalid credentials
    # Missing headers
    response = client.post("/api/nodes/report", json={
        "incident_id": "inc-1",
        "action": "client_banned",
        "client_email": "test@domain.com",
        "signature": "fake_sig"
    })
    assert response.status_code == 404
    
    # Invalid token in header
    response = client.post("/api/nodes/report", json={
        "incident_id": "inc-1",
        "action": "client_banned",
        "client_email": "test@domain.com",
        "signature": "fake_sig"
    }, headers={
        "X-Node-ID": node_id,
        "Authorization": "Bearer invalid_token"
    })
    assert response.status_code == 404
    
    # 6. Test Node Report with valid Token but invalid Signature
    response = client.post("/api/nodes/report", json={
        "incident_id": "inc-1",
        "action": "client_banned",
        "client_email": "test@domain.com",
        "signature": "abcd" * 16  # Invalid signature bytes
    }, headers={
        "X-Node-ID": node_id,
        "Authorization": f"Bearer {node_token}"
    })
    assert response.status_code == 404
    
    # 7. Test Node Report with valid Token and valid Ed25519 Signature
    report_payload = {
        "incident_id": "inc-100",
        "action": "client_banned",
        "client_email": "attacker@spectre.vpn",
        "details": "Brute-force attacker blocked locally."
    }
    
    # Generate signature using the node's private key
    sig = sign_payload(report_payload, node_priv)
    report_payload["signature"] = sig
    
    # Set up client to block in database so we verify block action
    with db_session() as session:
        # Clear existing
        session.query(ClientStats).filter_by(email="attacker@spectre.vpn").delete()
        # Add client
        client_stats = ClientStats(
            inbound_id=1,  # Assuming default inbound has ID 1 or just using mock
            email="attacker@spectre.vpn",
            client_uuid_or_pwd="some_password_or_uuid",
            enable=1
        )
        session.add(client_stats)
        
    response = client.post("/api/nodes/report", json=report_payload, headers={
        "X-Node-ID": node_id,
        "Authorization": f"Bearer {node_token}"
    })
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "success"
    
    # Verify client is blocked on Master after node report
    with db_session() as session:
        db_client = session.query(ClientStats).filter_by(email="attacker@spectre.vpn").first()
        assert db_client is not None
        assert db_client.enable == 0
        assert "Cooperative ban" in db_client.block_reason

    # 8. Test Admin Listing and Deleting (Revoking) Nodes
    # List nodes
    response = client.get("/api/nodes")
    assert response.status_code == 200
    nodes_list = response.json()
    assert len(nodes_list) >= 1
    assert any(n["id"] == node_id for n in nodes_list)
    
    # Delete (revoke) node
    response = client.delete(f"/api/nodes/{node_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Verify node is deleted in DB
    with db_session() as session:
        db_node = session.query(Node).filter_by(id=node_id).first()
        assert db_node is None
        
    # Verify that revoked node now receives decoy 404 responses
    response = client.post("/api/nodes/report", json=report_payload, headers={
        "X-Node-ID": node_id,
        "Authorization": f"Bearer {node_token}"
    })
    assert response.status_code == 404

def test_node_agent_bootstrap_and_autoban(client, monkeypatch):
    """Test the Node Agent config handling, registration flow, and auto-investigation log analysis."""
    
    # Clear local config file if exists
    import os
    from backend.node_agent import CONFIG_FILE_PATH
    if CONFIG_FILE_PATH.exists():
        os.remove(CONFIG_FILE_PATH)
        
    # Monkeypatch check_auth for admin join code generation
    import backend.routes.nodes
    monkeypatch.setattr(backend.routes.nodes, "check_auth", lambda r: True)
    
    # 1. Generate join code
    res = client.post("/api/nodes/join-code")
    join_code = res.json()["code"]
    
    # 2. Mock httpx client calls to go directly to FastAPI TestClient
    async def mock_post(client_self, url: str, json: dict = None, headers: dict = None, **kwargs):
        # Determine path from url
        path = url.split("master-server.com")[1]
        
        # Call fastapi testclient synchronous methods inside async wrapper
        if headers:
            r = client.post(path, json=json, headers=headers)
        else:
            r = client.post(path, json=json)
            
        # Wrap response into an object mimicking httpx Response
        class MockResponse:
            def __init__(self, r_obj):
                self.status_code = r_obj.status_code
                self.text = r_obj.text
                self._json = r_obj.json()
            def json(self):
                return self._json
                
        return MockResponse(r)
        
    monkeypatch.setattr("httpx.AsyncClient.post", mock_post)
    
    # 3. Test Agent registration function
    import asyncio
    
    reg_success = asyncio.run(register_with_master("http://master-server.com", join_code))
    assert reg_success is True
    
    # Verify config file exists and contains correct keys
    config = load_node_config()
    assert config is not None
    assert "node_id" in config
    assert "node_api_token" in config
    assert "private_key" in config
    
    # 4. Test Auto-Investigation Mock Flow
    # Add a mock connection in log parsers
    monkeypatch.setattr("backend.routes.security.find_email_in_hysteria_log", lambda ip, port: "malicious_user@vpn.net")
    monkeypatch.setattr("backend.routes.security.find_email_in_xray_log", lambda client_ip, ip, port: "malicious_user@vpn.net")
    
    # Setup client in local DB to verify local block
    with db_session() as session:
        session.query(ClientStats).filter_by(email="malicious_user@vpn.net").delete()
        client_stats = ClientStats(
            inbound_id=1,
            email="malicious_user@vpn.net",
            client_uuid_or_pwd="pass",
            enable=1
        )
        session.add(client_stats)
        
    # Run auto-investigate & resolve
    culprit = asyncio.run(auto_investigate_and_resolve("8.8.8.8", 443))
    assert culprit == "malicious_user@vpn.net"
    
    # Verify client was blocked locally
    with db_session() as session:
        db_client = session.query(ClientStats).filter_by(email="malicious_user@vpn.net").first()
        assert db_client is not None
        assert db_client.enable == 0
        assert "Cooperative ban" in db_client.block_reason or "Auto-ban" in db_client.block_reason
        
    # Cleanup config file
    if CONFIG_FILE_PATH.exists():
        os.remove(CONFIG_FILE_PATH)
