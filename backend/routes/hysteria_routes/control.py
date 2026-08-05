from fastapi import APIRouter, Request
from backend.auth_utils import check_auth, decoy_response
from backend.config import HYSTERIA_LOG_PATH
from backend.hysteria import (
    start_hysteria, stop_hysteria, restart_hysteria, get_hysteria_logs, is_hysteria_running
)

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

    action = payload.get("action")
    if action == "restart":
        success = restart_hysteria()
    elif action == "stop":
        stop_hysteria()
        success = True
    elif action == "start":
        success = start_hysteria()
    else:
        return {"success": False, "msg": "Неверное действие"}

    return {"success": success}

@router.get("/api/hysteria/logs")
async def hysteria_logs(request: Request):
    if not check_auth(request):
        return decoy_response()
    logs = get_hysteria_logs()
    return {"success": True, "logs": logs}

@router.post("/api/hysteria/logs/clear")
async def clear_hysteria_logs(request: Request):
    if not check_auth(request):
        return decoy_response()
    try:
        if HYSTERIA_LOG_PATH.exists():
            with open(HYSTERIA_LOG_PATH, "w", encoding="utf-8") as f:
                f.truncate(0)
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": str(e)}
