import base64
import hashlib
from pathlib import Path

def get_cert_sha256_fingerprint(cert_path: str) -> str:
    """Calculates the SHA-256 fingerprint (hex string) of a PEM certificate file"""
    try:
        p = Path(cert_path)
        if not p.exists():
            return ""
        content = p.read_text(encoding="utf-8", errors="ignore")
        start_marker = "-----BEGIN CERTIFICATE-----"
        end_marker = "-----END CERTIFICATE-----"
        start_idx = content.find(start_marker)
        end_idx = content.find(end_marker)
        if start_idx != -1 and end_idx != -1:
            cert_b64 = content[start_idx + len(start_marker):end_idx].replace("\n", "").replace("\r", "").strip()
            cert_der = base64.b64decode(cert_b64)
            return hashlib.sha256(cert_der).hexdigest()
    except Exception:
        pass
    return ""

def is_ip(val: str) -> bool:
    import socket
    try:
        socket.inet_aton(val)
        return True
    except socket.error:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, val)
        return True
    except socket.error:
        pass
    return False

def get_configured_fingerprint(stream_settings: dict, security_type: str = "reality") -> str:
    """
    Extracts the user-configured TLS/REALITY fingerprint from stream_settings.
    Checks inner settings, security settings dict, root stream_settings dict,
    and falls back to 'randomized' if not specified.
    """
    if not stream_settings:
        return "randomized"

    sec_settings = stream_settings.get(f"{security_type}Settings") or stream_settings.get("tlsSettings") or stream_settings.get("realitySettings") or {}
    inner_settings = sec_settings.get("settings") or {} if isinstance(sec_settings, dict) else {}

    fp = (
        (inner_settings.get("fingerprint") if isinstance(inner_settings, dict) else None) or
        (sec_settings.get("fingerprint") if isinstance(sec_settings, dict) else None) or
        (sec_settings.get("fp") if isinstance(sec_settings, dict) else None) or
        stream_settings.get("fingerprint") or
        stream_settings.get("fp")
    )

    return str(fp).strip() if fp else "randomized"

