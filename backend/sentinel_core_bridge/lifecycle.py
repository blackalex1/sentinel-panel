import logging
import os
from typing import Dict, Any, Tuple

from backend.sentinel_core_bridge.ffi import (
    _ffi_call_str,
    _ffi_call_json,
    run_core_command,
)

logger = logging.getLogger(__name__)

_CORE_VERSION_CACHE: Dict[Tuple[str, str, float], str] = {}


def start_core(core_name: str, bin_path: str, config_path: str = "") -> bool:
    """Starts a proxy core process via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelStartCore", core_name, str(bin_path), str(config_path or ""))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI start_core error: %s", e)

    args = ["supervisor", "start", "--core", core_name, "--bin", str(bin_path)]
    if config_path:
        args.extend(["--config", str(config_path)])
    res = run_core_command(args)
    return isinstance(res, dict) and res.get("success") is True


def stop_core(core_name: str) -> bool:
    """Stops a proxy core process via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelStopCore", core_name)
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI stop_core error: %s", e)

    res = run_core_command(["supervisor", "stop", "--core", core_name])
    return isinstance(res, dict) and res.get("success") is True


def restart_core(core_name: str, bin_path: str, config_path: str = "") -> bool:
    """Restarts a proxy core process via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelRestartCore", core_name, str(bin_path), str(config_path or ""))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI restart_core error: %s", e)

    args = ["supervisor", "restart", "--core", core_name, "--bin", str(bin_path)]
    if config_path:
        args.extend(["--config", str(config_path)])
    res = run_core_command(args)
    return isinstance(res, dict) and res.get("success") is True


def validate_core_config(core_name: str, bin_path: str, config_path: str) -> Tuple[bool, str]:
    """Validates configuration syntax for any core via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelValidateCore", core_name, str(bin_path), str(config_path))
        if isinstance(res, dict) and "valid" in res:
            return bool(res.get("valid", False)), str(res.get("output", "") or res.get("error", ""))
    except Exception as e:
        logger.debug("FFI validate_core_config error: %s", e)

    res = run_core_command(["supervisor", "validate", "--core", core_name, "--bin", str(bin_path), "--config", str(config_path)])
    if isinstance(res, dict):
        return bool(res.get("valid", False)), str(res.get("output", "") or res.get("error", ""))
    return False, "Validation failed"


def get_cores_status() -> Dict[str, Any]:
    """Returns runtime status of all cores via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelGetCoresStatus")
        if isinstance(res, dict) and "error" not in res and len(res) > 0:
            return res
    except Exception as e:
        logger.debug("FFI get_cores_status error: %s", e)

    res = run_core_command(["supervisor", "status"])
    if isinstance(res, dict) and "error" not in res:
        return res
    return {}


def get_core_version(core_name: str, bin_path: str) -> str:
    """Detects version string of any installed proxy core via sentinel-core with mtime caching."""
    if not os.path.exists(bin_path):
        return "Not Installed"
    try:
        mtime = os.path.getmtime(bin_path)
    except Exception:
        mtime = 0.0
    cache_key = (core_name, bin_path, mtime)
    if cache_key in _CORE_VERSION_CACHE:
        return _CORE_VERSION_CACHE[cache_key]

    try:
        ver = _ffi_call_str("SentinelGetCoreVersion", core_name, str(bin_path))
        if ver and ver != "Unknown":
            _CORE_VERSION_CACHE[cache_key] = ver
            return ver
    except Exception as e:
        logger.debug("FFI get_core_version error: %s", e)

    res = run_core_command(["supervisor", "version", "--core", core_name, "--bin", str(bin_path)])
    if isinstance(res, dict) and "version" in res and res["version"] != "Unknown":
        version = res["version"]
        _CORE_VERSION_CACHE[cache_key] = version
        return version
    return "Unknown"
