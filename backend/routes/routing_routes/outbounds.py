from fastapi import APIRouter, Request
from backend.database import get_all_outbounds, get_outbound_by_id, add_outbound, update_outbound, delete_outbound
from backend.auth_utils import check_auth, decoy_response
from backend.xray import write_xray_config, restart_xray
from backend.audit import log_action, get_actor_username

router = APIRouter()

@router.get("/api/routing/outbounds")
async def list_outbounds_api(request: Request):
    """Lists all configured outbounds."""
    if not check_auth(request):
        return decoy_response()
    return {"success": True, "obj": get_all_outbounds()}

@router.post("/api/routing/outbounds/create")
async def create_outbound_api(request: Request, payload: dict):
    """Creates a new outbound configuration."""
    if not check_auth(request):
        return decoy_response()
        
    remark = payload.get("remark", "").strip()
    protocol = payload.get("protocol", "").strip()
    tag = payload.get("tag", "").strip()
    settings = payload.get("settings", {})
    stream_settings = payload.get("streamSettings", {})
    enable = int(payload.get("enable", 1))
    
    if not remark or not protocol or not tag:
        return {"success": False, "msg": "Название, протокол и тег обязательны"}
        
    ob_id = add_outbound(remark, protocol, tag, settings, stream_settings, enable)
    if ob_id is None:
        return {"success": False, "msg": "Тег исходящего подключения должен быть уникальным"}
        
    write_xray_config()
    restart_xray()
    
    actor = get_actor_username(request)
    log_action(actor, "create_outbound", target=tag, details=f"protocol:{protocol}, remark:{remark}")
    
    return {"success": True, "id": ob_id}

@router.post("/api/routing/outbounds/update/{id}")
async def update_outbound_api(request: Request, id: int, payload: dict):
    """Updates an existing outbound configuration by ID."""
    if not check_auth(request):
        return decoy_response()
        
    remark = payload.get("remark", "").strip()
    protocol = payload.get("protocol", "").strip()
    tag = payload.get("tag", "").strip()
    settings = payload.get("settings", {})
    stream_settings = payload.get("streamSettings", {})
    enable = int(payload.get("enable", 1))
    
    if not remark or not protocol or not tag:
        return {"success": False, "msg": "Название, протокол и тег обязательны"}
        
    success = update_outbound(id, remark, protocol, tag, settings, stream_settings, enable)
    if not success:
        return {"success": False, "msg": "Ошибка обновления. Возможно, тег уже используется"}
        
    write_xray_config()
    restart_xray()
    
    actor = get_actor_username(request)
    log_action(actor, "update_outbound", target=tag, details=f"protocol:{protocol}, remark:{remark}, enable:{enable}")
    
    return {"success": True}

@router.post("/api/routing/outbounds/delete/{id}")
async def delete_outbound_api(request: Request, id: int):
    """Deletes an outbound configuration by ID."""
    if not check_auth(request):
        return decoy_response()
        
    ob = get_outbound_by_id(id)
    if not ob:
        return {"success": False, "msg": "Исходящее подключение не найдено"}
        
    if ob.get("is_system") == 1:
        return {"success": False, "msg": "Системные исходящие подключения нельзя удалять"}
        
    success = delete_outbound(id)
    if not success:
        return {"success": False, "msg": "Не удалось удалить исходящее подключение"}
        
    write_xray_config()
    restart_xray()
    
    actor = get_actor_username(request)
    log_action(actor, "delete_outbound", target=ob.get("tag"))
    
    return {"success": True}
