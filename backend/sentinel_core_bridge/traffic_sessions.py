import logging
from typing import Dict, Any, List

from backend.sentinel_core_bridge.ffi import (
    _ffi_call_str,
    _ffi_call_json,
    run_core_command,
)

logger = logging.getLogger(__name__)


def get_unified_traffic() -> Dict[str, Any]:
    """Returns aggregated traffic and active clients across all cores via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetUnifiedTraffic")
        if isinstance(res, dict) and "error" not in res:
            return res
    except Exception as e:
        logger.debug("FFI get_unified_traffic error: %s", e)

    res = run_core_command(["supervisor", "traffic"])
    if isinstance(res, dict) and "error" not in res:
        return res
    return {}


def get_active_sessions() -> List[Dict[str, Any]]:
    """Returns active client sessions tracked natively in Go sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetActiveSessions")
        if isinstance(res, list):
            return res
    except Exception:
        pass
    return []


def get_online_emails_core() -> List[str]:
    """Returns active online client emails tracked natively in Go sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetOnlineEmails")
        if isinstance(res, list):
            return [str(x) for x in res if x]
    except Exception:
        pass
    return []


def get_recent_session_events(since_ts: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """Returns recent connect/disconnect events tracked natively in Go sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetRecentSessionEvents", since_ts, limit)
        if isinstance(res, list):
            return res
    except Exception:
        pass
    return []


def register_external_connect(core: str, email: str, ip: str) -> None:
    """Registers an external connection (e.g. Hysteria HTTP Auth) in Go core session tracker."""
    try:
        _ffi_call_str("SentinelRegisterExternalConnect", core, email, ip)
    except Exception:
        pass


def register_hysteria_port(port: int) -> bool:
    """Registers a Hysteria 2 admin port with sentinel-core supervisor for telemetry monitoring."""
    if port <= 0:
        return False
    try:
        res = _ffi_call_json("SentinelRegisterHysteriaPort", int(port))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI register_hysteria_port error: %s", e)
    return True


def kick_client(email: str) -> bool:
    """Disconnects/kicks a client session across all cores via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelKickClient", email)
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI kick_client error: %s", e)

    res = run_core_command(["supervisor", "kick", "--client", email])
    if isinstance(res, dict) and res.get("success") is True:
        return True
    return False
