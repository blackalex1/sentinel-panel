import json
from backend.database import db_session, add_inbound, add_client_db, get_all_inbounds, get_clients_for_inbound
from backend.models import ClientStats, Inbound
from backend.backup import create_backup_dump, restore_backup_dump

def test_backup_restore():
    """Test backup creation and restoring functions."""
    ib_id = add_inbound("Backup Inbound", 61001, "shadowsocks", {"method": "aes-128-gcm"})
    add_client_db(ib_id, "backup_user@mail.com", "pwd123", total_gb=50)
    
    backup_str = create_backup_dump()
    backup_data = json.loads(backup_str)
    assert "inbounds" in backup_data
    assert "client_stats" in backup_data
    assert len(backup_data["inbounds"]) > 0
    
    ib_backup = next((x for x in backup_data["inbounds"] if x["port"] == 61001), None)
    assert ib_backup is not None
    assert ib_backup["remark"] == "Backup Inbound"
    
    with db_session() as session:
        c_db = session.query(ClientStats).filter_by(inbound_id=ib_id, email="backup_user@mail.com").first()
        session.delete(c_db)
        ib_db = session.query(Inbound).filter_by(id=ib_id).first()
        session.delete(ib_db)
        
    success, msg = restore_backup_dump(backup_str)
    assert success is True
    
    inbounds = get_all_inbounds()
    restored_ib = next((x for x in inbounds if x["port"] == 61001), None)
    assert restored_ib is not None
    
    restored_clients = get_clients_for_inbound(restored_ib["id"])
    assert len(restored_clients) == 1
    assert restored_clients[0]["email"] == "backup_user@mail.com"
    
    with db_session() as session:
        c_db = session.query(ClientStats).filter_by(inbound_id=restored_ib["id"], email="backup_user@mail.com").first()
        session.delete(c_db)
        ib_db = session.query(Inbound).filter_by(id=restored_ib["id"]).first()
        session.delete(ib_db)

def test_encrypted_backup_restore():
    """Test encrypted backup creation and decryption flow."""
    from backend.database import set_setting
    from backend.backup import decrypt_data
    
    # Enable backup encryption
    set_setting("backup_encrypt", "true")
    set_setting("backup_password", "super-safe-password")
    
    ib_id = add_inbound("Encrypted Inbound", 61002, "shadowsocks", {"method": "aes-128-gcm"})
    add_client_db(ib_id, "crypto_user@mail.com", "pwd123", total_gb=50)
    
    try:
        backup_str = create_backup_dump()
        assert backup_str.startswith("enc1:")
        
        # Test decryption fails with wrong password
        try:
            decrypt_data(backup_str, "wrong-password")
            assert False, "Should have raised exception for wrong password"
        except Exception:
            pass
            
        # Decrypt with correct password
        decrypted_str = decrypt_data(backup_str, "super-safe-password")
        backup_data = json.loads(decrypted_str)
        assert "inbounds" in backup_data
        
        # Cleanup original added records to verify restore works
        with db_session() as session:
            c_db = session.query(ClientStats).filter_by(inbound_id=ib_id, email="crypto_user@mail.com").first()
            session.delete(c_db)
            ib_db = session.query(Inbound).filter_by(id=ib_id).first()
            session.delete(ib_db)
            
        # Restore from decrypted backup
        success, msg = restore_backup_dump(decrypted_str)
        assert success is True
        
        # Verify restored state
        inbounds = get_all_inbounds()
        restored_ib = next((x for x in inbounds if x["port"] == 61002), None)
        assert restored_ib is not None
        restored_clients = get_clients_for_inbound(restored_ib["id"])
        assert len(restored_clients) == 1
        assert restored_clients[0]["email"] == "crypto_user@mail.com"
        
        # Cleanup
        with db_session() as session:
            c_db = session.query(ClientStats).filter_by(inbound_id=restored_ib["id"], email="crypto_user@mail.com").first()
            session.delete(c_db)
            ib_db = session.query(Inbound).filter_by(id=restored_ib["id"]).first()
            session.delete(ib_db)
    finally:
        # Restore settings to default to not affect other tests
        set_setting("backup_encrypt", "false")
        set_setting("backup_password", "")
