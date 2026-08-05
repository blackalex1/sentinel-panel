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
    """Queries online clients from Xray and Hysteria 2 and updates the cache in the background."""
    global _last_traffic_check_time, _online_emails
    from backend.xray import is_xray_running, log_xray_errors
    
    emails = []
    
    # 1. Query Xray online clients
    if is_xray_running():
        try:
            # Primary: use active IP cache from access log parsing (highly accurate last 3m activity)
            from backend.scheduler import parse_recent_xray_ips, ACTIVE_IP_CACHE
            try:
                parse_recent_xray_ips()
                emails.extend(ACTIVE_IP_CACHE.keys())
            except Exception as e:
                logging.error(f"Error parsing recent xray IPs for online check: {e}")

            # Fallback: query statsquery API for user list
            cmd = [str(XRAY_BIN_PATH), "api", "statsquery", "--server=127.0.0.1:10085"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=3)  # nosec B603
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if not ACTIVE_IP_CACHE:
                    for stat in data.get("stat", []):
                        name = stat.get("name", "")
                        parts = name.split(">>>")
                        if len(parts) == 4 and parts[0] == "user":
                            emails.append(parts[1])
        except Exception as e:
            logging.error(f"Error querying online Xray clients in background: {e}")
            log_xray_errors()
            
    # 2. Query Hysteria 2 online clients
    try:
        from backend.database import get_all_inbounds
        inbounds = get_all_inbounds()
        hysteria_inbounds = [ib for ib in inbounds if ib["protocol"] == "hysteria2" and ib["enable"]]
        import requests
        for ib in hysteria_inbounds:
            ib_id = ib["id"]
            admin_port = 10100 + ib_id
            
            # Query /traffic endpoint
            url_traffic = f"http://127.0.0.1:{admin_port}/traffic"
            try:
                response = requests.get(url_traffic, timeout=1)
                if response.status_code == 200:
                    traffic_data = response.json()
                    # Hysteria 2 /traffic returns a dictionary of active client emails
                    emails.extend(traffic_data.keys())
            except Exception:
                pass

            # Query /online endpoint to count current active connections
            url_online = f"http://127.0.0.1:{admin_port}/online"
            try:
                response = requests.get(url_online, timeout=1)
                if response.status_code == 200:
                    online_data = response.json()
                    # Hysteria 2 /online returns {"user_id": connection_count}
                    # We extend emails if connection count is greater than 0
                    emails.extend([k for k, v in online_data.items() if v > 0])
            except Exception:
                pass
    except Exception as e:
        logging.error(f"Error querying online Hysteria 2 clients in background: {e}")

    # 3. Query Sing-box online clients
    try:
        from backend.singbox import is_singbox_running
        if is_singbox_running():
            from backend.scheduler import parse_recent_singbox_ips, ACTIVE_IP_CACHE
            try:
                parse_recent_singbox_ips()
                emails.extend(ACTIVE_IP_CACHE.keys())
            except Exception as e:
                logging.error(f"Error parsing recent singbox IPs for online check: {e}")

            from backend.singbox.service import get_singbox_client_traffic_stats
            sb_stats = get_singbox_client_traffic_stats()
            if sb_stats:
                emails.extend(sb_stats.keys())
    except Exception as e:
        logging.error(f"Error querying online Sing-box clients in background: {e}")

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
