import secrets
import time
import logging
import json
import asyncio
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import settings
from backend.database import authenticate_admin
from backend.auth_utils import (
    ACTIVE_SESSIONS, CSRF_TOKENS, decoy_response, verify_telegram_webapp, check_auth
)

router = APIRouter()

class DbLoginAttempts:
    def clear(self):
        from backend.database import db_session
        from backend.models import SharedCache
        try:
            with db_session() as session:
                session.query(SharedCache).filter(SharedCache.key.like("login_attempts:%")).delete()
        except Exception:
            pass

LOGIN_ATTEMPTS = DbLoginAttempts()

def is_ip_whitelisted_sync(client_ip: str) -> bool:
    from backend.database import get_setting
    import json
    try:
        val = get_setting("ips_whitelisted_sync", "[]")
        ips = json.loads(val)
        for entry in ips:
            entry = entry.strip()
            if ":" in entry:
                entry_ip, entry_port = entry.rsplit(":", 1)
                if entry_ip == client_ip:
                    if entry_port == "*" or str(entry_port) == str(settings.PANEL_PORT):
                        return True
            else:
                if entry == client_ip:
                    return True
    except Exception as e:
        logging.error(f"Error checking synchronized IP whitelist: {e}")
    return False

def check_rate_limit(ip: str) -> bool:
    if is_ip_whitelisted_sync(ip):
        return True
    from backend.database import get_setting
    from backend.database.crud.shared_cache import get_shared_cache
    import json
    now = time.time()
    
    period = int(get_setting("login_attempts_period", str(settings.LOGIN_ATTEMPTS_PERIOD)))
    max_attempts = int(get_setting("login_max_attempts", str(settings.LOGIN_MAX_ATTEMPTS)))
    
    attempts_str = get_shared_cache(f"login_attempts:{ip}")
    if attempts_str:
        try:
            attempts = json.loads(attempts_str)
        except Exception:
            attempts = []
    else:
        attempts = []
        
    attempts = [t for t in attempts if now - t < period]
    return len(attempts) < max_attempts

def record_attempt(ip: str):
    from backend.database.crud.shared_cache import get_shared_cache, set_shared_cache
    from backend.database import get_setting
    import json
    now = time.time()
    
    period = int(get_setting("login_attempts_period", str(settings.LOGIN_ATTEMPTS_PERIOD)))
    
    attempts_str = get_shared_cache(f"login_attempts:{ip}")
    if attempts_str:
        try:
            attempts = json.loads(attempts_str)
        except Exception:
            attempts = []
    else:
        attempts = []
        
    attempts.append(now)
    set_shared_cache(f"login_attempts:{ip}", json.dumps(attempts), period)

class LoginRequest(BaseModel):
    username: str
    password: str

@router.get("/csrf-token")
async def get_csrf_token(request: Request):
    """Returns CSRF token for the session."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and auth_header.split(" ")[1] == settings.API_TOKEN:
        return {"success": True, "obj": "bearer_bypass"}
        
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in ACTIVE_SESSIONS:
        return decoy_response()
        
    token = CSRF_TOKENS.get(session_id)
    if not token:
        token = secrets.token_hex(16)
        CSRF_TOKENS[session_id] = token
        
    return {"success": True, "obj": token}

@router.post("/login")
async def login_api(request: Request, response: Response):
    """Login with username and password (JSON & Form)."""
    client_ip = request.client.host if request.client else "unknown"
    
    from backend.database import get_setting
    banned_ips = get_setting("banned_login_ips", "")
    if client_ip in [ip.strip() for ip in banned_ips.split(",") if ip.strip()]:
        return JSONResponse(status_code=403, content={"success": False, "msg": "Ваш IP-адрес заблокирован."})
        
    content_type = request.headers.get("content-type", "")
    uname = None
    pwd = None
    
    if "application/json" in content_type:
        try:
            body = await request.json()
            uname = body.get("username")
            pwd = body.get("password")
        except Exception as e:
            logging.warning(f"Failed to parse JSON login body: {e}")
    else:
        try:
            form = await request.form()
            uname = form.get("username")
            pwd = form.get("password")
        except Exception as e:
            logging.warning(f"Failed to parse Form login data: {e}")
            
    if not uname or not pwd:
        from backend.audit import log_action
        log_action("unknown", "login_failure", target=client_ip, details="Empty login credentials")
        return decoy_response()
        
    # Rate Limiting
    if not check_rate_limit(client_ip):
        from backend.audit import log_action
        period = int(get_setting("login_attempts_period", str(settings.LOGIN_ATTEMPTS_PERIOD)))
        log_action("system", "login_rate_limited", target=client_ip, details=f"IP {client_ip} exceeded max login attempts. Blocked for {period}s.")
        return JSONResponse(status_code=429, content={"success": False, "msg": f"Слишком много попыток входа. Пожалуйста, подождите {period} сек."})
        
    record_attempt(client_ip)
        
    fail_delay = float(get_setting("login_fail_delay", str(settings.LOGIN_FAIL_DELAY)))
    if fail_delay > 0:
        await asyncio.sleep(fail_delay)
    
    from backend.audit import log_action
    if authenticate_admin(uname, pwd):
        from backend.models import User
        from backend.database import db_session
        
        with db_session() as session:
            user = session.query(User).filter_by(username=uname).first()
            
            totp_secret = user.totp_secret if user else None
            totp_enabled = user.totp_enabled if user else 0
            
            totp_active = user and totp_enabled == 1
            telegram_active = get_setting("telegram_2fa_enabled", "false") == "true"
            
            if is_ip_whitelisted_sync(client_ip):
                logging.info(f"[Auth Whitelist] Отключение 2FA для белого IP: {client_ip}")
                totp_active = False
                telegram_active = False
            
            if totp_active or telegram_active:
                code = None
                if "application/json" in content_type:
                    try:
                        body = await request.json()
                        code = body.get("code")
                    except Exception:
                        pass
                else:
                    try:
                        form = await request.form()
                        code = form.get("code")
                    except Exception:
                        pass
                
                totp_verified = False
                if totp_active and code:
                    from backend.totp import verify_totp_token
                    if verify_totp_token(totp_secret, code):
                        totp_verified = True
                
                if not totp_verified:
                    if totp_active and code:
                        log_action(uname, "login_2fa_failure", target=client_ip, details="Invalid 2FA code")
                        return {"success": False, "msg": "Неверный код двухфакторной аутентификации"}
                        
                    if telegram_active:
                        tg_token = secrets.token_hex(16)
                        from backend.models import SystemSetting
                        session.add(SystemSetting(
                            key=f"tg_2fa_req_{tg_token}",
                            value=json.dumps({
                                "username": uname,
                                "client_ip": client_ip,
                                "status": "pending",
                                "expires": time.time() + 120
                            })
                        ))
                        session.commit()
                        
                        try:
                            from backend.config import CONFIG_DIR
                            log_file = CONFIG_DIR / "2fa.log"
                            with open(log_file, "a", encoding="utf-8") as f:
                                log_data = {
                                    "timestamp": int(time.time()),
                                    "status": "PENDING",
                                    "username": uname,
                                    "client_ip": client_ip,
                                    "token": tg_token
                                }
                                f.write(json.dumps(log_data) + "\n")
                        except Exception as e:
                            logging.error(f"Failed to write 2fa.log: {e}")
                        
                        bot_enabled = get_setting("telegram_bot_enabled", "true") == "true"
                        bot_token = get_setting("telegram_bot_token", "")
                        tg_admin_ids = get_setting("telegram_admin_ids", "")
                        
                        if bot_enabled and bot_token and tg_admin_ids:
                            from aiogram import Bot
                            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                            
                            temp_bot = Bot(token=bot_token)
                            kb = InlineKeyboardMarkup(inline_keyboard=[
                                [
                                    InlineKeyboardButton(text="✅ Да, разрешить", callback_data=f"tg_2fa_approve:{tg_token}"),
                                    InlineKeyboardButton(text="❌ Заблокировать IP", callback_data=f"tg_2fa_block:{tg_token}")
                                ]
                            ])
                            
                            admin_ids = [x.strip() for x in tg_admin_ids.split(",") if x.strip()]
                            
                            async def send_2fa_alert(bot_inst, chat, ip, keyboard):
                                try:
                                    await bot_inst.send_message(
                                        chat_id=chat,
                                        text=f"🚨 <b>Попытка входа в панель с IP <code>{ip}</code>. Это вы?</b>",
                                        reply_markup=keyboard,
                                        parse_mode="HTML"
                                    )
                                except Exception as ex:
                                    logging.error(f"Failed to send 2FA alert: {ex}")
                                finally:
                                    await bot_inst.session.close()
                                    
                            try:
                                loop = asyncio.get_running_loop()
                                for admin_id in admin_ids:
                                    loop.create_task(send_2fa_alert(temp_bot, admin_id, client_ip, kb))
                            except RuntimeError:
                                pass
                                
                        return {
                            "success": True,
                            "requires_2fa": True,
                            "type": "both" if totp_active else "tg_2fa",
                            "token": tg_token,
                            "msg": "Требуется подтверждение входа"
                        }
                    else:
                        return {"success": True, "requires_2fa": True, "type": "totp", "msg": "Требуется двухфакторная аутентификация"}

        session_id = secrets.token_hex(16)
        
        from backend.database import add_session_db
        timeout_days = int(get_setting("session_timeout_days", str(settings.SESSION_TIMEOUT_DAYS)))
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
        log_action(uname, "login_success", target=client_ip, details="Web password login success")
        return {"success": True, "msg": "Успешный вход"}
        
    log_action(uname, "login_failure", target=client_ip, details="Invalid password")
    return {"success": False, "msg": "Неверный логин или пароль"}

@router.post("/api/auth/telegram")
async def telegram_webapp_auth(request: Request, response: Response, payload: dict):
    """Auth via Telegram WebApp with initData signature verification."""
    init_data = payload.get("initData")
    if not init_data:
        return JSONResponse(status_code=400, content={"success": False, "msg": "Missing initData"})
        
    client_ip = request.client.host if request.client else "unknown"
    from backend.audit import log_action
    user = verify_telegram_webapp(init_data)
    if not user:
        log_action("unknown_tg", "login_telegram_failure", target=client_ip, details="Invalid Telegram webapp signature")
        return JSONResponse(status_code=401, content={"success": False, "msg": "Неверная цифровая подпись Telegram"})
        
    tg_id = str(user.get("id"))
    username_tg = user.get("username") or f"tg_{tg_id}"
    
    from backend.database import get_setting
    tg_admin_ids = get_setting("telegram_admin_ids", "")
    allowed_ids = [x.strip() for x in tg_admin_ids.split(",") if x.strip()]
    if not allowed_ids or tg_id not in allowed_ids:
        logging.warning(f"Unauthorized Telegram login attempt: ID {tg_id} ({user.get('username')})")
        log_action(username_tg, "login_telegram_failure", target=client_ip, details=f"Telegram ID {tg_id} not in whitelist")
        return JSONResponse(status_code=403, content={"success": False, "msg": "Ваш Telegram ID отсутствует в белом списке"})
        
    if not check_rate_limit(client_ip):
        from backend.audit import log_action
        period = int(get_setting("login_attempts_period", str(settings.LOGIN_ATTEMPTS_PERIOD)))
        log_action("system", "login_rate_limited", target=client_ip, details=f"IP {client_ip} exceeded max Telegram webapp login attempts. Blocked for {period}s.")
        return JSONResponse(status_code=429, content={"success": False, "msg": f"Слишком много попыток входа. Пожалуйста, подождите {period} сек."})
        
    record_attempt(client_ip)

    session_id = secrets.token_hex(16)
    
    from backend.database import add_session_db
    timeout_days = int(get_setting("session_timeout_days", str(settings.SESSION_TIMEOUT_DAYS)))
    user_agent = request.headers.get("user-agent", "unknown")
    add_session_db(session_id, username_tg, timeout_days, ip_address=client_ip, user_agent=user_agent)
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
    
    log_action(username_tg, "login_telegram_success", target=client_ip, details=f"Telegram WebApp login success (ID: {tg_id})")
    return {"success": True, "token": csrf_token}

@router.post("/api/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id:
        from backend.audit import log_action, get_actor_username
        from backend.database import delete_session_db
        actor = get_actor_username(request)
        delete_session_db(session_id)
        ACTIVE_SESSIONS.discard(session_id)
        CSRF_TOKENS.pop(session_id, None)
        client_ip = request.client.host if request.client else "unknown"
        log_action(actor, "logout", target=client_ip)
    response.delete_cookie("session_id")
    return {"success": True}
