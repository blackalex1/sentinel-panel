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

def update_online_emails():
    """Queries online clients from sentinel-core supervisor and updates the cache in the background."""
    global _last_traffic_check_time, _online_emails
    
    emails = []
    
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

    # 2. Add active IP cache if available
    try:
        from backend.scheduler import ACTIVE_IP_CACHE
        if ACTIVE_IP_CACHE:
            emails.extend(ACTIVE_IP_CACHE.keys())
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

@router.post("/panel/api/clients/onlines")
async def online_clients_api(request: Request):
    if not backend.routes.clients.check_auth(request):
        return backend.routes.clients.decoy_response()
    return {"success": True, "obj": _online_emails}

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
