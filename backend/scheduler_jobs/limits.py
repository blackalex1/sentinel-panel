import time
import datetime
import logging
import asyncio
from backend.models import ClientStats, Inbound
from backend.utils import read_last_lines
from backend.database import db_session

# Cache of active IPs in memory for limit checks: { email: { ip: timestamp } }
ACTIVE_IP_CACHE = {}

# Notification timers to prevent Telegram spam
_last_notified_blocks = {}
_last_sb_client_traffic = {}

def parse_recent_xray_ips():
    """Scans Xray access.log and collects unique IPs for each client in the last 3 minutes."""
    global ACTIVE_IP_CACHE
    import backend.scheduler
    
    now_ts = time.time()
    cutoff_ts = now_ts - 180  # 3 minutes
    
    # Clear expired IPs
    for email in list(ACTIVE_IP_CACHE.keys()):
        ip_map = ACTIVE_IP_CACHE[email]
        for ip in list(ip_map.keys()):
            if ip_map[ip] < cutoff_ts:
                del ip_map[ip]
        if not ip_map:
            del ACTIVE_IP_CACHE[email]
            
    # Incorporate active client IPs from sentinel-core bridge
    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic = get_unified_traffic()
        if traffic and isinstance(traffic, dict):
            for email, stats in traffic.items():
                if isinstance(stats, dict) and "activeIPs" in stats:
                    for ip in stats["activeIPs"]:
                        if email not in ACTIVE_IP_CACHE:
                            ACTIVE_IP_CACHE[email] = {}
                        ACTIVE_IP_CACHE[email][ip] = now_ts
    except Exception:
        pass

    xray_log_path = backend.scheduler.XRAY_LOG_PATH
    if not xray_log_path.exists():
        return
            
    try:
        from backend.sentinel_core_bridge import get_core_logs
        lines = get_core_logs(str(xray_log_path), 1000)
        if not lines:
            lines = read_last_lines(xray_log_path, 1000)
            
        for line in lines:
            if "accepted" not in line or "email: " not in line:
                continue
                
            parts = line.strip().split()
            if len(parts) < 4:
                continue
                
            try:
                log_time_str = parts[0] + " " + parts[1]
                log_time = datetime.datetime.strptime(log_time_str, "%Y/%m/%d %H:%M:%S")
                log_ts = log_time.timestamp()
            except Exception:
                log_ts = now_ts  # fallback
                
            if log_ts < cutoff_ts:
                continue
                
            email_part = line.split("email: ")
            if len(email_part) < 2:
                continue
            email = email_part[1].strip()
            
            import re
            match = re.search(r"from\s+\[([^\]]+)\]", line)
            if not match:
                match = re.search(r"from\s+(?:tcp:|udp:)?([^:\s]+)", line)
            if not match:
                continue
            ip = match.group(1)
                
            if email not in ACTIVE_IP_CACHE:
                ACTIVE_IP_CACHE[email] = {}
            ACTIVE_IP_CACHE[email][ip] = log_ts
            
    except Exception as e:
        logging.error(f"[Scheduler] Error parsing Xray access logs: {e}")

def parse_recent_singbox_ips():
    """Scans Sing-box singbox.log and collects unique IPs/activity for each client in the last 3 minutes."""
    global ACTIVE_IP_CACHE
    from backend.config import SINGBOX_LOG_PATH
    
    now_ts = time.time()
    cutoff_ts = now_ts - 180  # 3 minutes
    
    # Clear expired IPs
    for email in list(ACTIVE_IP_CACHE.keys()):
        ip_map = ACTIVE_IP_CACHE[email]
        for ip in list(ip_map.keys()):
            if ip_map[ip] < cutoff_ts:
                del ip_map[ip]
        if not ip_map:
            del ACTIVE_IP_CACHE[email]
            
    # Incorporate active client IPs from sentinel-core bridge
    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic = get_unified_traffic()
        if traffic and isinstance(traffic, dict):
            for email, stats in traffic.items():
                if isinstance(stats, dict) and "activeIPs" in stats:
                    for ip in stats["activeIPs"]:
                        if email not in ACTIVE_IP_CACHE:
                            ACTIVE_IP_CACHE[email] = {}
                        ACTIVE_IP_CACHE[email][ip] = now_ts
    except Exception:
        pass

    if not SINGBOX_LOG_PATH.exists():
        return
            
    try:
        from backend.database import db_session
        from backend.models import ClientStats
        with db_session() as session:
            client_emails = {c.email for c in session.query(ClientStats).filter_by(enable=1).all()}

        if not client_emails:
            return

        from backend.sentinel_core_bridge import get_core_logs
        lines = get_core_logs(str(SINGBOX_LOG_PATH), 1000)
        if not lines:
            lines = read_last_lines(SINGBOX_LOG_PATH, 1000)

        import re
        ip_pattern = re.compile(r"(?:from|client)\s+(?:\[([^\]]+)\]|([0-9a-fA-F.:]+?)(?::\d+)?(?:\s|$))")
        tz_pattern = re.compile(r"([+-]\d{4})\s+(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})")
        time_pattern = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})")
        conn_ip_map = {}
            
        for line in lines:
            if not line.strip():
                continue

            log_ts = now_ts
            tz_match = tz_pattern.search(line)
            if tz_match:
                try:
                    tz_str = tz_match.group(1)
                    time_str = tz_match.group(2).replace("-", "/")
                    dt = datetime.datetime.strptime(f"{time_str} {tz_str}", "%Y/%m/%d %H:%M:%S %z")
                    log_ts = dt.timestamp()
                except Exception:
                    pass
            else:
                time_match = time_pattern.search(line)
                if time_match:
                    try:
                        time_str = time_match.group(1).replace("-", "/")
                        dt_naive = datetime.datetime.strptime(time_str[:19], "%Y/%m/%d %H:%M:%S")
                        ts_local = dt_naive.timestamp()
                        ts_utc = dt_naive.replace(tzinfo=datetime.timezone.utc).timestamp()
                        if abs(now_ts - ts_utc) < abs(now_ts - ts_local):
                            log_ts = ts_utc
                        else:
                            log_ts = ts_local
                    except Exception:
                        pass

            if log_ts < cutoff_ts:
                continue

            conn_id = None
            conn_id_match = re.search(r"\[(\d+)\s+\d+m?s\]", line)
            if conn_id_match:
                conn_id = conn_id_match.group(1)

            # 1. Capture source IP from "inbound connection from <ip>"
            if "inbound connection from" in line or "from " in line:
                match = ip_pattern.search(line)
                if match:
                    src_ip = match.group(1) or match.group(2) or ""
                    if ":" in src_ip and not src_ip.startswith("["):
                        parts_ip = src_ip.split(":")
                        if len(parts_ip) == 2:
                            src_ip = parts_ip[0]
                    if src_ip and conn_id:
                        conn_ip_map[conn_id] = (src_ip, log_ts)

            # 2. Capture email
            found_email = None
            for token in line.split():
                clean_token = token.strip("[]():,\"'")
                if clean_token in client_emails:
                    found_email = clean_token
                    break

            if found_email is not None:
                ip = conn_ip_map.get(conn_id, ("127.0.0.1", log_ts))[0] if conn_id else "127.0.0.1"
                if found_email not in ACTIVE_IP_CACHE:
                    ACTIVE_IP_CACHE[found_email] = {}
                ACTIVE_IP_CACHE[found_email][ip] = log_ts
            
    except Exception as e:
        logging.error(f"[Scheduler] Error parsing Sing-box logs: {e}")

def parse_recent_hysteria_ips():
    """Scans Hysteria 2 log files and collects active IPs/sessions for each client in the last 3 minutes."""
    global ACTIVE_IP_CACHE
    import json
    import re
    from backend.config import HYSTERIA_LOG_PATH
    
    now_ts = time.time()
    cutoff_ts = now_ts - 180  # 3 minutes

    # Incorporate active client IPs from sentinel-core bridge
    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic = get_unified_traffic()
        if traffic and isinstance(traffic, dict):
            for email, stats in traffic.items():
                if isinstance(stats, dict):
                    if "activeIps" in stats and stats["activeIps"]:
                        for ip in stats["activeIps"]:
                            if email not in ACTIVE_IP_CACHE:
                                ACTIVE_IP_CACHE[email] = {}
                            ACTIVE_IP_CACHE[email][ip] = now_ts
                    elif stats.get("online") or stats.get("connections", 0) > 0:
                        if email not in ACTIVE_IP_CACHE:
                            ACTIVE_IP_CACHE[email] = {}
                        ACTIVE_IP_CACHE[email]["127.0.0.1"] = now_ts
    except Exception:
        pass

    if not HYSTERIA_LOG_PATH.exists():
        return

    try:
        from backend.sentinel_core_bridge import get_core_logs
        lines = get_core_logs(str(HYSTERIA_LOG_PATH), 1000)
        if not lines:
            lines = read_last_lines(HYSTERIA_LOG_PATH, 1000)

        for line in lines:
            if "client connected" in line:
                match = re.search(r"client connected\s+(\{.*\})", line)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        username = data.get("id") or "Unknown"
                        raw_addr = data.get("addr", "")
                        ip = raw_addr.split(":")[0].strip("[]") if raw_addr else "127.0.0.1"
                        if username != "Unknown":
                            if username not in ACTIVE_IP_CACHE:
                                ACTIVE_IP_CACHE[username] = {}
                            ACTIVE_IP_CACHE[username][ip] = now_ts
                    except Exception:
                        pass
            elif "client disconnected" in line:
                match = re.search(r"client disconnected\s+(\{.*\})", line)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        username = data.get("id") or "Unknown"
                        raw_addr = data.get("addr", "")
                        ip = raw_addr.split(":")[0].strip("[]") if raw_addr else "127.0.0.1"
                        if username in ACTIVE_IP_CACHE and ip in ACTIVE_IP_CACHE[username]:
                            del ACTIVE_IP_CACHE[username][ip]
                            if not ACTIVE_IP_CACHE[username]:
                                del ACTIVE_IP_CACHE[username]
                    except Exception:
                        pass
    except Exception as e:
        logging.error(f"[Scheduler] Error parsing Hysteria logs: {e}")

def enforce_client_limits_and_rules():
    """Main background client limits scheduler running every 30 seconds."""
    import backend.scheduler
    backend.scheduler.parse_recent_xray_ips()
    backend.scheduler.parse_recent_singbox_ips()
    backend.scheduler.parse_recent_hysteria_ips()
    try:
        from backend.client_alerts import check_xray_inactivity_timeouts, check_singbox_inactivity_timeouts
        check_xray_inactivity_timeouts()
        check_singbox_inactivity_timeouts()
    except Exception as ex:
        logging.error(f"[Scheduler] Error checking inactivity timeouts: {ex}")
    
    now_ts = time.time()
    now_ms = int(now_ts * 1000)
    need_config_update = False
    
    from backend.database import get_setting
    from backend.i18n import t

    sys_lang = get_setting("language", "ru")
    bot_token = get_setting("telegram_bot_token", "")
    tg_admin_ids = get_setting("telegram_admin_ids", "")
    
    from backend.models import ClientTrafficDaily

    current_date = datetime.date.today().isoformat()
    with db_session() as session:
        active_clients = session.query(ClientStats).filter_by(enable=1).all()
        # Bulk load inbounds and daily traffic records to avoid N+1 query problem
        inbounds_by_id = {ib.id: ib for ib in session.query(Inbound).all()}
        daily_records = {rec.email: rec for rec in session.query(ClientTrafficDaily).filter_by(date=current_date).all()}
        
        for c in active_clients:
            inbound = inbounds_by_id.get(c.inbound_id)
            if not inbound:
                continue

            # Calculate daily delta
            delta_up = c.up - c.last_seen_up if c.up >= c.last_seen_up else c.up
            delta_down = c.down - c.last_seen_down if c.down >= c.last_seen_down else c.down
            
            delta_up = max(0, delta_up)
            delta_down = max(0, delta_down)
            
            if delta_up > 0 or delta_down > 0:
                daily_record = daily_records.get(c.email)
                if daily_record:
                    daily_record.up += delta_up
                    daily_record.down += delta_down
                else:
                    new_record = ClientTrafficDaily(
                        email=c.email,
                        date=current_date,
                        up=delta_up,
                        down=delta_down
                    )
                    session.add(new_record)
                    daily_records[c.email] = new_record
                    
            c.last_seen_up = c.up
            c.last_seen_down = c.down
            block_reason = ""
            
            # 1. Traffic limit check
            if c.total > 0 and (c.up + c.down) >= c.total:
                block_reason = t("traffic_limit_exceeded", sys_lang)
                
            # 2. Expiration check
            elif c.expiry_time > 0 and now_ms > c.expiry_time:
                block_reason = t("subscription_expired", sys_lang)
                
            # 3. IP limit check
            elif c.limit_ip > 0:
                active_ips = ACTIVE_IP_CACHE.get(c.email, {})
                if len(active_ips) > c.limit_ip:
                    block_reason = t("ip_limit_exceeded", sys_lang, count=len(active_ips), limit=c.limit_ip)
                    
            if block_reason:
                logging.warning(f"[Scheduler] Blocking client {c.email} due to: {block_reason}")
                c.enable = 0
                c.block_reason = block_reason
                need_config_update = True
                
                try:
                    from backend.sentinel_core_bridge import kick_client
                    kick_client(c.email)
                except Exception:
                    pass

                try:
                    if inbound.protocol == "hysteria2":
                        backend.scheduler.kick_client_hysteria_api(inbound.id, c.email)
                    else:
                        backend.scheduler.remove_client_api(inbound.id, c.email)
                except Exception:
                    pass
                    
                backend.scheduler.asyncio_notify_admin(c.email, block_reason, bot_token, tg_admin_ids)
                
    if need_config_update:
        from backend.utils.service_restart import restart_services_background
        restart_services_background(delay=0.5)
        
    # Run Backup
    try:
        from backend.scheduler_jobs.backups import check_and_run_backups
        check_and_run_backups()
    except Exception as e:
        logging.error(f"[Backup Scheduler] Error running backups: {e}")

    # Run Log Rotation
    try:
        from backend.scheduler_jobs.maintenance import truncate_logs_if_large
        truncate_logs_if_large()
    except Exception as e:
        logging.error(f"[Log Rotation] Error running log rotation: {e}")

    # Run DB Cleanup Maintenance
    try:
        from backend.scheduler_jobs.maintenance import run_db_cleanup_maintenance
        run_db_cleanup_maintenance()
    except Exception as e:
        logging.error(f"[DB Maintenance] Error running database cleanup: {e}")

def asyncio_notify_admin(email: str, reason: str, bot_token: str, tg_admin_ids: str):
    """Sends a block alert to admins in Telegram (async background task)."""
    global _last_notified_blocks
    
    last_t = _last_notified_blocks.get((email, reason), 0)
    if time.time() - last_t < 600:
        return
        
    _last_notified_blocks[(email, reason)] = time.time()
    
    try:
        if bot_token and tg_admin_ids:
            from aiogram import Bot
            from backend.database import get_setting
            from backend.i18n import t
            lang = get_setting("language", "ru")
            temp_bot = Bot(token=bot_token)
            admin_ids = [x.strip() for x in tg_admin_ids.split(",") if x.strip()]
            for admin_id in admin_ids:
                msg = t("limits_user_blocked_notification", lang=lang, category="backend", email=email, reason=reason)
                try:
                    loop = asyncio.get_running_loop()
                    
                    async def send_and_close(bot_inst, chat, text):
                        try:
                            await bot_inst.send_message(chat_id=chat, text=text, parse_mode="HTML")
                        finally:
                            await bot_inst.session.close()
                            
                    loop.create_task(send_and_close(temp_bot, admin_id, msg))
                except RuntimeError:
                    pass
    except Exception as e:
        logging.error(f"[Scheduler] Failed to send Telegram alert: {e}")
