import logging
from typing import List, Optional

from backend.sentinel_core_bridge.ffi import (
    _ffi_call_str,
    _ffi_call_json,
    run_core_command,
)

logger = logging.getLogger(__name__)


def get_core_logs(log_path: str, lines: int = 100) -> List[str]:
    """Retrieves tail logs for any core via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetCoreLogs", str(log_path), int(lines))
        if isinstance(res, list):
            return res
    except Exception as e:
        logger.debug("FFI get_core_logs error: %s", e)

    res = run_core_command(["supervisor", "logs", "--path", str(log_path), "--lines", str(lines)])
    if isinstance(res, list):
        return res
    return []


def pop_core_log_line(core_name: str, timeout_ms: int = 100) -> Optional[str]:
    """Pops the next streaming log line for the specified core directly from memory without disk IO."""
    try:
        line = _ffi_call_str("SentinelPopLogLine", str(core_name), int(timeout_ms))
        if line:
            return line
    except Exception as e:
        logger.debug("FFI pop_core_log_line error: %s", e)
    return None


def get_in_memory_core_logs(core_name: str, limit: int = 200) -> List[str]:
    """Retrieves buffered in-memory logs for the specified core from sentinel-core ring buffer."""
    try:
        res = _ffi_call_json("SentinelGetInMemoryLogs", str(core_name), int(limit))
        if isinstance(res, list):
            return res
    except Exception as e:
        logger.debug("FFI get_in_memory_core_logs error: %s", e)
    return []


def clear_in_memory_core_logs(core_name: str) -> bool:
    """Clears buffered in-memory logs for the specified core."""
    try:
        res = _ffi_call_json("SentinelClearInMemoryLogs", str(core_name))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI clear_in_memory_core_logs error: %s", e)
    return True


def push_core_log_line(core_name: str, line: str) -> bool:
    """Pushes a raw log line into sentinel-core Go memory broadcaster and session tracker."""
    try:
        res = _ffi_call_json("SentinelPushLogLine", str(core_name), str(line))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI push_core_log_line error: %s", e)
    return True


def find_xray_client_email(
    lines: List[str],
    dst_ip: Optional[str],
    dst_port: int,
    client_ip: Optional[str] = None,
    max_age_sec: int = 300
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Searches Xray/Sing-box log lines for client email, IP, and inbound tag via sentinel-core."""
    import json
    lines_json = json.dumps(lines)
    try:
        res = _ffi_call_json("SentinelFindXrayClientEmail", lines_json, client_ip or "", dst_ip or "", int(dst_port), int(max_age_sec))
        if isinstance(res, dict) and res.get("email"):
            return res.get("email"), res.get("ip") or client_ip, res.get("inbound_tag")
    except Exception as e:
        logger.debug("FFI find_xray_client_email error: %s", e)

    args = [
        "security", "find-proxy-client",
        "--core", "xray",
        "--lines", lines_json,
        "--client-ip", client_ip or "",
        "--dst-ip", dst_ip or "",
        "--dpt", str(dst_port),
        "--max-age", str(max_age_sec)
    ]
    res = run_core_command(args)
    if isinstance(res, dict) and res.get("email"):
        return res.get("email"), res.get("ip") or client_ip, res.get("inbound_tag")
    return None, None, None


def find_hysteria_client_email(
    lines: List[str],
    dst_ip: Optional[str],
    dst_port: int,
    max_age_sec: int = 300
) -> Optional[str]:
    """Searches Hysteria 2 log lines for client user/email via sentinel-core."""
    import json
    lines_json = json.dumps(lines)
    try:
        email = _ffi_call_str("SentinelFindHysteriaClientEmail", lines_json, dst_ip or "", int(dst_port), int(max_age_sec))
        if email:
            return email.strip()
    except Exception as e:
        logger.debug("FFI find_hysteria_client_email error: %s", e)

    args = [
        "security", "find-proxy-client",
        "--core", "hysteria",
        "--lines", lines_json,
        "--dst-ip", dst_ip or "",
        "--dpt", str(dst_port),
        "--max-age", str(max_age_sec)
    ]
    res = run_core_command(args)
    if isinstance(res, dict) and res.get("email"):
        return res["email"].strip()
    return None


def find_client_ip_for_email_in_hysteria_log(
    lines: List[str],
    email: str,
    max_age_sec: int = 300
) -> Optional[str]:
    """Searches Hysteria 2 log lines for latest client IP by email via sentinel-core."""
    import json
    lines_json = json.dumps(lines)
    try:
        ip = _ffi_call_str("SentinelFindClientIPForEmail", lines_json, email, int(max_age_sec))
        if ip:
            return ip.strip()
    except Exception as e:
        logger.debug("FFI find_client_ip_for_email_in_hysteria_log error: %s", e)

    args = [
        "security", "find-proxy-client",
        "--core", "hysteria-ip",
        "--lines", lines_json,
        "--email", email,
        "--max-age", str(max_age_sec)
    ]
    res = run_core_command(args)
    if isinstance(res, dict) and res.get("ip"):
        return res["ip"].strip()
    return None

