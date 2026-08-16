import json
import os
import sys
import socket
import time
import tempfile
import subprocess
from pathlib import Path
from backend.config import BIN_DIR, IS_WINDOWS, XRAY_BIN_PATH, SINGBOX_BIN_PATH
from backend.hysteria import HYSTERIA_BIN_PATH

# ── Cross-process atomic port allocator ──────────────────────────────────────
# Shared state lives in two temp files visible to all xdist worker processes:
#   sentinel_pytest_ports.json  – JSON counter {"next_port": N}
#   sentinel_pytest_ports.lock  – exclusive file lock (never written)
#
# Algorithm:
#   1. Acquire exclusive OS-level file lock  (msvcrt on Win, fcntl on Linux)
#   2. Read counter from JSON file (default 49000 if missing)
#   3. Walk forward from counter until a port is free (bind-test)
#   4. Write counter+1 back, release lock, return port
#
# This is safe under parallel pytest-xdist because the lock is held for the
# entire read-find-write cycle.

_COUNTER_FILE = os.path.join(tempfile.gettempdir(), "sentinel_pytest_ports.json")
_LOCK_FILE    = os.path.join(tempfile.gettempdir(), "sentinel_pytest_ports.lock")
_PORT_START   = 49000
_PORT_END     = 62000   # >13 000 slots — plenty for any test suite


def _is_port_free(port: int) -> bool:
    """Return True if the port is available for binding on 127.0.0.1."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _acquire_lock(fobj):
    if sys.platform == "win32":
        import msvcrt
        deadline = time.monotonic() + 30
        while True:
            try:
                fobj.seek(0)
                msvcrt.locking(fobj.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except (OSError, IOError):
                if time.monotonic() > deadline:
                    raise RuntimeError("Timed out acquiring port-allocator lock")
                time.sleep(0.01)
    else:
        import fcntl
        fcntl.flock(fobj.fileno(), fcntl.LOCK_EX)


def _release_lock(fobj):
    try:
        if sys.platform == "win32":
            import msvcrt
            fobj.seek(0)
            msvcrt.locking(fobj.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fobj.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


def get_free_port() -> int:
    """
    Atomically allocate a unique free port across all pytest-xdist workers.

    Each call acquires an exclusive cross-process file lock, reads a shared
    counter, finds the next port that is actually free, bumps the counter, and
    returns the port.  No two workers can get the same port even if they call
    this function simultaneously.
    """
    lf = open(_LOCK_FILE, "a+")
    try:
        _acquire_lock(lf)

        # Read shared counter
        try:
            with open(_COUNTER_FILE) as f:
                data = json.load(f)
            next_port = int(data.get("next_port", _PORT_START))
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            next_port = _PORT_START

        # Clamp to valid range
        if next_port < _PORT_START or next_port >= _PORT_END:
            next_port = _PORT_START

        # Walk forward until a free port is found
        port = next_port
        while port < _PORT_END:
            if _is_port_free(port):
                break
            port += 1
        else:
            raise RuntimeError(
                f"No free ports found in range [{_PORT_START}, {_PORT_END}). "
                "Too many concurrent core processes or ports exhausted."
            )

        # Persist the next candidate (skip past the one we just claimed)
        with open(_COUNTER_FILE, "w") as f:
            json.dump({"next_port": port + 1}, f)

        return port
    finally:
        _release_lock(lf)
        lf.close()


def reset_port_counter():
    """Reset the shared port counter to the start of the range.
    Call this once per pytest session (session-scoped fixture) so that
    ports are reused cleanly across repeated test runs.
    """
    lf = open(_LOCK_FILE, "a+")
    try:
        _acquire_lock(lf)
        with open(_COUNTER_FILE, "w") as f:
            json.dump({"next_port": _PORT_START}, f)
    finally:
        _release_lock(lf)
        lf.close()

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
    """Validates Xray configuration using sentinel-core supervisor validation."""
    bin_path = get_xray_bin()
    if not bin_path:
        return True, "Xray binary not found, skipping validation"
        
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_dict, f, indent=2)
        tmp_name = f.name
        
    try:
        from backend.sentinel_core_bridge import validate_core_config
        return validate_core_config("xray", str(bin_path), tmp_name)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except Exception:
                pass

def validate_singbox_config(config_dict: dict) -> tuple[bool, str]:
    """Validates sing-box configuration using sentinel-core supervisor validation."""
    bin_path = get_singbox_bin()
    if not bin_path:
        return True, "sing-box binary not found, skipping validation"
        
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_dict, f, indent=2)
        tmp_name = f.name
        
    try:
        from backend.sentinel_core_bridge import validate_core_config
        return validate_core_config("sing-box", str(bin_path), tmp_name)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except Exception:
                pass

def validate_hysteria_config(config_dict: dict) -> tuple[bool, str]:
    """Validates Hysteria 2 configuration using sentinel-core supervisor validation."""
    bin_path = get_hysteria_bin()
    if not bin_path:
        return True, "Hysteria binary not found, skipping validation"
        
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
        from backend.sentinel_core_bridge import validate_core_config
        return validate_core_config("hysteria2", str(bin_path), tmp_name)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except Exception:
                pass
