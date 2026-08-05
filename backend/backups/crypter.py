import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

def get_fernet_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key using PBKDF2HMAC."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))

def encrypt_data(data: str, password: str) -> str:
    """Encrypt data using AES-256 (Fernet) with a derived key."""
    salt = os.urandom(16)
    key = get_fernet_key(password, salt)
    f = Fernet(key)
    encrypted = f.encrypt(data.encode("utf-8"))
    return f"enc1:{salt.hex()}:{encrypted.decode('utf-8')}"

def decrypt_data(encrypted_str: str, password: str) -> str:
    """Decrypt data using AES-256 (Fernet) with a derived key."""
    if not encrypted_str.startswith("enc1:"):
        raise ValueError("backup_unsupported_encryption_format")
    parts = encrypted_str.split(":")
    if len(parts) != 3:
        raise ValueError("backup_invalid_encrypted_data")
    salt = bytes.fromhex(parts[1])
    ciphertext = parts[2].encode("utf-8")
    key = get_fernet_key(password, salt)
    f = Fernet(key)
    decrypted = f.decrypt(ciphertext)
    return decrypted.decode("utf-8")
