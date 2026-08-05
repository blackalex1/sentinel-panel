from fastapi import APIRouter, Request
from backend.host_client import host_client

router = APIRouter()

@router.get("/api/system/bbr")
async def get_bbr_status_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    res = host_client.send_command("get_bbr_status")
    return res

@router.post("/api/system/bbr/enable")
async def enable_bbr_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    res = host_client.send_command("enable_bbr", timeout=15.0)
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    if res.get("success"):
        log_action(actor, "enable_bbr", details="status:success")
    else:
        log_action(actor, "enable_bbr", details=f"status:failed, error:{res.get('msg')}")
    return res

@router.get("/api/system/optimization/status")
async def get_optimization_status_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    res = host_client.send_command("get_optimization_status")
    return res

@router.post("/api/system/optimization/apply")
async def apply_optimizations_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    res = host_client.send_command("apply_optimizations", timeout=15.0)
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    if res.get("success"):
        log_action(actor, "apply_network_optimizations", details="status:success")
    else:
        log_action(actor, "apply_network_optimizations", details=f"status:failed, error:{res.get('msg')}")
    return res
