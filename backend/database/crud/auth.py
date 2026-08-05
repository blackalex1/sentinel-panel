import hashlib
import os
import secrets
from backend.models import User
import backend.database

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt_hex, key_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, 100000)
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False

def authenticate_admin(username: str, password_plain: str) -> bool:
    with backend.database.db_session() as session:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            return False
        return backend.database.verify_password(password_plain, user.password)

def update_admin_password(username: str, new_password_plain: str) -> bool:
    with backend.database.db_session() as session:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            return False
        user.password = backend.database.hash_password(new_password_plain)
        return True

def update_admin_credentials(current_username: str, new_username: str, new_password_plain: str = None) -> bool:
    with backend.database.db_session() as session:
        user = session.query(User).filter_by(username=current_username).first()
        if not user:
            return False
        user.username = new_username
        if new_password_plain:
            user.password = backend.database.hash_password(new_password_plain)
        return True

