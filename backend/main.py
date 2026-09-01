import asyncio
import logging
import time
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


from backend.config import settings, BASE_DIR
from backend.database import init_db
from backend.xray import start_xray, stop_xray, query_traffic_stats
from backend.hysteria import start_hysteria, stop_hysteria, query_hysteria_traffic
from backend.singbox import start_singbox, stop_singbox, query_singbox_traffic
from backend.api import router
from backend.auth_utils import decoy_response, handle_decoy_route, DecoyException

# Настройка логирования — уровень берётся из config/.env (LOG_LEVEL=INFO по умолчанию)
_log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(level=_log_level, format="%(asctime)s - %(levelname)s - %(message)s")

# Фоновые задачи
polling_task = None
session_sync_task = None


async def sync_session_events_loop():
    """High-speed background worker (every 2s) syncing core SessionTracker events, active sessions, and ACTIVE_IP_CACHE into AuditLog."""
    logging.info("Started background session events synchronization task.")
    seen_events: set[tuple] = set()
    reconciled_active: set[tuple] = set()

    while True:
        try:
            await asyncio.sleep(2)
            from backend.sentinel_core_bridge import get_recent_session_events, get_active_sessions
            from backend.audit import log_action
            from backend.client_alerts import get_singbox_user_traffic, get_xray_user_traffic
            from backend.database import db_session
            from backend.models import AuditLog

            # 1. Process recent event stream from Go sentinel-core SessionTracker
            events = get_recent_session_events(0, limit=100)
            if events and isinstance(events, list):
                for ev in events:
                    ev_ts = ev.get("timestamp", 0)
                    action_type = ev.get("action")
                    core_name = str(ev.get("core", "singbox")).replace("-", "")
                    action = f"{core_name}_{action_type}"
                    email = ev.get("email")
                    ip = ev.get("ip")
                    if email and ip and ip != "127.0.0.1":
                        ev_key = (core_name, action_type, email, ip, ev_ts)
                        if ev_key in seen_events:
                            continue
                        seen_events.add(ev_key)
                        if len(seen_events) > 5000:
                            seen_events.clear()

                        if action_type == "disconnect":
                            reconciled_active.discard((core_name, email, ip))

                        is_dup = False
                        with db_session() as a_sess:
                            dup_count = a_sess.query(AuditLog).filter(
                                AuditLog.action == action,
                                AuditLog.target == ip,
                                AuditLog.timestamp >= int(time.time()) - 10
                            ).count()
                            is_dup = dup_count > 0
                        if not is_dup:
                            tx, rx = get_singbox_user_traffic(email) if "sing" in core_name else get_xray_user_traffic(email)
                            details_dict = {"username": email, "tx": tx, "rx": rx}
                            if action_type == "disconnect":
                                details_dict["duration"] = ev.get("duration", "несколько секунд")
                            logging.info(f"[SessionTracker Sync] Recording AuditLog: action={action}, target={ip}, user={email}")
                            log_action(
                                username="system",
                                action=action,
                                target=ip,
                                details=json.dumps(details_dict, ensure_ascii=False)
                            )

            # 2. Active sessions reconciliation: ensure all active core sessions have an AuditLog entry
            active_list = get_active_sessions()
            current_active_keys = set()
            if active_list and isinstance(active_list, list):
                for sess_info in active_list:
                    email = sess_info.get("email")
                    ip = sess_info.get("ip")
                    core_name = str(sess_info.get("core", "singbox")).replace("-", "")
                    action = f"{core_name}_connect"
                    if email and ip and ip != "127.0.0.1":
                        s_key = (core_name, email, ip)
                        current_active_keys.add(s_key)
                        if s_key not in reconciled_active:
                            with db_session() as a_sess:
                                has_recent = a_sess.query(AuditLog).filter(
                                    AuditLog.action == action,
                                    AuditLog.target == ip,
                                    AuditLog.timestamp >= int(time.time()) - 30
                                ).count() > 0
                            if not has_recent:
                                tx, rx = get_singbox_user_traffic(email) if "sing" in core_name else get_xray_user_traffic(email)
                                details_dict = {"username": email, "tx": tx, "rx": rx}
                                logging.info(f"[SessionTracker Sync] Reconciled active session in AuditLog: action={action}, target={ip}, user={email}")
                                log_action(
                                    username="system",
                                    action=action,
                                    target=ip,
                                    details=json.dumps(details_dict, ensure_ascii=False)
                                )
                            reconciled_active.add(s_key)

            # Clean reconciled sessions that are no longer active
            for stale_key in list(reconciled_active):
                if stale_key not in current_active_keys:
                    reconciled_active.discard(stale_key)

            # 3. Secondary check: ACTIVE_IP_CACHE from Clash API / Xray API
            try:
                from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                if ACTIVE_IP_CACHE:
                    now_sec = int(time.time())
                    for c_user, c_ip_map in list(ACTIVE_IP_CACHE.items()):
                        if isinstance(c_ip_map, dict):
                            for c_ip, c_last_seen in list(c_ip_map.items()):
                                if c_ip and c_ip != "127.0.0.1" and (now_sec - int(c_last_seen)) < 60:
                                    s_key = ("singbox", c_user, c_ip)
                                    if s_key not in reconciled_active:
                                        with db_session() as a_sess:
                                            has_audit = a_sess.query(AuditLog).filter(
                                                AuditLog.target == c_ip,
                                                AuditLog.action.in_(("singbox_connect", "xray_connect", "hysteria2_connect", "hysteria_connect")),
                                                AuditLog.timestamp >= now_sec - 30
                                            ).count() > 0
                                        if not has_audit:
                                            tx, rx = get_singbox_user_traffic(c_user)
                                            details_dict = {"username": c_user, "tx": tx, "rx": rx}
                                            logging.info(f"[SessionTracker Sync] Reconciled ACTIVE_IP_CACHE in AuditLog: user={c_user}, ip={c_ip}")
                                            log_action(
                                                username="system",
                                                action="singbox_connect",
                                                target=c_ip,
                                                details=json.dumps(details_dict, ensure_ascii=False)
                                            )
                                        reconciled_active.add(s_key)
            except Exception as e:
                logging.debug(f"[SessionTracker Sync] ACTIVE_IP_CACHE check: {e}")

        except asyncio.CancelledError:
            logging.info("Session events synchronization task cancelled.")
            break
        except Exception as e:
            logging.error(f"[SessionTracker Sync] Error syncing core session events: {e}", exc_info=True)


async def poll_xray_stats_loop():
    logging.info("Started background traffic statistics polling task.")
    
    # Fast-probe cores API ready status with 300ms intervals instead of static 5s sleep
    for attempt in range(15):
        await asyncio.sleep(0.3)
        try:
            await asyncio.to_thread(query_traffic_stats)
            await asyncio.to_thread(query_hysteria_traffic)
            await asyncio.to_thread(query_singbox_traffic)
            break
        except Exception:
            pass

    # Run the initial statistics and online check immediately at startup to populate caches
    try:
        await asyncio.to_thread(query_traffic_stats)
        await asyncio.to_thread(query_hysteria_traffic)
        await asyncio.to_thread(query_singbox_traffic)
        
        from backend.routes.clients import update_online_emails
        await asyncio.to_thread(update_online_emails)
        
        from backend.scheduler import enforce_client_limits_and_rules
        await asyncio.to_thread(enforce_client_limits_and_rules)

        # Warm up GitHub core releases cache asynchronously in background
        async def _warmup_core_releases():
            try:
                from backend.singbox.core import get_singbox_releases
                from backend.xray.core import get_xray_releases
                from backend.hysteria.core import get_hysteria_releases
                await asyncio.to_thread(get_singbox_releases)
                await asyncio.to_thread(get_xray_releases)
                await asyncio.to_thread(get_hysteria_releases)
            except Exception:
                pass

        asyncio.create_task(_warmup_core_releases())
    except Exception as e:
        logging.error(f"Error in initial stats polling: {e}")
        
    last_releases_refresh = time.time()
    while True:
        try:
            await asyncio.sleep(5)
            await asyncio.to_thread(query_traffic_stats)
            await asyncio.to_thread(query_hysteria_traffic)
            await asyncio.to_thread(query_singbox_traffic)
            
            from backend.routes.clients import update_online_emails
            await asyncio.to_thread(update_online_emails)

            # Update active Telegram cards traffic on the panel
            try:
                from backend.telegram_alerts import update_panel_active_cards_traffic
                await update_panel_active_cards_traffic()
            except Exception as e:
                logging.error(f"Error updating active panel cards: {e}")
                
            # Проверка лимитов клиентов (лимит трафика, срок действия, лимит IP)
            from backend.scheduler import enforce_client_limits_and_rules
            await asyncio.to_thread(enforce_client_limits_and_rules)

            # Автоматическое фоновое обновление версий ядер каждые 30 минут
            if time.time() - last_releases_refresh > 1800:
                last_releases_refresh = time.time()
                asyncio.create_task(_warmup_core_releases())
        except asyncio.CancelledError:
            logging.info("Background traffic statistics polling task cancelled.")
            break
        except Exception as e:
            logging.error(f"Error in stats polling: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global polling_task
    # Инициализация БД
    init_db()
    
    # Синхронизация статуса WARP с хоста при запуске
    try:
        from backend.host_client import host_client
        from backend.routes.system.warp import sync_warp_outbound_state
        status = host_client.send_command("get_warp_status", timeout=15.0)
        if isinstance(status, dict) and "connected" in status:
            sync_warp_outbound_state(status["connected"])
    except Exception as e:
        logging.error(f"Failed to perform startup WARP status sync: {e}")
    
    # Генерация дефолтных самоподписанных сертификатов при старте
    try:
        from backend.ssl_utils import generate_default_self_signed_cert
        generate_default_self_signed_cert()
    except Exception as e:
        logging.error(f"Failed to generate default self-signed certificate: {e}")
        
    # Загрузка словарей локализации
    from backend.i18n import load_translations
    load_translations()
    
    # Запуск Xray, Hysteria 2 и sing-box
    start_xray()
    start_hysteria()
    try:
        start_singbox()
    except Exception as e:
        logging.error(f"Failed to start sing-box at startup: {e}")
    
    # Запуск фоновых сборщиков и стримеров логов ядер
    from backend.log_streamer import ensure_log_tailers
    ensure_log_tailers()

    # Запуск фонового опроса трафика и синхронизации сессий
    polling_task = asyncio.create_task(poll_xray_stats_loop())
    session_sync_task = asyncio.create_task(sync_session_events_loop())
    
    yield
    
    # Отмена фоновых задач
    if session_sync_task:
        session_sync_task.cancel()
    if polling_task:
        polling_task.cancel()
        
    # Остановка Xray, Hysteria 2 и sing-box
    stop_xray()
    stop_hysteria()
    stop_singbox()

# Отключаем документацию для скрытности (Stealth Mode)
app = FastAPI(
    title="Sentinel Panel",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code in (404, 405):
        path = request.url.path.lstrip("/")
        return await handle_decoy_route(request, path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(DecoyException)
async def decoy_exception_handler(request: Request, exc: DecoyException):
    path = request.url.path.lstrip("/")
    return await handle_decoy_route(request, path)

from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from backend.auth_utils import check_auth
    if not check_auth(request):
        path = request.url.path.lstrip("/")
        return await handle_decoy_route(request, path)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )




# Настройка CORS
# В продакшене фронтенд раздается на том же хосте/порту, что и API, поэтому CORS не требуется.
# Для разработки (например, с Vite на порту 5173) разрешаем локальные хосты.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)  # nosec B104

# Подключение сжатия Gzip для ответов API
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Middleware для правильного кэширования статики и отключения кэша для HTML
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        if "No response returned" in str(exc):
            from backend.auth.decoy import RawDropResponse
            return RawDropResponse()
        raise exc

    path = request.url.path
    if path.startswith(f"/{settings.PANEL_SECRET_PATH}"):
        clean_path = path.rstrip("/")
        if clean_path.endswith(f"/{settings.PANEL_SECRET_PATH}") or clean_path.endswith(".html"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif any(clean_path.endswith(ext) for ext in (".js", ".css", ".svg", ".png", ".jpg", ".woff2", ".woff", ".ttf", ".ico")):
            response.headers["Cache-Control"] = "private, max-age=86400"

    # Mask real server technology — replace uvicorn header with nginx decoy on all responses
    response.headers["Server"] = "nginx/1.24.0 (Ubuntu)"
    try:
        del response.headers["x-powered-by"]
    except (KeyError, Exception):
        pass
    return response

# Подключаем API роутер
app.include_router(router)

# Роут для Let's Encrypt HTTP-01 верификации
@app.get("/.well-known/acme-challenge/{token}")
async def acme_challenge(token: str):
    from backend.acme_client import ACME_CHALLENGES
    if token in ACME_CHALLENGES:
        return Response(content=ACME_CHALLENGES[token], media_type="text/plain")
    return Response(content="Challenge not found", status_code=404, media_type="text/plain")

# Роут для отдачи приманки (Decoy) на корневом пути
@app.get("/")
async def get_decoy_root(request: Request):
    return await handle_decoy_route(request)

# Подключаем фронтенд-статику по секретному пути
frontend_dir = BASE_DIR / "frontend"
dist_react_dir = BASE_DIR / "dist-react"
primary_dir = dist_react_dir if dist_react_dir.exists() else frontend_dir

class AuthenticatedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        norm_path = path.replace("\\", "/").lstrip("/")
        
        # Ручная обработка пути /react для обратной совместимости
        if norm_path == "react" or norm_path.startswith("react/"):
            rel_react_path = norm_path[5:].lstrip("/") if norm_path.startswith("react/") else (norm_path[5:] if norm_path.startswith("react") else "")
            if rel_react_path == "" or rel_react_path == "index.html":
                target_file = dist_react_dir / "index.html"
            else:
                target_file = dist_react_dir / rel_react_path
            
            if target_file.exists() and target_file.is_file():
                from starlette.responses import FileResponse
                res = FileResponse(str(target_file))
                if target_file.name == "index.html":
                    res.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                return res
            elif (dist_react_dir / "index.html").exists():
                from starlette.responses import FileResponse
                res = FileResponse(str(dist_react_dir / "index.html"))
                res.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                return res

        is_component = norm_path.startswith("components/")
        is_private_js = "js/" in norm_path and any(x in norm_path for x in (
            "panel-main.js", "dashboard.js", "hysteria.js", "routing.js", 
            "inbound-modal.js", "clients.js", "modules/"
        ))
        
        if is_component or is_private_js:
            from backend.auth_utils import check_auth, decoy_response
            req = Request(scope)
            if not check_auth(req):
                return decoy_response()
        
        response = await super().get_response(path, scope)
        
        # Prevent any caching of frontend assets during active development and updates
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
            
        return response

if frontend_dir.exists():
    app.mount(
        f"/{settings.PANEL_SECRET_PATH}", 
        AuthenticatedStaticFiles(directory=str(frontend_dir), html=True), 
        name="frontend"
    )
    logging.info(f"Frontend mounted at: /{settings.PANEL_SECRET_PATH}/")

else:
    logging.warning("Frontend directory not found. Serving API only.")

# Роут-фолбек на все остальные пути для скрытности
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path_name: str):
    # Если путь не совпадает с секретным путем, отдаем заглушку Nginx или маскируемся
    return await handle_decoy_route(request, path_name)

if __name__ == "__main__":
    import uvicorn
    from backend.ssl_utils import generate_default_self_signed_cert, SSL_CERT_PATH, SSL_KEY_PATH
    
    # Гарантируем наличие сертификатов перед запуском веб-сервера
    try:
        generate_default_self_signed_cert()
    except Exception as e:
        logging.error(f"Failed to generate default self-signed certificate before startup: {e}")
        
    ssl_key = str(SSL_KEY_PATH) if SSL_KEY_PATH.exists() else None
    ssl_cert = str(SSL_CERT_PATH) if SSL_CERT_PATH.exists() else None
    
    if ssl_key and ssl_cert:
        logging.info(f"Starting HTTPS server on port {settings.PANEL_PORT}...")
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=settings.PANEL_PORT,
            ssl_keyfile=ssl_key,
            ssl_certfile=ssl_cert,
            server_header=False,
            reload=False
        )  # nosec B104
    else:
        logging.warning("SSL certificates not found. Starting HTTP server...")
        logging.info(f"Starting server on port {settings.PANEL_PORT}...")
        uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.PANEL_PORT, server_header=False, reload=False)  # nosec B104

