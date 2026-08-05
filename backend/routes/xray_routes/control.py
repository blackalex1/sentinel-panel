from fastapi import APIRouter, Request

from backend.xray import (
    restart_xray, get_xray_logs, is_xray_running, stop_xray, start_xray
)
from backend.hysteria import restart_hysteria

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
        return {"success": False, "msg": "Неверное действие"}
        
    return {"success": success}

@router.get("/api/xray/logs")
async def xray_logs(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    logs = get_xray_logs()
    return {"success": True, "logs": logs}

@router.post("/api/xray/logs/clear")
async def clear_xray_logs(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    try:
        from backend.config import XRAY_LOG_PATH
        if XRAY_LOG_PATH.exists():
            with open(XRAY_LOG_PATH, "w", encoding="utf-8") as f:
                f.truncate(0)
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": str(e)}
