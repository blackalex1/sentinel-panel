from fastapi import APIRouter, Request
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
