"""Sentinel-Core C-FFI and CLI Bridge.

Delegates 100% of proxy URI parsing, subscription parsing, proxy checking,
and client/server configuration building to the native Go Sentinel-Core engine.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("SentinelCoreBridge")

_core_dir = os.path.dirname(os.path.abspath(__file__))
_updater_dir = os.path.dirname(_core_dir)
_project_root = os.path.dirname(_updater_dir)

_SENTINEL_LIB: Optional[ctypes.CDLL] = None
_SENTINEL_LIB_TRIED: bool = False


def _find_core_bin() -> Optional[str]:
    """Finds sentinel-core binary strictly in project bin paths."""
    candidates = [
        os.path.join(os.getcwd(), "bot", "bin", "sentinel-core"),
        os.path.join(os.getcwd(), "bin", "sentinel-core"),
        os.path.join(_project_root, "bot", "bin", "sentinel-core"),
        os.path.join(_project_root, "bin", "sentinel-core"),
        os.path.join(_updater_dir, "bot", "bin", "sentinel-core"),
        os.path.join(_updater_dir, "bin", "sentinel-core"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _find_core_lib() -> Optional[str]:
    """Finds libsentinel-core.so / .dll / .dylib strictly in project bin paths."""
    is_win = sys.platform == "win32"
    is_mac = sys.platform == "darwin"
    lib_names = ["sentinel-core.dll", "libsentinel-core.dll"] if is_win else (
        ["libsentinel-core.dylib", "sentinel-core.dylib"] if is_mac else
        ["libsentinel-core.so", "sentinel-core.so"]
    )

    candidate_dirs = [
        os.path.join(os.getcwd(), "bot", "bin"),
        os.path.join(os.getcwd(), "bin"),
        os.path.join(_project_root, "bot", "bin"),
        os.path.join(_project_root, "bin"),
        os.path.join(_updater_dir, "bot", "bin"),
        os.path.join(_updater_dir, "bin"),
    ]

    for d in candidate_dirs:
        for name in lib_names:
            p = os.path.join(d, name)
            if os.path.isfile(p) and os.path.getsize(p) > 1024 * 1024:
                return p

    return None


def _init_sentinel_lib(lib: Any) -> None:
    """Configures argtypes and restype for Sentinel C-FFI exports."""
    if hasattr(lib, "SentinelFreeString"):
        lib.SentinelFreeString.argtypes = [ctypes.c_void_p]
        lib.SentinelFreeString.restype = None

    if hasattr(lib, "SentinelParseURI"):
        lib.SentinelParseURI.argtypes = [ctypes.c_char_p]
        lib.SentinelParseURI.restype = ctypes.c_void_p

    if hasattr(lib, "SentinelParseSubscription"):
        lib.SentinelParseSubscription.argtypes = [ctypes.c_char_p]
        lib.SentinelParseSubscription.restype = ctypes.c_void_p

    if hasattr(lib, "SentinelBatchCheckProxies"):
        lib.SentinelBatchCheckProxies.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
        ]
        lib.SentinelBatchCheckProxies.restype = ctypes.c_void_p

    if hasattr(lib, "SentinelFindFastestProxy"):
        lib.SentinelFindFastestProxy.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
        ]
        lib.SentinelFindFastestProxy.restype = ctypes.c_void_p

    if hasattr(lib, "SentinelBuildFailoverClientConfig"):
        lib.SentinelBuildFailoverClientConfig.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p
        ]
        lib.SentinelBuildFailoverClientConfig.restype = ctypes.c_void_p


def get_sentinel_lib() -> Optional[ctypes.CDLL]:
    """Loads and initializes Sentinel-Core C-shared library."""
    global _SENTINEL_LIB, _SENTINEL_LIB_TRIED
    if _SENTINEL_LIB is not None:
        return _SENTINEL_LIB
    if _SENTINEL_LIB_TRIED:
        return None

    _SENTINEL_LIB_TRIED = True
    lib_path = _find_core_lib()
    if not lib_path:
        return None

    try:
        lib = ctypes.CDLL(lib_path)
        _init_sentinel_lib(lib)
        _SENTINEL_LIB = lib
        return _SENTINEL_LIB
    except Exception as e:
        logger.debug("Failed to load sentinel-core C-shared library: %s", e)
        return None


def _ffi_call(func_name: str, *args) -> Optional[str]:
    """Invokes a C-FFI function safely with memory cleanup."""
    lib = get_sentinel_lib()
    if not lib or not hasattr(lib, func_name):
        return None

    func = getattr(lib, func_name)
    if hasattr(func, "restype") and func.restype != ctypes.c_void_p and func_name != "SentinelFreeString":
        func.restype = ctypes.c_void_p

    c_args = []
    for a in args:
        if isinstance(a, str):
            c_args.append(a.encode("utf-8"))
        elif isinstance(a, int):
            c_args.append(ctypes.c_int(a))
        elif isinstance(a, bytes):
            c_args.append(a)
        elif a is None:
            c_args.append(None)
        else:
            c_args.append(a)

    ptr = func(*c_args)
    if not ptr:
        return None
    try:
        raw_bytes = ctypes.cast(ptr, ctypes.c_char_p).value
        if raw_bytes is None:
            return None
        return raw_bytes.decode("utf-8", errors="replace")
    finally:
        if hasattr(lib, "SentinelFreeString"):
            lib.SentinelFreeString(ctypes.c_void_p(ptr))


def run_cli_command(args: List[str], input_data: Optional[str] = None) -> Any:
    """Executes sentinel-core binary CLI as fallback."""
    bin_path = _find_core_bin()
    if not bin_path:
        return {"error": "sentinel-core binary not found"}

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
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"raw": output}
        return {"error": stderr.strip() or f"Exited with code {proc.returncode}"}
    except Exception as e:
        return {"error": str(e)}


# ==============================================================================
# Public Core Functions (100% Core Delegated)
# ==============================================================================

def parse_proxy_uri(raw_uri: str) -> Optional[Dict[str, Any]]:
    """Parses any VPN URI (VLESS Reality, Shadowsocks, Trojan, Hysteria2) via Go Core."""
    raw = _ffi_call("SentinelParseURI", raw_uri)
    if raw:
        try:
            res = json.loads(raw)
            if isinstance(res, dict) and "error" not in res:
                return res
        except Exception:
            pass

    cli_res = run_cli_command(["parse", "--uri", raw_uri])
    if isinstance(cli_res, dict) and "error" not in cli_res:
        return cli_res
    return None


def parse_subscription(content: str) -> List[Dict[str, Any]]:
    """Parses raw subscription text / base64 into list of ServerProfiles via Go Core."""
    if not content or not content.strip():
        return []

    raw = _ffi_call("SentinelParseSubscription", content)
    if raw:
        try:
            res = json.loads(raw)
            if isinstance(res, list):
                return res
        except Exception:
            pass

    cli_res = run_cli_command(["parse-subscription"], input_data=content)
    if isinstance(cli_res, list):
        return cli_res
    if isinstance(cli_res, dict) and "profiles" in cli_res:
        return cli_res["profiles"]
    return []


def batch_check_proxies(
    proxies: List[str],
    target_host: str = "objects.githubusercontent.com",
    target_port: int = 443,
    use_tls: bool = True,
    timeout_ms: int = 2500,
    concurrency: int = 32,
) -> List[Dict[str, Any]]:
    """Checks proxies concurrently using Go Core (goroutines + TLS/Reality handshakes)."""
    if not proxies:
        return []

    proxies_json = json.dumps(proxies)
    raw = _ffi_call(
        "SentinelBatchCheckProxies",
        proxies_json,
        target_host,
        target_port,
        1 if use_tls else 0,
        timeout_ms,
        concurrency,
    )
    if raw:
        try:
            res = json.loads(raw)
            if isinstance(res, list):
                return res
        except Exception:
            pass

    cli_res = run_cli_command(
        ["check-proxies", "--target-host", target_host, "--target-port", str(target_port), "--timeout-ms", str(timeout_ms)],
        input_data=proxies_json,
    )
    if isinstance(cli_res, list):
        return cli_res
    return []


def build_failover_client_config(
    profiles: List[Dict[str, Any]],
    target_core: str = "singbox",
    socks_port: int = 10818,
    http_port: int = 10819,
    health_url: str = "https://objects.githubusercontent.com",
) -> Optional[Dict[str, Any]]:
    """Builds complete Sing-box or Xray failover client JSON configuration via Go Core."""
    if not profiles:
        return None

    profiles_json = json.dumps(profiles)
    raw = _ffi_call(
        "SentinelBuildFailoverClientConfig",
        profiles_json,
        target_core,
        socks_port,
        http_port,
        health_url,
    )
    if raw:
        try:
            res = json.loads(raw)
            if isinstance(res, dict) and "error" not in res:
                return res
        except Exception:
            pass

    cli_res = run_cli_command(
        ["build-failover", "--core", target_core, "--socks", str(socks_port), "--http", str(http_port), "--health-url", health_url],
        input_data=profiles_json,
    )
    if isinstance(cli_res, dict) and "error" not in cli_res:
        return cli_res
    return None
