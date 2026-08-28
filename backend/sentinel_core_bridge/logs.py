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
