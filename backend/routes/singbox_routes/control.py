import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import backend.routes.singbox
from backend.auth_utils import decoy_response
from backend.config import SINGBOX_LOG_PATH
from backend.singbox import (
    start_singbox, stop_singbox, restart_singbox, get_singbox_logs
)

router = APIRouter()

@router.get("/api/singbox/status")
async def singbox_status(request: Request):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()
    return {"running": backend.routes.singbox.is_singbox_running()}

@router.post("/api/singbox/action")
async def singbox_action(request: Request, payload: dict):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()

    action = payload.get("action")
    if action == "restart":
        success = restart_singbox()
    elif action == "stop":
        stop_singbox()
        success = True
    elif action == "start":
        success = start_singbox()
    else:
        return {"success": False, "msg": "Неверное действие"}

    return {"success": success}

@router.get("/api/singbox/logs")
async def singbox_logs(request: Request):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()
    logs = get_singbox_logs()
    return {"success": True, "logs": logs}

@router.get("/api/singbox/logs/stream")
async def singbox_logs_stream(request: Request):
    """SSE endpoint for real-time sing-box log streaming."""
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()

    from backend.log_streamer import get_history, subscribe, unsubscribe

    async def event_generator():
        history = get_history("singbox")
        if history:
            payload = json.dumps(history, ensure_ascii=False)
            yield f"event: history\ndata: {payload}\n\n"
        q = subscribe("singbox")
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
            unsubscribe("singbox", q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

@router.post("/api/singbox/logs/clear")
async def clear_singbox_logs(request: Request):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()
    try:
        if SINGBOX_LOG_PATH.exists():
            with open(SINGBOX_LOG_PATH, "w", encoding="utf-8") as f:
                f.truncate(0)
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": str(e)}
