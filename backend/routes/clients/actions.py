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
    
    # 1. Primary: query online emails and active sessions directly from sentinel-core Go session tracker
    try:
        from backend.sentinel_core_bridge import get_online_emails_core, get_active_sessions, get_unified_traffic
        core_emails = get_online_emails_core()
        if core_emails:
            emails.extend(core_emails)

        core_sessions = get_active_sessions()
        if core_sessions and isinstance(core_sessions, list):
            from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
            for s in core_sessions:
                s_email = s.get("email")
                s_ip = s.get("ip")
                if s_email:
                    emails.append(s_email)
                    if s_ip:
                        if s_email not in ACTIVE_IP_CACHE:
                            ACTIVE_IP_CACHE[s_email] = {}
                        ACTIVE_IP_CACHE[s_email][s_ip] = s.get("last_seen_at", now_ts)

        traffic_data = get_unified_traffic()
        if traffic_data and isinstance(traffic_data, dict):
            for email, stats in traffic_data.items():
                if isinstance(stats, dict) and (stats.get("online") or stats.get("connections", 0) > 0):
                    emails.append(email)
    except Exception as e:
        logging.debug(f"Querying native sessions from sentinel-core: {e}")

    # 2. Check ACTIVE_IP_CACHE
    try:
        from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
        if ACTIVE_IP_CACHE:
            for email, ip_map in list(ACTIVE_IP_CACHE.items()):
                if isinstance(ip_map, dict):
                    if any(ts >= cutoff_ts for ts in ip_map.values()):
                        emails.append(email)
                elif ip_map:
                    emails.append(email)
    except Exception:
        pass

    # Map collected tokens/UUIDs/emails to actual enabled ClientStats.email
    try:
        from backend.database import db_session
        from backend.models import ClientStats
        with db_session() as session:
            clients_all = session.query(ClientStats).filter_by(enable=1).all()
            enabled_emails = {c.email for c in clients_all}
            uuid_to_email = {c.client_uuid_or_pwd: c.email for c in clients_all if c.client_uuid_or_pwd}

        matched_emails = set()
        for em in emails:
            clean_em = str(em).strip("[]():,\"'")
            if clean_em in enabled_emails:
                matched_emails.add(clean_em)
            elif clean_em in uuid_to_email:
                matched_emails.add(uuid_to_email[clean_em])
            else:
                # Case-insensitive / prefix matching
                for c in clients_all:
                    if c.email.lower() == clean_em.lower() or (c.client_uuid_or_pwd and c.client_uuid_or_pwd.lower() == clean_em.lower()):
                        matched_emails.add(c.email)
                        break
                    elif c.email.lower().startswith(f"{clean_em.lower()}@") or clean_em.lower().startswith(f"{c.email.lower()}@"):
                        matched_emails.add(c.email)
                        break
        _online_emails = list(matched_emails)
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
