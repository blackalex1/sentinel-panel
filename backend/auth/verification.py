import secrets
import hmac
import hashlib
import time
import logging
import json
from urllib.parse import parse_qsl
from typing import Optional
from fastapi import Request

from backend.config import settings
from backend.database import get_setting
from backend.auth.sessions import ACTIVE_SESSIONS, CSRF_TOKENS

def check_auth(request: Request) -> bool:
    """Проверяет авторизацию: либо по Bearer Token, либо по Cookie сессии"""
    # 1. Проверка Bearer Token (для бота-контроллера)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        if hmac.compare_digest(token, settings.API_TOKEN):
            return True
            
    # 2. Проверка Session Cookie
    session_id = request.cookies.get("session_id")
    if session_id:
        from backend.database import get_session_db, delete_session_db, update_session_ip_db
        db_sess = get_session_db(session_id)
        if db_sess:
            if db_sess["expires_at"] > int(time.time()):
                # Если IP-адрес запроса изменился по сравнению с сохраненным в сессии, обновляем его
                client_ip = request.client.host if request.client else "unknown"
                if client_ip != "unknown" and db_sess.get("ip_address") != client_ip:
                    try:
                        update_session_ip_db(session_id, client_ip)
                        db_sess["ip_address"] = client_ip
                    except Exception as e:
                        logging.error(f"Failed to update session IP: {e}")
                
                # Валидация CSRF для небезопасных методов
                if request.method in ("POST", "PUT", "DELETE"):
                    csrf_token = request.headers.get("X-CSRF-Token")
                    if not csrf_token or CSRF_TOKENS.get(session_id) != csrf_token:
                        return False
                return True
            else:
                # Сессия истекла, удаляем ее из БД
                delete_session_db(session_id)
                ACTIVE_SESSIONS.discard(session_id)
        
    return False

def check_ws_auth(websocket) -> bool:
    """Криптографически проверяет авторизацию WebSocket-соединения перед accept()"""
    # 1. Проверка Bearer Token
    token = websocket.query_params.get("token") or ""
    auth_header = websocket.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    if token and hmac.compare_digest(token, settings.API_TOKEN):
        return True

    # 2. Проверка Session Cookie
    session_id = websocket.cookies.get("session_id")
    if session_id:
        from backend.database import get_session_db, delete_session_db
        db_sess = get_session_db(session_id)
        if db_sess:
            if db_sess.get("expires_at", 0) > int(time.time()):
                return True
            else:
                delete_session_db(session_id)
                ACTIVE_SESSIONS.discard(session_id)
    return False

def verify_node_token(request: Request) -> bool:
    """Проверяет токен ноды (Edge-сервера) во избежание получения decoy заглушки"""
    node_id = request.headers.get("X-Node-ID")
    auth_header = request.headers.get("Authorization", "")
    
    if not node_id or not auth_header.startswith("Bearer "):
        return False
        
    token = auth_header.split(" ")[1]
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    
    try:
        from backend.database import db_session
        from backend.models import Node
        with db_session() as session:
            node = session.query(Node).filter_by(id=node_id, status="active").first()
            if node:
                return hmac.compare_digest(node.api_token_hash, token_hash)
    except Exception as e:
        logging.error(f"Error in verify_node_token: {e}")
        
    return False

def verify_telegram_webapp(init_data: str) -> Optional[dict]:
    """Криптографически проверяет initData от Telegram Mini App"""
    bot_token = get_setting("telegram_bot_token", "")
    if not bot_token:
        logging.warning("[verify_telegram_webapp] telegram_bot_token is empty in database settings!")
        return None
    if not init_data:
        logging.warning("[verify_telegram_webapp] init_data is empty!")
        return None
        
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed:
            logging.warning("[verify_telegram_webapp] 'hash' parameter is missing from initData!")
            return None
            
        received_hash = parsed.pop("hash")
        
        # Сортируем все оставшиеся параметры по алфавиту
        sorted_params = sorted(parsed.items())
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_params)
        
        # Вычисляем секретный ключ (HMAC с ключом "WebAppData" от токена бота)
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        
        # Вычисляем хэш
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(calculated_hash, received_hash):
            logging.warning(
                f"[verify_telegram_webapp] Signature hash mismatch! "
                f"Check that the bot token set in the panel matches the bot you are using to open the WebApp. "
                f"Configured token starts with: '{bot_token[:6]}...'"
            )
            return None
            
        # Проверяем дату (устаревание initData через 24 часа)
        auth_date = int(parsed.get("auth_date", 0))
        time_diff = time.time() - auth_date
        logging.info(f"[verify_telegram_webapp] Signature verified successfully. auth_date diff: {time_diff:.1f}s")
        
        if time_diff > 86400:
            logging.warning(f"[verify_telegram_webapp] initData expired. auth_date diff is {time_diff:.1f}s (> 86400s)")
            return None
            
        user_json = parsed.get("user")
        if user_json:
            return json.loads(user_json)
    except Exception as e:
        logging.error(f"[verify_telegram_webapp] Telegram webapp signature verification error: {e}")
    return None
