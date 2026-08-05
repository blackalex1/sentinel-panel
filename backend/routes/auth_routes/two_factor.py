import secrets
import time
import json
import subprocess
import logging
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from backend.config import settings
from backend.auth_utils import (
    decoy_response, check_auth, ACTIVE_SESSIONS, CSRF_TOKENS
)

router = APIRouter()

@router.get("/api/settings/2fa/setup")
async def setup_2fa_api(request: Request):
    """Generates new TOTP secret and QR code URI."""
    if not check_auth(request):
        return decoy_response()
        
    from backend.audit import get_actor_username
    actor = get_actor_username(request)
    
    from backend.models import User
    from backend.database import db_session
    from backend.totp import generate_totp_secret, get_totp_uri
    
    with db_session() as session:
        user = session.query(User).filter_by(username=actor).first()
        if not user:
            return {"success": False, "msg": "Пользователь не найден"}
            
        if user.totp_enabled == 1:
            return {"success": False, "msg": "Двухфакторная аутентификация уже включена"}
            
        secret = generate_totp_secret()
        user.totp_secret = secret
        session.commit()
        
    qr_uri = get_totp_uri(secret, actor)
    return {
        "success": True,
        "secret": secret,
        "qr_uri": qr_uri
    }

@router.post("/api/settings/2fa/enable")
async def enable_2fa_api(request: Request):
    """Enables TOTP 2FA after verifying a one-time code."""
    if not check_auth(request):
        return decoy_response()
        
    try:
        body = await request.json()
        code = body.get("code")
    except Exception:
        return {"success": False, "msg": "Неверный формат запроса"}
        
    if not code:
        return {"success": False, "msg": "Код подтверждения обязателен"}
        
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    from backend.models import User
    from backend.database import db_session
    from backend.totp import verify_totp_token
    
    with db_session() as session:
        user = session.query(User).filter_by(username=actor).first()
        if not user or not user.totp_secret:
            return {"success": False, "msg": "2FA не настроена. Сначала получите секретный ключ."}
            
        if user.totp_enabled == 1:
            return {"success": False, "msg": "2FA уже включена"}
            
        if verify_totp_token(user.totp_secret, code):
            user.totp_enabled = 1
            # Invalidate all other sessions of this user for security
            session_id = request.cookies.get("session_id")
            if session_id:
                from backend.models import UserSession, SharedCache
                other_sessions = session.query(UserSession).filter(
                    UserSession.username == actor,
                    UserSession.session_id != session_id
                ).all()
                for s in other_sessions:
                    session.query(SharedCache).filter(SharedCache.key == f"csrf:{s.session_id}").delete()
                    session.delete(s)
            session.commit()
            log_action(actor, "enable_2fa", details="TOTP enabled successfully")
            return {"success": True, "msg": "Двухфакторная аутентификация успешно включена"}
        else:
            return {"success": False, "msg": "Неверный код подтверждения"}

@router.post("/api/settings/2fa/disable")
async def disable_2fa_api(request: Request):
    """Disables TOTP 2FA after verifying a code."""
    if not check_auth(request):
        return decoy_response()
        
    try:
        body = await request.json()
        code = body.get("code")
    except Exception:
        return {"success": False, "msg": "Неверный формат запроса"}
        
    if not code:
        return {"success": False, "msg": "Код подтверждения обязателен"}
        
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    from backend.models import User
    from backend.database import db_session
    from backend.totp import verify_totp_token
    
    with db_session() as session:
        user = session.query(User).filter_by(username=actor).first()
        if not user or user.totp_enabled == 0:
            return {"success": False, "msg": "2FA не включена для этого пользователя"}
            
        if verify_totp_token(user.totp_secret, code):
            user.totp_enabled = 0
            user.totp_secret = None
            # Invalidate all other sessions of this user for security
            session_id = request.cookies.get("session_id")
            if session_id:
                from backend.models import UserSession, SharedCache
                other_sessions = session.query(UserSession).filter(
                    UserSession.username == actor,
                    UserSession.session_id != session_id
                ).all()
                for s in other_sessions:
                    session.query(SharedCache).filter(SharedCache.key == f"csrf:{s.session_id}").delete()
                    session.delete(s)
            session.commit()
            log_action(actor, "disable_2fa", details="TOTP disabled successfully")
            return {"success": True, "msg": "Двухфакторная аутентификация успешно отключена"}
        else:
            return {"success": False, "msg": "Неверный код подтверждения"}

@router.get("/api/auth/tg-2fa/poll")
async def tg_2fa_poll(request: Request, response: Response, token: str):
    """Polls Telegram 2FA status and creates session cookie if approved."""
    from backend.database import db_session, get_setting, add_session_db
    from backend.models import SystemSetting
    import json
    import time
    
    with db_session() as session:
        setting = session.query(SystemSetting).filter_by(key=f"tg_2fa_req_{token}").first()
        if not setting:
            return {"success": False, "status": "expired"}
            
        try:
            data = json.loads(setting.value)
        except Exception:
            return {"success": False, "status": "expired"}
            
        if time.time() > data.get("expires", 0):
            session.delete(setting)
            session.commit()
            return {"success": True, "status": "expired"}
            
        status = data.get("status", "pending")
        if status == "approved":
            uname = data.get("username", "admin")
            session_id = secrets.token_hex(16)
            timeout_days = int(get_setting("session_timeout_days", str(settings.SESSION_TIMEOUT_DAYS)))
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            add_session_db(session_id, uname, timeout_days, ip_address=client_ip, user_agent=user_agent)
            ACTIVE_SESSIONS.add(session_id)
            
            csrf_token = secrets.token_hex(16)
            CSRF_TOKENS[session_id] = csrf_token
            
            response.set_cookie(
                key="session_id", 
                value=session_id, 
                httponly=True, 
                samesite="lax",
                secure=True,
                max_age=timeout_days * 24 * 3600
            )
            
            session.delete(setting)
            session.commit()
            
            from backend.audit import log_action
            log_action(uname, "login_success", target=data.get("client_ip"), details="Web Telegram 2FA login approved")
            return {"success": True, "status": "approved", "msg": "Успешный вход"}
            
        elif status == "blocked":
            session.delete(setting)
            session.commit()
            return {"success": True, "status": "blocked"}
            
        return {"success": True, "status": "pending"}

class Tg2faActionBody(BaseModel):
    token: str
    action: str

@router.post("/api/auth/tg-2fa/action")
async def tg_2fa_action(payload: Tg2faActionBody):
    """Executes approval or block actions for a Telegram 2FA request."""
    from backend.database import db_session, get_setting, set_setting
    from backend.models import SystemSetting
    import json
    import subprocess
    
    token = payload.token
    action = payload.action
    
    with db_session() as session:
        setting = session.query(SystemSetting).filter_by(key=f"tg_2fa_req_{token}").first()
        if not setting:
            return {"success": False, "msg": "Запрос не найден или истек"}
            
        try:
            data = json.loads(setting.value)
        except Exception:
            return {"success": False, "msg": "Неверный формат запроса"}
            
        if action == "approve":
            data["status"] = "approved"
            setting.value = json.dumps(data)
            session.commit()
            return {"success": True, "msg": "Вход разрешен"}
            
        elif action == "block":
            data["status"] = "blocked"
            setting.value = json.dumps(data)
            
            client_ip = data.get("client_ip")
            if client_ip and client_ip != "unknown":
                from backend.routes.auth_routes.login import is_ip_whitelisted_sync
                if is_ip_whitelisted_sync(client_ip) or client_ip in ("127.0.0.1", "::1", "localhost"):
                    session.commit()
                    return {"success": True, "msg": "IP в белом списке, блокировка пропущена"}
                    
                banned_ips = get_setting("banned_login_ips", "")
                banned_list = [ip.strip() for ip in banned_ips.split(",") if ip.strip()]
                if client_ip not in banned_list:
                    banned_list.append(client_ip)
                    set_setting("banned_login_ips", ",".join(banned_list))
                    
                try:
                    subprocess.run(["iptables", "-I", "INPUT", "-s", client_ip, "-j", "DROP"], capture_output=True)
                except Exception as ex:
                    logging.warning(f"Failed to block IP via iptables: {ex}")
                    
            session.commit()
            return {"success": True, "msg": "IP заблокирован"}
            
        return {"success": False, "msg": "Неверное действие"}
