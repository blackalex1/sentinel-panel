import time
import logging
from backend.config import XRAY_LOG_PATH, HYSTERIA_LOG_PATH
from backend.utils import read_last_lines
from backend.database import db_session

_last_db_cleanup = 0

def truncate_logs_if_large():
    """Checks log file sizes and truncates them to last 2000 lines if they exceed 10 MB."""
    from backend.bot_manager import TELEGRAM_BOT_LOG_PATH
    
    logs_to_check = [
        ("Xray", XRAY_LOG_PATH),
        ("Hysteria 2", HYSTERIA_LOG_PATH),
        ("Telegram Bot", TELEGRAM_BOT_LOG_PATH),
    ]
    
    max_size_bytes = 10 * 1024 * 1024  # 10 MB
    lines_to_keep = 2000
    
    for name, log_path in logs_to_check:
        try:
            if not log_path.exists():
                continue
                
            file_size = log_path.stat().st_size
            if file_size <= max_size_bytes:
                continue
                
            logging.info(f"[Scheduler] Log file {log_path.name} ({name}) is too large ({file_size / (1024*1024):.2f} MB). Truncating to last {lines_to_keep} lines...")
            
            # Read last N lines using memory-efficient helper
            last_lines = read_last_lines(log_path, lines_to_keep)
            
            # Write back to file, truncating it
            with open(log_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write("\n".join(last_lines) + "\n")
                
            logging.info(f"[Scheduler] Log file {log_path.name} ({name}) truncated successfully. New size: {log_path.stat().st_size} bytes.")
        except Exception as e:
            logging.error(f"[Scheduler] Failed to truncate log file {log_path}: {e}")

def run_db_cleanup_maintenance():
    """Background DB cleanup: deletes expired user sessions and action logs older than 30 days."""
    global _last_db_cleanup
    now = time.time()
    
    # Run once every 24 hours
    if now - _last_db_cleanup < 86400:
        return
        
    _last_db_cleanup = now
    logging.info("[Scheduler] Starting database maintenance (cleanup of expired sessions & old audit logs)...")
    
    try:
        from backend.database import clean_expired_sessions_db, clean_expired_shared_cache
        clean_expired_sessions_db()
        logging.info("[Scheduler] Expired user sessions cleaned successfully.")
        clean_expired_shared_cache()
        logging.info("[Scheduler] Expired shared cache entries cleaned successfully.")
    except Exception as e:
        logging.error(f"[Scheduler] Failed to clean expired sessions or shared cache: {e}")
        
    try:
        from backend.models import AuditLog
        cutoff = int(now) - (30 * 24 * 60 * 60)
        with db_session() as session:
            deleted_count = session.query(AuditLog).filter(AuditLog.timestamp < cutoff).delete()
            if deleted_count > 0:
                logging.info(f"[Scheduler] Cleaned {deleted_count} old audit logs (older than 30 days).")
    except Exception as e:
        logging.error(f"[Scheduler] Failed to clean old audit logs: {e}")
