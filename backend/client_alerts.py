import time
import json
import logging
import re
import requests
from backend.database import db_session, get_all_inbounds
from backend.models import ClientStats
from backend.audit import log_action
from backend.hysteria.service import hysteria_processes

# In-memory session states
# active_xray_sessions = { (email, ip): { 'last_seen_at': float, 'started_at': float } }
active_xray_sessions = {}
# active_singbox_sessions = { (email, ip): { 'last_seen_at': float, 'started_at': float } }
active_singbox_sessions = {}

def get_singbox_user_traffic(email: str) -> tuple:
    """Calculates cumulative uploaded (tx) and downloaded (rx) bytes for Sing-box email across all inbounds."""
    tx, rx = 0, 0
    try:
        with db_session() as session:
            records = session.query(ClientStats).filter_by(email=email).all()
            for r in records:
                tx += r.up
                rx += r.down
    except Exception as e:
        logging.error(f"[Singbox Stats Alert] Error querying traffic: {e}")
    return tx, rx

def process_singbox_connection_event(username: str, client_ip: str):
    """Processes new client connection on Sing-box and logs singbox_connect action."""
    if not username or not client_ip:
        return
    client_ip = parse_ip_from_addr(client_ip)
    key = (username, client_ip)
    now = time.time()
    if key not in active_singbox_sessions:
        tx, rx = get_singbox_user_traffic(username)
        log_action(
            username="system",
            action="singbox_connect",
            target=client_ip,
            details=json.dumps({"username": username, "tx": tx, "rx": rx})
        )
        active_singbox_sessions[key] = {
            'started_at': now,
            'last_seen_at': now
        }
    else:
        active_singbox_sessions[key]['last_seen_at'] = now

def process_singbox_log_line(line: str):
    """Parses Singbox accepted log lines to track new connections."""
    if "accepted" not in line:
        return
        
    try:
        email = None
        if "email: " in line:
            email_part = line.split("email: ")
            if len(email_part) >= 2:
                email = email_part[1].strip()
        
        match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+\s+accepted", line)
        if not match:
            match = re.search(r"from\s+\[([^\]]+)\]", line)
        if not match:
            match = re.search(r"from\s+(?:tcp:|udp:)?([^:\s]+)", line)
        if not match:
            return
            
        client_ip = match.group(1)
        if email:
            process_singbox_connection_event(email, client_ip)
    except Exception as e:
        logging.error(f"[Singbox Alert Tracker] Error parsing log line: {e}")

def check_singbox_inactivity_timeouts():
    """Checks active Singbox sessions. Triggers disconnect event if inactive for 3 minutes."""
    now = time.time()
    for (email, ip), session in list(active_singbox_sessions.items()):
        if now - session['last_seen_at'] > 180.0:
            del active_singbox_sessions[(email, ip)]
            
            duration_sec = int(now - session['started_at']) - 180
            duration_sec = max(0, duration_sec)
            
            if duration_sec < 60:
                duration_str = f"{duration_sec} сек"
            elif duration_sec < 3600:
                duration_str = f"{duration_sec // 60} мин {duration_sec % 60} сек"
            else:
                duration_str = f"{duration_sec // 3600} ч {(duration_sec % 3600) // 60} мин"
                
            tx, rx = get_singbox_user_traffic(email)
            log_action(
                username="system",
                action="singbox_disconnect",
                target=ip,
                details=json.dumps({"username": email, "tx": tx, "rx": rx, "duration": duration_str})
            )

def get_xray_user_traffic(email: str) -> tuple:
    """Calculates cumulative uploaded (tx) and downloaded (rx) bytes for Xray email across all inbounds."""
    tx, rx = 0, 0
    try:
        with db_session() as session:
            records = session.query(ClientStats).filter_by(email=email).all()
            for r in records:
                tx += r.up
                rx += r.down
    except Exception as e:
        logging.error(f"[Xray Stats Alert] Error querying traffic: {e}")
    return tx, rx

def get_user_traffic_bytes(username: str) -> tuple:
    """Queries Hysteria 2 API stats locally for active connections/traffic."""
    tx, rx = 0, 0
    try:
        for ib_id, proc in list(hysteria_processes.items()):
            if proc.poll() is None:
                admin_port = 10100 + ib_id
                url = f"http://127.0.0.1:{admin_port}/traffic"
                try:
                    r = requests.get(url, timeout=0.5)
                    if r.status_code == 200:
                        stats = r.json()
                        user_stats = stats.get(username)
                        if user_stats:
                            tx += user_stats.get("tx", 0)
                            rx += user_stats.get("rx", 0)
                except Exception:
                    pass
    except Exception as e:
        logging.error(f"[Hysteria Stats Alert] Error querying traffic: {e}")
    return tx, rx

def process_xray_log_line(line: str):
    """Parses Xray accepted log lines to track new connections."""
    if "accepted" not in line or "email: " not in line:
        return
        
    try:
        email_part = line.split("email: ")
        if len(email_part) < 2:
            return
        email = email_part[1].strip()
        
        match = re.search(r"from\s+\[([^\]]+)\]", line)
        if not match:
            match = re.search(r"from\s+(?:tcp:|udp:)?([^:\s]+)", line)
        if not match:
            return
        client_ip = match.group(1)
        
        key = (email, client_ip)
        now = time.time()
        
        if key not in active_xray_sessions:
            tx, rx = get_xray_user_traffic(email)
            log_action(
                username="system",
                action="xray_connect",
                target=client_ip,
                details=json.dumps({"username": email, "tx": tx, "rx": rx})
            )
            active_xray_sessions[key] = {
                'started_at': now,
                'last_seen_at': now
            }
        else:
            active_xray_sessions[key]['last_seen_at'] = now
            
    except Exception as e:
        logging.error(f"[Xray Alert Tracker] Error parsing log line: {e}")

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

def process_hysteria_log_line(line: str):
    """Parses Hysteria log lines to track connections/disconnections immediately."""
    try:
        if "client connected" in line:
            match = re.search(r"client connected\s+(\{.*\})", line)
            if match:
                data = json.loads(match.group(1))
                username = data.get("id") or "Unknown"
                client_ip = parse_ip_from_addr(data.get("addr", ""))
                
                # Update ACTIVE_IP_CACHE for IP limiting
                try:
                    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                    if username not in ACTIVE_IP_CACHE:
                        ACTIVE_IP_CACHE[username] = {}
                    ACTIVE_IP_CACHE[username][client_ip] = time.time()
                except Exception as ex:
                    logging.error(f"Error updating ACTIVE_IP_CACHE on Hysteria connect: {ex}")
                
                tx, rx = get_user_traffic_bytes(username)
                log_action(
                    username="system",
                    action="hysteria_connect",
                    target=client_ip,
                    details=json.dumps({"username": username, "tx": tx, "rx": rx})
                )
        elif "client disconnected" in line:
            match = re.search(r"client disconnected\s+(\{.*\})", line)
            if match:
                data = json.loads(match.group(1))
                username = data.get("id") or "Unknown"
                client_ip = parse_ip_from_addr(data.get("addr", ""))
                
                # Remove from ACTIVE_IP_CACHE
                try:
                    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                    if username in ACTIVE_IP_CACHE and client_ip in ACTIVE_IP_CACHE[username]:
                        del ACTIVE_IP_CACHE[username][client_ip]
                        if not ACTIVE_IP_CACHE[username]:
                            del ACTIVE_IP_CACHE[username]
                except Exception as ex:
                    logging.error(f"Error updating ACTIVE_IP_CACHE on Hysteria disconnect: {ex}")
                
                # Tiny wait for stats API to update values
                time.sleep(0.1)
                tx, rx = get_user_traffic_bytes(username)
                log_action(
                    username="system",
                    action="hysteria_disconnect",
                    target=client_ip,
                    details=json.dumps({"username": username, "tx": tx, "rx": rx})
                )
    except Exception as e:
        logging.error(f"[Hysteria Alert Tracker] Error parsing log line: {e}")

def check_xray_inactivity_timeouts():
    """Checks active Xray sessions. Triggers disconnect event if inactive for 3 minutes."""
    now = time.time()
    for (email, ip), session in list(active_xray_sessions.items()):
        if now - session['last_seen_at'] > 180.0:
            del active_xray_sessions[(email, ip)]
            
            duration_sec = int(now - session['started_at']) - 180
            duration_sec = max(0, duration_sec)
            
            if duration_sec < 60:
                duration_str = f"{duration_sec} сек"
            elif duration_sec < 3600:
                duration_str = f"{duration_sec // 60} мин {duration_sec % 60} сек"
            else:
                duration_str = f"{duration_sec // 3600} ч {(duration_sec % 3600) // 60} мин"
                
            tx, rx = get_xray_user_traffic(email)
            log_action(
                username="system",
                action="xray_disconnect",
                target=ip,
                details=json.dumps({"username": email, "tx": tx, "rx": rx, "duration": duration_str})
            )
