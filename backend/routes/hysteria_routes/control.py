import asyncio
import json
from fastapi import APIRouter, Request, WebSocket, status
from fastapi.responses import StreamingResponse
from backend.auth_utils import check_auth, decoy_response, check_ws_auth
from backend.config import HYSTERIA_LOG_PATH
from backend.hysteria import (
    start_hysteria, stop_hysteria, restart_hysteria, get_hysteria_logs, is_hysteria_running
)
from backend.i18n import t, get_lang

router = APIRouter()

@router.get("/api/hysteria/status")
async def hysteria_status(request: Request):
    if not check_auth(request):
        return decoy_response()
    return {"running": is_hysteria_running()}

@router.post("/api/hysteria/action")
async def hysteria_action(request: Request, payload: dict):
    if not check_auth(request):
        return decoy_response()

    lang = get_lang(request)
    action = payload.get("action")
    if action == "restart":
        success = restart_hysteria()
    elif action == "stop":
        stop_hysteria()
        success = True
    elif action == "start":
        success = start_hysteria()
    else:
        return {"success": False, "msg": t("invalid_action", lang=lang, category="backend")}

    return {"success": success}

@router.get("/api/hysteria/logs")
async def hysteria_logs(request: Request):
    if not check_auth(request):
        return decoy_response()
    logs = get_hysteria_logs()
    return {"success": True, "logs": logs}

@router.get("/api/hysteria/logs/stream")
async def hysteria_logs_stream(request: Request):
    """SSE endpoint for real-time Hysteria log streaming."""
    if not check_auth(request):
        return decoy_response()

    from backend.log_streamer import get_history, subscribe, unsubscribe

    async def event_generator():
        history = get_history("hysteria")
        if history:
            payload = json.dumps(history, ensure_ascii=False)
            yield f"event: history\ndata: {payload}\n\n"
        q = subscribe("hysteria")
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
            unsubscribe("hysteria", q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

@router.websocket("/api/hysteria/logs/ws")
async def hysteria_logs_ws(websocket: WebSocket):
    """Secure real-time WebSocket stream for Hysteria logs with strict authorization."""
    if not check_ws_auth(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    from backend.log_streamer import get_history, subscribe, unsubscribe
    history = get_history("hysteria")
    if history:
        await websocket.send_json({"event": "history", "data": history})

    q = subscribe("hysteria")
    try:
        while True:
            line = await q.get()
            await websocket.send_json({"event": "line", "data": line})
    except Exception:
        pass
    finally:
        unsubscribe("hysteria", q)

@router.post("/api/hysteria/logs/clear")
async def clear_hysteria_logs(request: Request):
    if not check_auth(request):
        return decoy_response()
    try:
        from backend.sentinel_core_bridge import clear_in_memory_core_logs
        from backend.log_streamer import clear_history
        clear_in_memory_core_logs("hysteria")
        clear_history("hysteria")
        if HYSTERIA_LOG_PATH.exists():
            with open(HYSTERIA_LOG_PATH, "w", encoding="utf-8") as f:
                f.truncate(0)
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": str(e)}
