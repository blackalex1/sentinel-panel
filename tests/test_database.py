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


def test_normalize_database_url():
    """Test auto-detection and normalization of PostgreSQL database URLs."""
    from backend.database.connection import normalize_database_url

    # SQLite URLs should remain unchanged
    assert normalize_database_url("sqlite:///app/panel.db") == "sqlite:///app/panel.db"
    assert normalize_database_url("") == ""

    # Legacy postgres:// prefix should be converted
    res_legacy = normalize_database_url("postgres://user:pass@127.0.0.1:5432/db")
    assert res_legacy.startswith("postgresql")

    # In our current test environment (where psycopg2 is installed and psycopg is not),
    # postgresql:// should normalize to postgresql+psycopg2://
    res = normalize_database_url("postgresql://user:pass@127.0.0.1:5432/db")
    assert res.startswith("postgresql")
    try:
        import psycopg
        assert res == "postgresql://user:pass@127.0.0.1:5432/db" or "psycopg" in res
    except ImportError:
        try:
            import psycopg2
            assert res == "postgresql+psycopg2://user:pass@127.0.0.1:5432/db"
        except ImportError:
            pass

    # Test with monkeypatched modules
    import sys
    orig_modules = dict(sys.modules)
    try:
        # Scenario A: only psycopg2 available
        sys.modules["psycopg"] = None
        sys.modules["psycopg2"] = type(sys)("psycopg2")
        assert normalize_database_url("postgresql://u:p@127.0.0.1/db") == "postgresql+psycopg2://u:p@127.0.0.1/db"
        assert normalize_database_url("postgresql+psycopg://u:p@127.0.0.1/db") == "postgresql+psycopg2://u:p@127.0.0.1/db"

        # Scenario B: only psycopg available
        sys.modules["psycopg"] = type(sys)("psycopg")
        sys.modules["psycopg2"] = None
        assert normalize_database_url("postgresql://u:p@127.0.0.1/db") == "postgresql+psycopg://u:p@127.0.0.1/db"
        assert normalize_database_url("postgresql+psycopg2://u:p@127.0.0.1/db") == "postgresql+psycopg://u:p@127.0.0.1/db"

        # Scenario C: both available (prefers default postgresql:// for SQLAlchemy 2.1+)
        sys.modules["psycopg"] = type(sys)("psycopg")
        sys.modules["psycopg2"] = type(sys)("psycopg2")
        assert normalize_database_url("postgresql://u:p@127.0.0.1/db") == "postgresql://u:p@127.0.0.1/db"
    finally:
        sys.modules.clear()
        sys.modules.update(orig_modules)


