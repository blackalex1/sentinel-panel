import base64
import hmac
import hashlib
import struct
import time
import secrets
from urllib.parse import quote

def generate_totp_secret() -> str:
    """Generates a secure random 32-character base32 secret (160 bits)."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(secrets.choice(chars) for _ in range(32))

def get_totp_token(secret: str, time_step: int = 30, t: int = None) -> str:
    """
    Generates a 6-digit TOTP token for a given secret and timestamp.
    Follows RFC 6238 / RFC 4226.
    """
    if t is None:
        t = int(time.time())
    counter = t // time_step
    
    # Clean up base32 secret and apply correct padding
    secret = secret.strip().replace(" ", "").upper()
    missing_padding = len(secret) % 8
    if missing_padding:
        secret += "=" * (8 - missing_padding)
        
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception as e:
        raise ValueError(f"Invalid Base32 secret: {e}")
        
    # Pack counter into 8-byte big-endian bytes
    msg = struct.pack(">Q", counter)
    
    # Generate HMAC-SHA1 signature
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    
    # Dynamic truncation (RFC 4226 Section 5.4)
    offset = digest[19] & 15
    binary = struct.unpack(">I", digest[offset:offset+4])[0] & 0x7fffffff
    
    # Extract 6 digits
    token = binary % 1000000
    return f"{token:06d}"

def verify_totp_token(secret: str, token: str, window: int = 1) -> bool:
    """
    Verifies a TOTP token against a secret.
    Allows for time drift by checking codes within the specified window (default +/- 1 time step, i.e. +/- 30s).
    """
    if not token or not secret:
        return False
        
    token = token.strip()
    if len(token) != 6 or not token.isdigit():
        return False
        
    now = int(time.time())
    for i in range(-window, window + 1):
        t_drift = now + (i * 30)
        try:
            if get_totp_token(secret, t=t_drift) == token:
                return True
        except ValueError:
            return False
            
    return False

def get_totp_uri(secret: str, username: str, issuer: str = "Spectre Panel") -> str:
    """Generates the standard otpauth:// URI to generate QR codes for Authenticator apps."""
    label = f"{issuer}:{username}"
    return f"otpauth://totp/{quote(label)}?secret={secret}&issuer={quote(issuer)}"
