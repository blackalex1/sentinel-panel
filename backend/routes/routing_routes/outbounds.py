from fastapi import APIRouter, Request
from backend.database import get_all_outbounds, get_outbound_by_id, add_outbound, update_outbound, delete_outbound
from backend.auth_utils import check_auth, decoy_response
from backend.xray import write_xray_config, restart_xray
from backend.audit import log_action, get_actor_username
from backend.i18n import t, get_lang

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
        
    lang = get_lang(request)
    remark = payload.get("remark", "").strip()
    protocol = payload.get("protocol", "").strip()
    tag = payload.get("tag", "").strip()
    settings = payload.get("settings", {})
    stream_settings = payload.get("streamSettings", {})
    enable = int(payload.get("enable", 1))
    
    if not remark or not protocol or not tag:
        return {"success": False, "msg": t("outbound_name_proto_tag_required", lang=lang, category="backend")}
        
    ob_id = add_outbound(remark, protocol, tag, settings, stream_settings, enable)
    if ob_id is None:
        return {"success": False, "msg": t("outbound_tag_must_be_unique", lang=lang, category="backend")}
        
    from backend.singbox import write_singbox_config, restart_singbox
    from backend.xray import write_xray_config, restart_xray
    from backend.hysteria import restart_hysteria

    write_singbox_config(force=True)
    write_xray_config()

    singbox_ok = restart_singbox()
    xray_ok = restart_xray()
    restart_hysteria()

    if singbox_ok is False:
        from backend.singbox.service import get_last_singbox_error
        last_err = get_last_singbox_error() or "Failed to start or validate Sing-box process"
        return {"success": False, "msg": t("singbox_config_error", lang=lang, category="backend", error=last_err)}

    if xray_ok is False:
        from backend.xray.service import get_last_xray_error
        last_err = get_last_xray_error() or "Failed to start or validate Xray process"
        return {"success": False, "msg": t("xray_config_error", lang=lang, category="backend", error=last_err)}
    
    actor = get_actor_username(request)
    log_action(actor, "create_outbound", target=tag, details=f"protocol:{protocol}, remark:{remark}")
    
    return {"success": True, "id": ob_id}

@router.post("/api/routing/outbounds/update/{id}")
async def update_outbound_api(request: Request, id: int, payload: dict):
    """Updates an existing outbound configuration by ID."""
    if not check_auth(request):
        return decoy_response()
        
    lang = get_lang(request)
    remark = payload.get("remark", "").strip()
    protocol = payload.get("protocol", "").strip()
    tag = payload.get("tag", "").strip()
    settings = payload.get("settings", {})
    stream_settings = payload.get("streamSettings", {})
    enable = int(payload.get("enable", 1))
    
    if not remark or not protocol or not tag:
        return {"success": False, "msg": t("outbound_name_proto_tag_required", lang=lang, category="backend")}
        
    success = update_outbound(id, remark, protocol, tag, settings, stream_settings, enable)
    if not success:
        return {"success": False, "msg": t("outbound_update_tag_conflict", lang=lang, category="backend")}
        
    from backend.singbox import write_singbox_config, restart_singbox
    from backend.xray import write_xray_config, restart_xray
    from backend.hysteria import restart_hysteria

    write_singbox_config(force=True)
    write_xray_config()

    singbox_ok = restart_singbox()
    xray_ok = restart_xray()
    restart_hysteria()

    if singbox_ok is False:
        from backend.singbox.service import get_last_singbox_error
        last_err = get_last_singbox_error() or "Failed to start or validate Sing-box process"
        return {"success": False, "msg": t("singbox_config_error", lang=lang, category="backend", error=last_err)}

    if xray_ok is False:
        from backend.xray.service import get_last_xray_error
        last_err = get_last_xray_error() or "Failed to start or validate Xray process"
        return {"success": False, "msg": t("xray_config_error", lang=lang, category="backend", error=last_err)}
    
    actor = get_actor_username(request)
    log_action(actor, "update_outbound", target=tag, details=f"protocol:{protocol}, remark:{remark}, enable:{enable}")
    
    return {"success": True}

@router.post("/api/routing/outbounds/delete/{id}")
async def delete_outbound_api(request: Request, id: int):
    """Deletes an outbound configuration by ID."""
    if not check_auth(request):
        return decoy_response()
        
    lang = get_lang(request)
    ob = get_outbound_by_id(id)
    if not ob:
        return {"success": False, "msg": t("outbound_not_found", lang=lang, category="backend")}
        
    if ob.get("is_system") == 1:
        return {"success": False, "msg": t("outbound_system_cannot_delete", lang=lang, category="backend")}
        
    success = delete_outbound(id)
    if not success:
        return {"success": False, "msg": t("outbound_delete_failed", lang=lang, category="backend")}
        
    from backend.utils.service_restart import restart_services_background
    restart_services_background(delay=0.5)
    
    actor = get_actor_username(request)
    log_action(actor, "delete_outbound", target=ob.get("tag"))
    
    return {"success": True}

@router.post("/api/routing/outbounds/parse-link")
async def parse_link_api(request: Request, payload: dict):
    """Parses any proxy URI using sentinel-core parser."""
    if not check_auth(request):
        return decoy_response()
        
    lang = get_lang(request)
    link = payload.get("link", "").strip()
    if not link:
        return {"success": False, "msg": t("link_is_empty", lang=lang, category="backend")}
        
    from backend.sentinel_core_bridge import parse_proxy_uri
    parsed = parse_proxy_uri(link)
    if not parsed or "error" in parsed:
        return {"success": False, "msg": parsed.get("error") if parsed else t("link_parse_failed", lang=lang, category="backend")}
        
    return {"success": True, "obj": parsed}

