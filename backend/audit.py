import time
import logging
from fastapi import Request
from backend.database import db_session
from backend.models import AuditLog
from backend.config import settings
from backend.auth_utils import ACTIVE_SESSIONS

def get_actor_username(request: Request) -> str:
    """
    Определяет имя пользователя, совершившего запрос (bot или admin).
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        if token == settings.API_TOKEN:
            return "bot"
            
    session_id = request.cookies.get("session_id")
    if session_id and session_id in ACTIVE_SESSIONS:
        try:
            from backend.database import get_session_db
            db_sess = get_session_db(session_id)
            if db_sess and db_sess.get("username"):
                return db_sess["username"]
        except Exception:
            pass
        return settings.ADMIN_USERNAME or "admin"
        
    return "unknown"

def log_action(username: str, action: str, target: str = None, details: str = None):
    """
    Записывает действие администратора или системы в таблицу AuditLog.
    """
    try:
        with db_session() as session:
            log_entry = AuditLog(
                timestamp=int(time.time()),
                username=username,
                action=action,
                target=target,
                details=details
            )
            session.add(log_entry)
        logging.info(f"[AuditLog] {username} executed '{action}' on target '{target}'")
        
        # Отправка Telegram-уведомления при необходимости
        from backend.telegram_alerts import trigger_telegram_alert
        trigger_telegram_alert(username, action, target, details)
    except Exception as e:
        logging.error(f"[AuditLog] Failed to write audit log: {e}")
