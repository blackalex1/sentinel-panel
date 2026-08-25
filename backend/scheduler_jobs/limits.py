import time
import datetime
import logging
import asyncio
from backend.models import ClientStats, Inbound
from backend.database import db_session

# Cache of active IPs in memory for limit checks: { email: { ip: timestamp } }
ACTIVE_IP_CACHE = {}

# Notification timers to prevent Telegram spam
_last_notified_blocks = {}
_last_sb_client_traffic = {}

def sync_active_ips_from_core():
    """Populates ACTIVE_IP_CACHE natively from Go sentinel-core SessionTracker with zero disk IO."""
    global ACTIVE_IP_CACHE
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

    # 1. Native active sessions from sentinel-core SessionTracker
    try:
        from backend.sentinel_core_bridge import get_active_sessions, get_unified_traffic
        sessions = get_active_sessions()
        if sessions and isinstance(sessions, list):
            for s in sessions:
                email = s.get("email")
                ip = s.get("ip")
                if email and ip:
                    if email not in ACTIVE_IP_CACHE:
                        ACTIVE_IP_CACHE[email] = {}
                    ACTIVE_IP_CACHE[email][ip] = s.get("last_seen_at", now_ts)

        traffic = get_unified_traffic()
        if traffic and isinstance(traffic, dict):
            for email, stats in traffic.items():
                if isinstance(stats, dict) and "activeIPs" in stats and stats["activeIPs"]:
                    for ip in stats["activeIPs"]:
                        if email not in ACTIVE_IP_CACHE:
                            ACTIVE_IP_CACHE[email] = {}
                        ACTIVE_IP_CACHE[email][ip] = now_ts
    except Exception as e:
        logging.debug(f"[Scheduler] Error syncing active IPs from core: {e}")

# Backward-compatibility aliases for scheduler exports
parse_recent_xray_ips = sync_active_ips_from_core
parse_recent_singbox_ips = sync_active_ips_from_core
parse_recent_hysteria_ips = sync_active_ips_from_core

def enforce_client_limits_and_rules():
    """Main background client limits scheduler running every 30 seconds."""
    import backend.scheduler
    sync_active_ips_from_core()
    
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
