import pytest
from backend.database import (
    hash_password, verify_password, add_inbound, get_inbound_by_id, 
    update_inbound, add_client_db, get_clients_for_inbound, 
    update_client_db, delete_client_db, delete_inbound
)

def test_password_hashing():
    """Test PBKDF2-HMAC-SHA256 password security."""
    pwd = "MySecretPassword123"
    hashed = hash_password(pwd)
    
    assert hashed != pwd
    assert len(hashed.split(":")) == 2
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_database_crud():
    """Test SQL CRUD functions in database.py."""
    # 1. Add inbound
    port = 60001
    ib_id = add_inbound(
        remark="Test direct CRUD",
        port=port,
        protocol="vless",
        settings_dict={"clients": []},
        stream_settings_dict={"network": "ws"}
    )
    assert ib_id is not None

    # 2. Get inbound
    ib = get_inbound_by_id(ib_id)
    assert ib["remark"] == "Test direct CRUD"
    assert ib["port"] == port
    assert ib["protocol"] == "vless"

    # 3. Update inbound
    success = update_inbound(
        inbound_id=ib_id,
        remark="Test direct CRUD updated",
        port=port,
        protocol="vless",
        settings_dict={"clients": []},
        stream_settings_dict={"network": "ws"},
        enable=0
    )
    assert success is True
    ib = get_inbound_by_id(ib_id)
    assert ib["remark"] == "Test direct CRUD updated"
    assert ib["enable"] == 0

    # 4. Add client
    client_pwd = "my-secret-uuid"
    c_success = add_client_db(
        inbound_id=ib_id,
        email="test_client@mail.com",
        client_uuid_or_pwd=client_pwd,
        total_gb=10,
        expiry_time=123456789,
        enable=1
    )
    assert c_success is True

    # 5. Get client
    clients = get_clients_for_inbound(ib_id)
    assert len(clients) == 1
    assert clients[0]["email"] == "test_client@mail.com"
    assert clients[0]["client_uuid_or_pwd"] == client_pwd

    # 6. Update client
    u_success = update_client_db(
        inbound_id=ib_id,
        email="test_client@mail.com",
        total_gb=20,
        expiry_time=987654321,
        enable=0
    )
    assert u_success is True
    clients = get_clients_for_inbound(ib_id)
    assert clients[0]["enable"] == 0
    assert clients[0]["total"] == 20 * 1024 * 1024 * 1024

    # 7. Delete client
    d_c_success = delete_client_db(ib_id, "test_client@mail.com")
    assert d_c_success is True
    assert len(get_clients_for_inbound(ib_id)) == 0

    # 8. Delete inbound
    d_success = delete_inbound(ib_id)
    assert d_success is True
    assert get_inbound_by_id(ib_id) is None
