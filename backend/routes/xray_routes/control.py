import asyncio
import json
from fastapi import APIRouter, Request, WebSocket, status
from fastapi.responses import StreamingResponse
from backend.auth_utils import check_ws_auth

from backend.xray import (
    restart_xray, get_xray_logs, is_xray_running, stop_xray, start_xray
)
from backend.hysteria import restart_hysteria
from backend.i18n import t, get_lang

router = APIRouter()

@router.get("/api/xray/status")
async def xray_status(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    return {"running": is_xray_running()}

@router.post("/api/xray/action")
async def xray_action(request: Request, payload: dict):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
        
    lang = get_lang(request)
    action = payload.get("action")
    if action == "restart":
        success = restart_xray()
        restart_hysteria()
    elif action == "stop":
        stop_xray()
        success = True
    elif action == "start":
        success = start_xray()
    else:
        return {"success": False, "msg": t("xray_invalid_action", lang=lang, category="backend")}
        
    return {"success": success}

@router.get("/api/xray/logs")
async def xray_logs(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    logs = get_xray_logs()
    return {"success": True, "logs": logs}

@router.get("/api/xray/logs/stream")
async def xray_logs_stream(request: Request):
    """Server-Sent Events endpoint for real-time Xray log streaming."""
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()

    from backend.log_streamer import get_history, subscribe, unsubscribe

    async def event_generator():
        history = get_history("xray")
        if history:
            payload = json.dumps(history, ensure_ascii=False)
            yield f"event: history\ndata: {payload}\n\n"

        q = subscribe("xray")
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    payload = json.dumps(line, ensure_ascii=False)
                    yield f"event: line\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe("xray", q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.websocket("/api/xray/logs/ws")
async def xray_logs_ws(websocket: WebSocket):
    """Secure real-time WebSocket stream for Xray logs with strict authorization."""
    if not check_ws_auth(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    from backend.log_streamer import get_history, subscribe, unsubscribe
    history = get_history("xray")
    if history:
        await websocket.send_json({"event": "history", "data": history})

    q = subscribe("xray")
    try:
        while True:
            line = await q.get()
            await websocket.send_json({"event": "line", "data": line})
    except Exception:
        pass
    finally:
        unsubscribe("xray", q)

@router.post("/api/xray/logs/clear")
async def clear_xray_logs(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    try:
        from backend.config import XRAY_LOG_PATH
        from backend.sentinel_core_bridge import clear_in_memory_core_logs
        from backend.log_streamer import clear_history
        clear_in_memory_core_logs("xray")
        clear_history("xray")
        if XRAY_LOG_PATH.exists():
            with open(XRAY_LOG_PATH, "w", encoding="utf-8") as f:
                f.truncate(0)
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": str(e)}

