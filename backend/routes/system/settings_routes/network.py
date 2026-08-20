from fastapi import APIRouter, Request
from backend.host_client import host_client

router = APIRouter()

@router.get("/api/system/bbr")
async def get_bbr_status_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    
    import os
    try:
        if os.path.exists("/proc/sys/net/ipv4/tcp_congestion_control"):
            with open("/proc/sys/net/ipv4/tcp_congestion_control", "r") as f:
                content = f.read().strip()
                return {"success": True, "bbr_enabled": (content == "bbr")}
    except Exception:
        pass

    res = host_client.send_command("get_bbr_status", timeout=1.0)
    return res

@router.post("/api/system/bbr/enable")
async def enable_bbr_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    res = host_client.send_command("enable_bbr", timeout=10.0)
    if not res.get("success"):
        try:
            from host.agent.optimizations import enable_bbr as direct_enable_bbr
            success, msg = direct_enable_bbr()
            res = {"success": success, "msg": msg}
        except Exception:
            pass

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

@router.get("/api/system/ipv6/status")
async def get_ipv6_status_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    
    import os
    try:
        proc_path = "/proc/sys/net/ipv6/conf/all/disable_ipv6"
        if os.path.exists(proc_path):
            with open(proc_path, "r") as f:
                val = f.read().strip()
                return {"success": True, "ipv6_disabled": (val == "1"), "supported": True}
    except Exception:
        pass

    res = host_client.send_command("get_ipv6_status", timeout=2.0)
    return res

@router.post("/api/system/ipv6/set")
async def set_ipv6_status_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    
    try:
        body = await request.json()
        disable = bool(body.get("disable", True))
    except Exception:
        disable = True

    res = host_client.send_command("set_ipv6_disabled", {"disable": disable}, timeout=10.0)
    if not res.get("success"):
        try:
            from host.agent.optimizations import set_ipv6_disabled as direct_set_ipv6
            success, msg = direct_set_ipv6(disable)
            res = {"success": success, "msg": msg}
        except Exception:
            pass

    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    action_name = "disable_ipv6" if disable else "enable_ipv6"
    if res.get("success"):
        log_action(actor, action_name, details="status:success")
    else:
        log_action(actor, action_name, details=f"status:failed, error:{res.get('msg')}")
    return res

