import time
from backend.database import db_session
from backend.models import AuditLog

def test_audit_logging(client, monkeypatch):
    """Test backend audit logging creation and API retrieval."""
    import backend.routes.system
    monkeypatch.setattr(backend.routes.system, "check_auth", lambda r: True)
    
    with db_session() as session:
        # Clear existing logs for a predictable test
        session.query(AuditLog).delete()
        
        # Add a couple of audit logs
        log1 = AuditLog(timestamp=int(time.time()) - 10, username="test_admin", action="test_action_1", target="client1", details="details1")
        log2 = AuditLog(timestamp=int(time.time()), username="test_admin", action="test_action_2", target="client2", details="details2")
        session.add(log1)
        session.add(log2)
        
    # Get audit logs via API
    response = client.get("/api/audit-logs?page=1&limit=10")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    logs = res_data["obj"]["logs"]
    assert len(logs) >= 2
    # Check ordering (descending)
    assert logs[0]["action"] == "test_action_2"
    assert logs[1]["action"] == "test_action_1"
    
    # Test search query
    response = client.get("/api/audit-logs?search=test_action_1")
    assert response.status_code == 200
    res_data = response.json()
    assert len(res_data["obj"]["logs"]) == 1
    assert res_data["obj"]["logs"][0]["action"] == "test_action_1"


def test_crud_audit_logging(client, monkeypatch):
    """Verify that inbound and client CRUD operations actually write to the AuditLog table."""
    import json
    # Mock xray/hysteria restart to avoid running subprocesses
    monkeypatch.setattr("backend.routes.inbound_routes.crud.restart_xray", lambda: None)
    monkeypatch.setattr("backend.routes.inbound_routes.crud.restart_hysteria", lambda: None)
    monkeypatch.setattr("backend.routes.clients.crud.restart_xray", lambda: None)
    monkeypatch.setattr("backend.routes.clients.crud.restart_hysteria", lambda: None)

    with db_session() as session:
        session.query(AuditLog).delete()

    headers = {"Authorization": "Bearer test_bearer_token"}

    # 1. Create Inbound
    payload = {
        "remark": "Audit Inbound",
        "port": 54321,
        "protocol": "vless",
        "settings": {},
        "streamSettings": {},
        "sniffing": {},
        "total": 0,
        "expiryTime": 0
    }
    response = client.post("/api/inbounds/create", json=payload, headers=headers)
    assert response.status_code == 200
    ib_id = response.json()["id"]

    # 2. Add Client
    client_payload = {
        "id": ib_id,
        "settings": json.dumps({
            "clients": [{
                "id": "audit-client-uuid",
                "email": "audit_client@test.com",
                "enable": True,
                "limitIp": 0,
                "totalGB": 10,
                "expiryTime": 0
            }]
        })
    }
    response = client.post("/panel/api/inbounds/addClient", data=client_payload, headers=headers)
    assert response.status_code == 200

    # 3. Delete Client
    response = client.post(f"/panel/api/inbounds/{ib_id}/delClient/audit-client-uuid", headers=headers)
    assert response.status_code == 200

    # 4. Delete Inbound
    response = client.post(f"/api/inbounds/delete/{ib_id}", headers=headers)
    assert response.status_code == 200

    # Verify AuditLog table contents
    with db_session() as session:
        logs = session.query(AuditLog).all()
        actions = [log.action for log in logs]
        assert "create_inbound" in actions
        assert "create_client" in actions
        assert "delete_client" in actions
        assert "delete_inbound" in actions
