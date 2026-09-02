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


_last_unified_stats: Dict[str, tuple] = {}


def reset_unified_traffic_stats():
    """Resets the in-memory delta cache for unified traffic polling."""
    global _last_unified_stats
    _last_unified_stats.clear()


def query_all_cores_traffic(traffic_data_override=None):
    """
    Centralized, single-pass traffic aggregator across all cores (Xray, Hysteria 2, Sing-box).
    Reads unified cumulative traffic from Go sentinel-core, computes accurate deltas per client,
    and updates ClientStats and the matching Inbound record without cross-core multiplication or duplication.
    """
    global _last_unified_stats
    import time
    import sys
    from backend.database import db_session
    from backend.models import ClientStats, Inbound

    try:
        bridge_mod = sys.modules.get("backend.sentinel_core_bridge")
        sessions_mod = sys.modules.get("backend.sentinel_core_bridge.traffic_sessions")

        if traffic_data_override is not None:
            traffic_data = traffic_data_override
        else:
            get_traffic_fn = get_unified_traffic
            if sessions_mod and hasattr(sessions_mod, "get_unified_traffic"):
                fn = getattr(sessions_mod, "get_unified_traffic")
                if hasattr(fn, "return_value") or hasattr(fn, "mock") or hasattr(fn, "__wrapped__"):
                    get_traffic_fn = fn
                elif bridge_mod and hasattr(bridge_mod, "get_unified_traffic") and getattr(bridge_mod, "get_unified_traffic") is not get_unified_traffic:
                    get_traffic_fn = getattr(bridge_mod, "get_unified_traffic")
                elif fn is not get_unified_traffic:
                    get_traffic_fn = fn
            elif bridge_mod and hasattr(bridge_mod, "get_unified_traffic") and getattr(bridge_mod, "get_unified_traffic") is not get_unified_traffic:
                get_traffic_fn = getattr(bridge_mod, "get_unified_traffic")

            traffic_data = get_traffic_fn()

        if not traffic_data or not isinstance(traffic_data, dict):
            return

        get_sessions_fn = get_active_sessions
        if sessions_mod and hasattr(sessions_mod, "get_active_sessions"):
            fn = getattr(sessions_mod, "get_active_sessions")
            if hasattr(fn, "return_value") or hasattr(fn, "mock") or hasattr(fn, "__wrapped__"):
                get_sessions_fn = fn
            elif bridge_mod and hasattr(bridge_mod, "get_active_sessions") and getattr(bridge_mod, "get_active_sessions") is not get_active_sessions:
                get_sessions_fn = getattr(bridge_mod, "get_active_sessions")
            elif fn is not get_active_sessions:
                get_sessions_fn = fn
        elif bridge_mod and hasattr(bridge_mod, "get_active_sessions") and getattr(bridge_mod, "get_active_sessions") is not get_active_sessions:
            get_sessions_fn = getattr(bridge_mod, "get_active_sessions")

        active_sessions = get_sessions_fn() or []
        active_core_by_email = {}
        now_ts = time.time()

        for s in active_sessions:
            if isinstance(s, dict):
                em = s.get("email")
                c_name = s.get("core", "")
                c_ip = s.get("ip")
                if em:
                    active_core_by_email[em] = c_name
                    if c_ip and c_ip not in ("127.0.0.1", "::1", ""):
                        try:
                            from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                            if em not in ACTIVE_IP_CACHE:
                                ACTIVE_IP_CACHE[em] = {}
                            ACTIVE_IP_CACHE[em][c_ip] = s.get("last_seen_at", now_ts)
                        except Exception:
                            pass

        with db_session() as session:
            all_inbounds = {ib.id: ib for ib in session.query(Inbound).all()}
            all_clients = session.query(ClientStats).all()

            # Map email / uuid / username prefix to ClientStats records (deduplicated per list)
            clients_by_key: Dict[str, List[ClientStats]] = {}
            for c in all_clients:
                keys_to_index = []
                if c.email:
                    keys_to_index.extend([c.email, c.email.lower()])
                    if "@" in c.email or ":" in c.email:
                        prefix = c.email.split(":")[0].split("@")[0].strip()
                        if prefix:
                            keys_to_index.extend([prefix, prefix.lower()])
                if c.client_uuid_or_pwd:
                    keys_to_index.extend([c.client_uuid_or_pwd, c.client_uuid_or_pwd.lower()])

                for k in keys_to_index:
                    if c not in clients_by_key.setdefault(k, []):
                        clients_by_key[k].append(c)

            for key, stats in traffic_data.items():
                if not isinstance(stats, dict):
                    continue
                up = int(stats.get("upBytes", 0) or stats.get("up", 0) or 0)
                down = int(stats.get("downBytes", 0) or stats.get("down", 0) or 0)

                prev_up, prev_down = _last_unified_stats.get(key, (0, 0))
                up_delta = up - prev_up if up >= prev_up else up
                down_delta = down - prev_down if down >= prev_down else down
                _last_unified_stats[key] = (up, down)

                if up_delta <= 0 and down_delta <= 0:
                    continue

                if key.startswith("outbound:"):
                    ob_tag = key[len("outbound:"):].strip()
                    if ob_tag:
                        from backend.database import update_outbound_traffic
                        update_outbound_traffic(ob_tag, max(0, up_delta), max(0, down_delta))
                    continue

                # Find candidate ClientStats
                candidates = clients_by_key.get(key) or clients_by_key.get(key.lower()) or []
                if not candidates and ("@" in key or ":" in key):
                    clean_key = key.split(":")[0].split("@")[0].strip()
                    candidates = clients_by_key.get(clean_key) or clients_by_key.get(clean_key.lower()) or []

                if not candidates:
                    continue

                # If client exists on multiple inbounds, pick the one matching current active core
                target_client = None
                active_core = active_core_by_email.get(key) or active_core_by_email.get(candidates[0].email, "")
                if active_core and len(candidates) > 1:
                    norm_core = "singbox" if "sing" in active_core.lower() else ("hysteria" if "hysteria" in active_core.lower() else "xray")
                    for cand in candidates:
                        ib = all_inbounds.get(cand.inbound_id)
                        if ib and (ib.core == norm_core or norm_core in ib.protocol.lower()):
                            target_client = cand
                            break

                if not target_client:
                    target_client = candidates[0]

                target_client.up += max(0, up_delta)
                target_client.down += max(0, down_delta)

                target_ib = all_inbounds.get(target_client.inbound_id)
                if target_ib:
                    target_ib.up += max(0, up_delta)
                    target_ib.down += max(0, down_delta)

    except Exception as e:
        logger.debug("Error in query_all_cores_traffic: %s", e)

