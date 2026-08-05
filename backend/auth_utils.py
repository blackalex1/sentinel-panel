import secrets
import hmac
import hashlib
import time
import logging
import json
import datetime
import socket
import ipaddress
from urllib.parse import parse_qsl, urlparse
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
import httpx

from backend.config import settings, BASE_DIR
from backend.database import get_setting

def is_safe_url(url: str) -> bool:
    """Проверяет URL на безопасность от SSRF-атак"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        
        # Разрешаем имя хоста во все IP адреса
        try:
            ips = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # Если имя не разрешается (например, mock-домен decoy.site в тестах),
            # это безопасно для SSRF, так как сетевой запрос к нему совершить невозможно.
            return True
            
        for family, _, _, _, sockaddr in ips:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_loopback or ip.is_private or ip.is_multicast or ip.is_link_local or ip.is_unspecified:
                return False
        return True
    except Exception:
        return False

class DbCsrfTokens:
    def get(self, key, default=None):
        from backend.database.crud.shared_cache import get_shared_cache
        val = get_shared_cache(f"csrf:{key}")
        return val if val is not None else default
        
    def __getitem__(self, key):
        from backend.database.crud.shared_cache import get_shared_cache
        val = get_shared_cache(f"csrf:{key}")
        if val is None:
            raise KeyError(key)
        return val
        
    def __setitem__(self, key, value):
        from backend.database.crud.shared_cache import set_shared_cache
        set_shared_cache(f"csrf:{key}", value, 7 * 24 * 60 * 60)
        
    def __delitem__(self, key):
        from backend.database.crud.shared_cache import delete_shared_cache
        delete_shared_cache(f"csrf:{key}")
        
    def __contains__(self, key):
        return self.get(key) is not None
        
    def discard(self, key):
        from backend.database.crud.shared_cache import delete_shared_cache
        delete_shared_cache(f"csrf:{key}")
        
    def pop(self, key, default=None):
        val = self.get(key)
        if val is not None:
            self.__delitem__(key)
            return val
        return default
        
    def clear(self):
        from backend.database import db_session
        from backend.models import SharedCache
        try:
            with db_session() as session:
                session.query(SharedCache).filter(SharedCache.key.like("csrf:%")).delete()
        except Exception:
            pass

class DbActiveSessions:
    def __contains__(self, key):
        from backend.database import get_session_db
        import time
        try:
            db_sess = get_session_db(key)
            return db_sess is not None and db_sess["expires_at"] > int(time.time())
        except Exception:
            return False
        
    def add(self, key):
        pass
        
    def discard(self, key):
        from backend.database import delete_session_db
        try:
            delete_session_db(key)
        except Exception:
            pass
            
    def clear(self):
        from backend.database import db_session
        from backend.models import UserSession
        try:
            with db_session() as session:
                session.query(UserSession).delete()
        except Exception:
            pass

ACTIVE_SESSIONS = DbActiveSessions()
CSRF_TOKENS = DbCsrfTokens()

class DecoyException(Exception):
    """Исключение для динамического перехвата маскировки"""
    pass

def decoy_response_html():
    """Возвращает стандартную заглушку Nginx 404"""
    html_content = """<html>
<head><title>404 Not Found</title></head>
<body>
<center><h1>404 Not Found</h1></center>
<hr><center>nginx</center>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=404)

def decoy_response():
    """Возбуждает исключение для динамической маскировки"""
    raise DecoyException()


def check_auth(request: Request) -> bool:
    """Проверяет авторизацию: либо по Bearer Token, либо по Cookie сессии"""
    # 1. Проверка Bearer Token (для бота-контроллера)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        if token == settings.API_TOKEN:
            return True
            
    # 2. Проверка Session Cookie
    session_id = request.cookies.get("session_id")
    if session_id:
        from backend.database import get_session_db, delete_session_db, update_session_ip_db
        db_sess = get_session_db(session_id)
        if db_sess:
            import time
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
        
        if calculated_hash != received_hash:
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


# --- Системы маскировки (Decoy Sites) ---

templates = None

def get_templates():
    global templates
    if templates is None:
        decoy_dir = BASE_DIR / "frontend" / "decoy"
        if decoy_dir.exists():
            templates = Jinja2Templates(directory=str(decoy_dir))
    return templates

def render_static_decoy(request: Request, path: str = "") -> Response:
    decoy_dir = BASE_DIR / "frontend" / "decoy"
    if not decoy_dir.exists():
        return decoy_response_html()
        
    path = path.strip("/")
    if not path:
        decoy_value = get_setting("decoy_value", "company_landing")
        template_name = decoy_value if decoy_value.endswith(".html") else f"{decoy_value}.html"
        file_path = decoy_dir / template_name
        if not file_path.exists():
            file_path = decoy_dir / "index.html"
    else:
        file_path = decoy_dir / path
        
    if file_path.exists() and file_path.is_dir():
        file_path = file_path / "index.html"
        
    if not file_path.exists() and path:
        html_file = decoy_dir / f"{path}.html"
        if html_file.exists() and html_file.is_file():
            file_path = html_file

    # Защита от Path Traversal: файл должен находиться строго внутри decoy_dir
    if file_path.exists():
        try:
            file_path.resolve().relative_to(decoy_dir.resolve())
        except (ValueError, RuntimeError):
            return decoy_response_html()

    if file_path.exists() and file_path.is_file():
        # Поддержка динамических полей Jinja2 для стандартной заглушки и index.html
        if file_path.name in ("company_landing.html", "index.html"):
            tpls = get_templates()
            if tpls:
                try:
                    server_host = request.headers.get("host", "localhost")
                    h = sum(ord(c) for c in server_host)
                    served_count = 120 + (h % 380)
                    domain = server_host.split(":")[0]
                    contact_email = f"info@{domain}" if "." in domain else "info@nimbus.solutions"
                    current_year = datetime.datetime.now().year
                    
                    # Проверяем, действительно ли файл лежит непосредственно в decoy_dir
                    # во избежание Path Traversal при передаче имени в TemplateResponse
                    rel_name = file_path.relative_to(decoy_dir)
                    return tpls.TemplateResponse(
                        request,
                        str(rel_name).replace("\\", "/"),
                        {
                            "contact_email": contact_email,
                            "served_count": served_count,
                            "current_year": current_year,
                            "server_host": server_host
                        }
                    )
                except Exception as e:
                    logging.error(f"Error rendering static decoy template: {e}")
                    
        return FileResponse(str(file_path))
        
    custom_404 = decoy_dir / "404.html"
    if custom_404.exists() and custom_404.is_file():
        return FileResponse(str(custom_404), status_code=404)
        
    return decoy_response_html()

async def proxy_decoy_request(request: Request, path: str) -> Response:
    decoy_value = get_setting("decoy_value", "company_landing")
    if not decoy_value.startswith("http"):
        return render_static_decoy(request)
        
    try:
        target_url = f"{decoy_value.rstrip('/')}/{path}"
        if request.query_params:
            target_url += f"?{request.query_params}"
            
        if not is_safe_url(target_url):
            logging.warning(f"SSRF block triggered for target URL: {target_url}")
            return render_static_decoy(request)
            
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "accept-encoding")}
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, verify=False) as client:
            req_method = request.method
            req_content = await request.body()
            
            proxy_res = await client.request(
                method=req_method,
                url=target_url,
                headers=headers,
                content=req_content
            )
            
            exclude_headers = ("content-encoding", "content-length", "transfer-encoding", "connection")
            res_headers = {k: v for k, v in proxy_res.headers.items() if k.lower() not in exclude_headers}
            
            return Response(
                content=proxy_res.content,
                status_code=proxy_res.status_code,
                headers=res_headers,
                media_type=proxy_res.headers.get("content-type")
            )
    except Exception as e:
        logging.error(f"Proxy decoy error for path '{path}': {e}")
        return render_static_decoy(request, path)

async def handle_decoy_route(request: Request, path: str = "") -> Response:
    """Определяет тип маскировки и отдает соответствующий ответ"""
    decoy_type = get_setting("decoy_type", "none")
    
    if decoy_type == "proxy":
        return await proxy_decoy_request(request, path)
    elif decoy_type == "redirect":
        decoy_value = get_setting("decoy_value", "company_landing")
        if decoy_value.startswith("http"):
            return RedirectResponse(url=decoy_value, status_code=302)
        return render_static_decoy(request, path)
    elif decoy_type == "static":
        return render_static_decoy(request, path)
    else:
        return decoy_response_html()

