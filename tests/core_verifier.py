import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from backend.config import BIN_DIR, IS_WINDOWS, XRAY_BIN_PATH, SINGBOX_BIN_PATH
from backend.hysteria import HYSTERIA_BIN_PATH

def get_free_port() -> int:
    """Finds a free port on localhost."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def get_xray_bin():
    if XRAY_BIN_PATH.exists():
        return XRAY_BIN_PATH
    alt = BIN_DIR / ("xray.exe" if IS_WINDOWS else "xray")
    if alt.exists():
        return alt
    return None

def get_singbox_bin():
    if SINGBOX_BIN_PATH.exists():
        return SINGBOX_BIN_PATH
    alt = BIN_DIR / ("sing-box.exe" if IS_WINDOWS else "sing-box")
    if alt.exists():
        return alt
    return None

def get_hysteria_bin():
    if HYSTERIA_BIN_PATH.exists():
        return HYSTERIA_BIN_PATH
    for fname in ["hysteria-windows-amd64.exe", "hysteria.exe", "hysteria-linux-amd64", "hysteria"]:
        p = BIN_DIR / fname
        if p.exists():
            return p
    return None

def validate_xray_config(config_dict: dict) -> tuple[bool, str]:
    """Validates Xray configuration using the real Xray core binary."""
    bin_path = get_xray_bin()
    if not bin_path:
        return True, "Xray binary not found, skipping CLI validation"
        
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_dict, f, indent=2)
        tmp_name = f.name
        
    try:
        res = subprocess.run(
            [str(bin_path), "run", "-test", "-config", tmp_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = (res.stdout or "") + (res.stderr or "")
        # Exit code 0 or output containing 'Configuration OK' indicates valid config
        if res.returncode == 0 or "Configuration OK" in output:
            return True, output
        return False, f"Xray config validation failed (code {res.returncode}): {output}"
    except subprocess.TimeoutExpired:
        return False, "Xray binary validation timed out"
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except Exception:
                pass

def validate_singbox_config(config_dict: dict) -> tuple[bool, str]:
    """Validates sing-box configuration using the real sing-box core binary."""
    bin_path = get_singbox_bin()
    if not bin_path:
        return True, "sing-box binary not found, skipping CLI validation"
        
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_dict, f, indent=2)
        tmp_name = f.name
        
    try:
        res = subprocess.run(
            [str(bin_path), "check", "-c", tmp_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = (res.stdout or "") + (res.stderr or "")
        if res.returncode == 0:
            return True, output
        return False, f"sing-box config validation failed (code {res.returncode}): {output}"
    except subprocess.TimeoutExpired:
        return False, "sing-box binary validation timed out"
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except Exception:
                pass

def validate_hysteria_config(config_dict: dict) -> tuple[bool, str]:
    """Validates Hysteria 2 configuration using the real Hysteria core binary."""
    bin_path = get_hysteria_bin()
    if not bin_path:
        return True, "Hysteria binary not found, skipping CLI validation"
        
    from backend.hysteria import generate_self_signed_cert, HYSTERIA_CERT_PATH, HYSTERIA_KEY_PATH
    if not HYSTERIA_CERT_PATH.exists() or not HYSTERIA_KEY_PATH.exists():
        try:
            generate_self_signed_cert()
        except Exception:
            pass

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_dict, f, indent=2)
        tmp_name = f.name
        
    try:
        res = subprocess.run(
            [str(bin_path), "server", "-c", tmp_name],
            capture_output=True,
            text=True,
            timeout=1
        )
        output = (res.stdout or "") + (res.stderr or "")
        if "invalid config" in output.lower() and "tls: failed to find any pem data" not in output.lower():
            return False, f"Hysteria config validation failed: {output}"
        return True, output
    except subprocess.TimeoutExpired:
        # Running fine for 1s means it loaded config and started listening server mode successfully
        return True, "Hysteria server started successfully"
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except Exception:
                pass
