import json
import time
import subprocess
import logging
from fastapi import APIRouter, Request
from backend.config import XRAY_BIN_PATH
import backend.routes.clients

router = APIRouter()

# Временный кэш трафика для вычисления онлайна
_last_traffic_check_time = 0
_online_emails = []

import asyncio

def update_online_emails():
    """Queries online clients from sentinel-core supervisor and updates the cache in the background."""
    global _last_traffic_check_time, _online_emails
    
    emails = []
    now_ts = time.time()
    cutoff_ts = now_ts - 180  # 3 minutes window
    
    # 1. Primary: query unified traffic from sentinel-core supervisor
    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic_data = get_unified_traffic()
        if traffic_data and isinstance(traffic_data, dict):
            for email, stats in traffic_data.items():
                if isinstance(stats, dict) and (stats.get("online") or stats.get("connections", 0) > 0):
                    emails.append(email)
    except Exception as e:
        logging.error(f"Error querying unified traffic from sentinel-core: {e}")

    # 2. Query Sing-box Clash API directly (127.0.0.1:9090/connections)
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:9090/connections", headers={"User-Agent": "SentinelPanel"})
        with urllib.request.urlopen(req, timeout=0.8) as response:
            if response.status == 200:
                raw_data = response.read().decode("utf-8", errors="ignore")
                data = json.loads(raw_data)
                for conn in data.get("connections", []):
                    meta = conn.get("metadata", {})
                    user = (
                        meta.get("user") or meta.get("username") or meta.get("client") or
                        meta.get("name") or meta.get("email") or meta.get("clientUser") or
                        meta.get("inboundUser") or meta.get("auth_user") or conn.get("user") or ""
                    )
                    if user:
                        emails.append(user)
                        src_ip = meta.get("sourceIP") or meta.get("source_ip") or "127.0.0.1"
                        try:
                            from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                            if user not in ACTIVE_IP_CACHE:
                                ACTIVE_IP_CACHE[user] = {}
                            ACTIVE_IP_CACHE[user][src_ip] = now_ts
                        except Exception:
                            pass
    except Exception:
        pass

    # 3. Trigger log parsers to ensure ACTIVE_IP_CACHE is freshly populated
    try:
        from backend.scheduler_jobs.limits import parse_recent_singbox_ips, parse_recent_hysteria_ips, ACTIVE_IP_CACHE
        parse_recent_singbox_ips()
        parse_recent_hysteria_ips()
        if ACTIVE_IP_CACHE:
            for email, ip_map in list(ACTIVE_IP_CACHE.items()):
                if isinstance(ip_map, dict):
                    if any(ts >= cutoff_ts for ts in ip_map.values()):
                        emails.append(email)
                elif ip_map:
                    emails.append(email)
    except Exception:
        pass

    # 4. Add active Xray sessions if available
    try:
        from backend.client_alerts import active_xray_sessions
        if active_xray_sessions:
            for (em, _), sess in list(active_xray_sessions.items()):
                if isinstance(sess, dict) and (now_ts - sess.get('last_seen_at', 0) <= 180):
                    emails.append(em)
    except Exception:
        pass

    # Keep only emails of clients that are enabled in the database
    try:
        from backend.database import db_session
        from backend.models import ClientStats
        with db_session() as session:
            enabled_emails = {c.email for c in session.query(ClientStats).filter_by(enable=1).all()}
        _online_emails = list(set(emails) & enabled_emails)
    except Exception as e:
        logging.error(f"Error filtering online emails by enabled status: {e}")
        _online_emails = list(set(emails))
    _last_traffic_check_time = time.time()
    return _online_emails

@router.post("/panel/api/clients/onlines")
async def online_clients_api(request: Request):
    if not backend.routes.clients.check_auth(request):
        return backend.routes.clients.decoy_response()
    
    # Auto-refresh if cache is older than 2 seconds
    if time.time() - _last_traffic_check_time > 2:
        await asyncio.to_thread(update_online_emails)
        
    return {"success": True, "obj": _online_emails, "onlines": _online_emails}

@router.get("/api/clients/{email}/traffic")
async def get_client_daily_traffic_api(request: Request, email: str):
    if not backend.routes.clients.check_auth(request):
        return backend.routes.clients.decoy_response()
    
    from backend.database import db_session
    from backend.models import ClientTrafficDaily
    import datetime
    
    with db_session() as session:
        # Get traffic records from the last 30 days, sorted by date ascending
        thirty_days_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        records = session.query(ClientTrafficDaily).filter(
            ClientTrafficDaily.email == email,
            ClientTrafficDaily.date >= thirty_days_ago
        ).order_by(ClientTrafficDaily.date.asc()).all()
        
        result = [{
            "date": rec.date,
            "up": rec.up,
            "down": rec.down
        } for rec in records]
        
        return {"success": True, "obj": result}
