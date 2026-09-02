import time
import json
import logging
from backend.database import db_session
from backend.models import ClientStats
from backend.audit import log_action

def get_user_traffic_from_db(email: str) -> tuple:
    """Calculates cumulative downloaded (down) and uploaded (up) bytes for email/token across all inbounds from DB."""
    down, up = 0, 0
    try:
        with db_session() as session:
            records = session.query(ClientStats).filter_by(email=email).all()
            if not records:
                records = session.query(ClientStats).filter(
                    (ClientStats.email.ilike(email)) | (ClientStats.client_uuid_or_pwd == email)
                ).all()
            for r in records:
                down += r.down
                up += r.up
    except Exception as e:
        logging.error(f"[User Stats Alert] Error querying traffic: {e}")
    return down, up

def get_singbox_user_traffic(email: str) -> tuple:
    """Calculates cumulative downloaded and uploaded bytes for Sing-box email across all inbounds."""
    return get_user_traffic_from_db(email)

def get_xray_user_traffic(email: str) -> tuple:
    """Calculates cumulative downloaded and uploaded bytes for Xray email across all inbounds."""
    return get_user_traffic_from_db(email)

def get_user_traffic_bytes(username: str) -> tuple:
    """Queries user traffic via sentinel-core unified traffic snapshot."""
    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic_data = get_unified_traffic()
        if traffic_data and isinstance(traffic_data, dict):
            user_stats = traffic_data.get(username, {})
            if isinstance(user_stats, dict):
                return user_stats.get("downBytes", 0), user_stats.get("upBytes", 0)
    except Exception as e:
        logging.error(f"[Stats Alert] Error querying traffic via sentinel-core: {e}")
    return 0, 0

def parse_ip_from_addr(addr: str) -> str:
    if not addr:
        return ""
    addr = addr.strip()
    if addr.startswith("["):
        idx = addr.find("]")
        if idx != -1:
            return addr[1:idx]
    if addr.count(":") > 1:
        return addr
    parts = addr.rsplit(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return addr
