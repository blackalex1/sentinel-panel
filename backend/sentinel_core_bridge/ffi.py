import ctypes
import json
import logging
import os
import subprocess
import sys
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_SENTINEL_LIB: Optional[ctypes.CDLL] = None
_SENTINEL_LIB_TRIED: bool = False


def _get_sentinel_core_bin() -> str:
    """Finds the sentinel-core binary on Windows or Linux."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bin_dir = os.path.join(base_dir, "bin")

    is_windows = sys.platform == "win32" or os.name == "nt"
    bin_name = "sentinel-core.exe" if is_windows else "sentinel-core"

    bin_path = os.path.join(bin_dir, bin_name)
    if os.path.isfile(bin_path):
        return bin_path

    # Fallback to PATH
    return bin_name


def _find_sentinel_core_lib_path() -> Optional[str]:
    """Finds the sentinel-core shared library (.dll, .so, .dylib) on Windows, Linux, or macOS."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bin_dir = os.path.join(base_dir, "bin")

    is_windows = sys.platform == "win32" or os.name == "nt"
    is_darwin = sys.platform == "darwin"

    if is_windows:
        candidates = [
            os.path.join(bin_dir, "sentinel-core.dll"),
            os.path.join(bin_dir, "libsentinel-core.dll"),
            "sentinel-core.dll",
        ]
    elif is_darwin:
        candidates = [
            os.path.join(bin_dir, "libsentinel-core.dylib"),
            os.path.join(bin_dir, "sentinel-core.dylib"),
            "libsentinel-core.dylib",
        ]
    else:
        candidates = [
            os.path.join(bin_dir, "libsentinel-core.so"),
            os.path.join(bin_dir, "sentinel-core.so"),
            "libsentinel-core.so",
            "sentinel-core.so",
        ]

    for cand in candidates:
        if os.path.isabs(cand) and os.path.isfile(cand):
            return cand

    # Try finding in system paths via ctypes.util
    try:
        from ctypes.util import find_library
        sys_lib = find_library("sentinel-core") or find_library("libsentinel-core")
        if sys_lib:
            return sys_lib
    except Exception:
        pass

    return None


def _init_sentinel_lib(lib: Any) -> Any:
    """Configures argtypes and restype for all exported Sentinel C-FFI functions."""
    if hasattr(lib, "SentinelFreeString"):
        try:
            lib.SentinelFreeString.argtypes = [ctypes.c_void_p]
            lib.SentinelFreeString.restype = None
        except (AttributeError, TypeError):
            pass

    func_signatures = [
        ("SentinelBuildConfig", [ctypes.c_char_p]),
        ("SentinelBuildServerConfig", [ctypes.c_char_p]),
        ("SentinelParseURI", [ctypes.c_char_p]),
        ("SentinelGenerateURI", [ctypes.c_char_p]),
        ("SentinelGenerateX25519Keys", []),
        ("SentinelGetCoresStatus", []),
        ("SentinelGetUnifiedTraffic", []),
        ("SentinelKickClient", [ctypes.c_char_p]),
        ("SentinelGetCoreLogs", [ctypes.c_char_p, ctypes.c_int]),
        ("SentinelPing", [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]),
        ("SentinelEncrypt", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelDecrypt", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelEncryptPayload", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelDecryptPayload", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelListPresets", []),
        ("SentinelGetPreset", [ctypes.c_char_p]),
        ("SentinelGetConfigurationSchema", [ctypes.c_char_p]),
        ("SentinelRunHealthCheck", [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]),
        ("SentinelStartCore", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelStopCore", [ctypes.c_char_p]),
        ("SentinelRestartCore", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelValidateCore", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelGenerateVlessEncKeys", []),
        ("SentinelRegisterHysteriaPort", [ctypes.c_int]),
        ("SentinelConfigureSupervisor", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelGetCoreVersion", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelPopLogLine", [ctypes.c_char_p, ctypes.c_int]),
        ("SentinelGetInMemoryLogs", [ctypes.c_char_p, ctypes.c_int]),
        ("SentinelClearInMemoryLogs", [ctypes.c_char_p]),
        ("SentinelGetSecuritySchema", [ctypes.c_char_p]),
        ("SentinelGetDefaultSecurityConfig", []),
        ("SentinelValidateSecurityConfig", [ctypes.c_char_p]),
        ("SentinelGetActiveSessions", []),
        ("SentinelGetOnlineEmails", []),
        ("SentinelGetRecentSessionEvents", [ctypes.c_longlong, ctypes.c_int]),
        ("SentinelRegisterExternalConnect", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelSetLanguage", [ctypes.c_char_p]),
        ("SentinelParseSubscription", [ctypes.c_char_p]),
        ("SentinelBatchCheckProxies", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]),
        ("SentinelFindFastestProxy", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]),
        ("SentinelBuildFailoverClientConfig", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p]),
    ]

    for name, argtypes in func_signatures:
        if hasattr(lib, name):
            try:
                func = getattr(lib, name)
                func.argtypes = argtypes
                func.restype = ctypes.c_void_p
            except (AttributeError, TypeError):
                pass

    return lib


def get_sentinel_lib() -> Optional[ctypes.CDLL]:
    """Returns the loaded ctypes.CDLL instance for sentinel-core, or None if unavailable."""
    global _SENTINEL_LIB, _SENTINEL_LIB_TRIED
    if _SENTINEL_LIB is not None:
        return _SENTINEL_LIB
    if _SENTINEL_LIB_TRIED:
        return None

    _SENTINEL_LIB_TRIED = True
    lib_path = _find_sentinel_core_lib_path()
    if not lib_path:
        return None

    try:
        lib = ctypes.CDLL(lib_path)
        _init_sentinel_lib(lib)
        _SENTINEL_LIB = lib
        logger.info("Loaded sentinel-core shared library from %s", lib_path)
        return _SENTINEL_LIB
    except Exception as e:
        logger.warning("Failed to load sentinel-core shared library (%s): %s", lib_path, e)
        return None


def set_sentinel_lib(lib: Optional[ctypes.CDLL]) -> None:
    """Explicitly sets or resets the CDLL instance (useful for testing or runtime injection)."""
    global _SENTINEL_LIB, _SENTINEL_LIB_TRIED
    if lib is not None:
        _init_sentinel_lib(lib)
    _SENTINEL_LIB = lib
    _SENTINEL_LIB_TRIED = (lib is not None)


def _ffi_call_str(func_name: str, *args) -> Optional[str]:
    """Calls a C-FFI function returning a Go allocated string, decodes utf-8, and frees memory via SentinelFreeString."""
    lib = get_sentinel_lib()
    if not lib or not hasattr(lib, func_name):
        return None

    func = getattr(lib, func_name)
    func.restype = ctypes.c_void_p

    c_args = []
    for i, a in enumerate(args):
        if isinstance(a, str):
            c_args.append(a.encode("utf-8"))
        elif isinstance(a, int):
            if hasattr(func, "argtypes") and func.argtypes and i < len(func.argtypes):
                expected_t = func.argtypes[i]
                c_args.append(expected_t(a))
            else:
                c_args.append(ctypes.c_longlong(a) if a > 2147483647 or a < -2147483648 else ctypes.c_int(a))
        elif isinstance(a, bytes):
            c_args.append(a)
        elif a is None:
            c_args.append(None)
        else:
            c_args.append(a)

    try:
        ptr = func(*c_args)
    except Exception as e:
        logger.debug("FFI call %s failed: %s", func_name, e)
        return None

    if not ptr:
        return None
    try:
        raw_bytes = ctypes.cast(ptr, ctypes.c_char_p).value
        if raw_bytes is None:
            return None
        return raw_bytes.decode("utf-8", errors="replace")
    finally:
        if hasattr(lib, "SentinelFreeString"):
            try:
                lib.SentinelFreeString(ctypes.c_void_p(ptr))
            except Exception:
                pass


def _ffi_call_json(func_name: str, *args) -> Optional[Any]:
    """Calls a C-FFI function and parses its JSON output."""
    raw = _ffi_call_str(func_name, *args)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw}


def run_core_command(args: List[str], input_data: Optional[str] = None, parse_json: bool = True) -> Any:
    """Executes sentinel-core CLI with given args and returns parsed JSON output or raw string."""
    import shutil
    bin_path = _get_sentinel_core_bin()
    if not os.path.isabs(bin_path) and not os.path.exists(bin_path):
        which_p = shutil.which(bin_path)
        if which_p:
            bin_path = which_p

    if not os.path.exists(bin_path) and not shutil.which(bin_path):
        logger.debug("sentinel-core binary not found at '%s', skipping command", bin_path)
        return {"error": f"sentinel-core binary not found at '{bin_path}'"}

    cmd = [bin_path] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if input_data else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )
        stdout, stderr = proc.communicate(input=input_data, timeout=10)
        output = (stdout or "").strip()
        if output:
            if not parse_json:
                return output
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return output

        if proc.returncode != 0:
            err_msg = (stderr or "").strip() or f"Process exited with code {proc.returncode}"
            logger.error("sentinel-core exited with code %d: %s", proc.returncode, err_msg)
            return {"error": err_msg}

        return {"raw": output}
    except Exception as e:
        logger.exception("Failed to execute sentinel-core CLI: %s", e)
        return {"error": str(e)}
