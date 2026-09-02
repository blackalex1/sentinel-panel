import json
from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.database import (
    get_all_inbounds, get_clients_for_inbound, add_inbound, update_inbound, delete_inbound, add_client_db
)
from backend.xray import restart_xray
from backend.hysteria import restart_hysteria
from backend.singbox import restart_singbox
from backend.auth_utils import check_auth, decoy_response
from backend.routes.inbound_routes.validation import validate_inbound_port_collision, validate_vless_encryption_settings
from backend.utils.service_restart import restart_services_background
from backend.i18n import t, get_lang

router = APIRouter()

class InboundCreate(BaseModel):
    remark: str
    port: int
    protocol: str
    core: Optional[str] = "xray"
    settings: dict
    streamSettings: Optional[dict] = Field(default_factory=dict)
    sniffing: Optional[dict] = Field(default_factory=dict)
    total: Optional[int] = 0
    expiryTime: Optional[int] = 0

class InboundUpdate(BaseModel):
    remark: str
    port: int
    protocol: str
    core: Optional[str] = "xray"
    settings: dict
    streamSettings: Optional[dict] = Field(default_factory=dict)
    sniffing: Optional[dict] = Field(default_factory=dict)
    enable: Optional[int] = 1
    total: Optional[int] = 0
    expiryTime: Optional[int] = 0

@router.get("/panel/api/inbounds/list")
async def list_inbounds_api(request: Request):
    if not check_auth(request):
        return decoy_response()
        
    inbounds = get_all_inbounds()
    obj_list = []
    
    for ib in inbounds:
        ib_id = ib["id"]
        clients = get_clients_for_inbound(ib_id)
        
        # Формируем settings.clients для совместимости
        db_settings_dict = json.loads(ib["settings"] or "{}")
        db_clients_list = db_settings_dict.get("clients", [])
        
        settings_dict = db_settings_dict.copy()
        settings_dict["clients"] = []
        for c in clients:
            flow = ""
            for dc in db_clients_list:
                if dc.get("email") == c["email"]:
                    flow = dc.get("flow", "")
                    break
            client_item = {
                "id": c["client_uuid_or_pwd"],
                "email": c["email"],
                "enable": bool(c["enable"]),
                "limitIp": c["limit_ip"],
                "allowedIps": c.get("allowed_ips", ""),
                "totalGB": int(c["total"] / (1024**3)) if c["total"] > 0 else 0,
                "expiryTime": c["expiry_time"]
            }
            if ib["protocol"] == "vless":
                client_item["flow"] = flow
            settings_dict["clients"].append(client_item)

        # clientStats содержит статистику трафика по клиентам
        client_stats_list = [
            {
                "id": c["id"],
                "inboundId": ib_id,
                "email": c["email"],
                "up": c["up"],
                "down": c["down"],
                "total": c["total"],
                "expiryTime": c["expiry_time"],
                "enable": bool(c["enable"]),
                "allowedIps": c.get("allowed_ips", ""),
                "limitIp": c.get("limit_ip", 0)
            } for c in clients
        ]
        
        obj_list.append({
            "id": ib_id,
            "up": ib["up"],
            "down": ib["down"],
            "total": ib["total"],
            "remark": ib["remark"],
            "enable": bool(ib["enable"]),
            "port": ib["port"],
            "protocol": ib["protocol"],
            "core": ib.get("core") or ("hysteria" if ib["protocol"] == "hysteria2" else "xray"),
            "settings": json.dumps(settings_dict),
            "streamSettings": ib["stream_settings"],
            "sniffing": ib["sniffing"],
            "expiryTime": ib["expiry_time"],
            "clientStats": client_stats_list
        })
        
    return {"success": True, "obj": obj_list}

def _sanitize_hysteria_payload(payload):
    if payload.protocol == "hysteria2":
        if payload.core != "singbox":
            payload.core = "hysteria"
        payload.sniffing = {"enabled": False, "destOverride": []}
        hysteria_opts = (payload.streamSettings or {}).get("hysteria", {})
        if hysteria_opts.get("ignoreClientBandwidth"):
            hysteria_opts["upMbps"] = 0
            hysteria_opts["downMbps"] = 0
        if hysteria_opts.get("routingViaXray"):
            import secrets
            if not hysteria_opts.get("socksUsername"):
                hysteria_opts["socksUsername"] = secrets.token_hex(12)
            if not hysteria_opts.get("socksPassword"):
                hysteria_opts["socksPassword"] = secrets.token_hex(16)
        payload.streamSettings["hysteria"] = hysteria_opts

def _sanitize_inbound_payload(payload):
    _sanitize_hysteria_payload(payload)

@router.post("/api/inbounds/create")
async def create_inbound_ui(request: Request, payload: InboundCreate):
    if not check_auth(request):
        return decoy_response()
        
    _sanitize_inbound_payload(payload)
    stream_settings = payload.streamSettings or {}
    
    # Run collision check
    err = validate_inbound_port_collision(payload.port, payload.protocol, stream_settings)
    if err:
        return {"success": False, "msg": err}

    lang = request.headers.get("accept-language", "ru")[:2].lower()
    if lang not in ("ru", "en"):
        lang = "ru"

    if payload.protocol == "vless":
        enc_err = validate_vless_encryption_settings(payload.settings, lang=lang)
        if enc_err:
            return {"success": False, "msg": enc_err}
            
    inbound_id = add_inbound(
        remark=payload.remark,
        port=payload.port,
        protocol=payload.protocol,
        core=payload.core or "xray",
        settings_dict=payload.settings,
        stream_settings_dict=stream_settings,
        sniffing_dict=payload.sniffing,
        total=payload.total,
        expiry_time=payload.expiryTime
    )
    lang = get_lang(request)
    if inbound_id:
        import secrets
        import uuid
        clients = payload.settings.get("clients", []) if payload.settings else []
        if clients:
            for c in clients:
                email = c.get("email") or "default"
                uid = c.get("id") or c.get("uuid") or c.get("password") or ""
                limit_ip = c.get("limitIp") or c.get("limit_ip") or 0
                allowed_ips = c.get("allowedIps") or c.get("allowed_ips") or ""
                total_gb = c.get("totalGB") or c.get("total_gb") or 0
                expiry_time = c.get("expiryTime") or c.get("expiry_time") or 0
                enable = 1 if c.get("enable", True) else 0
                add_client_db(inbound_id, email, uid, total_gb, expiry_time, limit_ip, enable, allowed_ips=allowed_ips)
        elif payload.settings is None:
            proto = payload.protocol.lower()
            if proto == "shadowsocks":
                import base64
                import os
                method = str(payload.settings.get("method", "") if payload.settings else "")
                pwd = payload.settings.get("password") if payload.settings else None
                if not pwd:
                    if method.startswith("2022-blake3-aes-128"):
                        pwd = base64.b64encode(os.urandom(16)).decode()
                    elif method.startswith("2022-blake3-aes-256") or method.startswith("2022-blake3-chacha20"):
                        pwd = base64.b64encode(os.urandom(32)).decode()
                    else:
                        pwd = secrets.token_urlsafe(16)
                add_client_db(inbound_id, "default", pwd)
            elif proto in ("vless", "vmess"):
                uid = str(uuid.uuid4())
                add_client_db(inbound_id, "default", uid)
            else:
                pwd = secrets.token_urlsafe(16)
                add_client_db(inbound_id, "default", pwd)

        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "create_inbound", target=f"port:{payload.port}", details=f"remark:{payload.remark}, protocol:{payload.protocol}, core:{payload.core}")
        xray_ok = restart_xray()
        restart_hysteria()
        singbox_ok = restart_singbox()
        target_core = payload.core or ("hysteria" if payload.protocol == "hysteria2" else "xray")
        if (target_core == "xray" and xray_ok is False) or (target_core == "singbox" and singbox_ok is False):
            # Rollback newly created inbound from DB so database is never left corrupted
            delete_inbound(inbound_id)
            restart_xray()
            restart_singbox()
            restart_hysteria()
            if target_core == "xray":
                from backend.xray.service import get_last_xray_error
                last_err = get_last_xray_error() or "Failed to start or validate Xray process"
                return {"success": False, "msg": t("xray_config_error", lang=lang, category="backend", error=last_err)}
            else:
                from backend.singbox.service import get_last_singbox_error
                last_err = get_last_singbox_error() or "Failed to start or validate Sing-box process"
                return {"success": False, "msg": t("singbox_config_error", lang=lang, category="backend", error=last_err)}
        return {"success": True, "id": inbound_id}
    return {"success": False, "msg": t("inbound_port_busy", lang=lang, category="backend")}

@router.post("/panel/api/inbounds/update/{inbound_id}")
async def update_inbound_ui(request: Request, inbound_id: int, payload: InboundUpdate):
    if not check_auth(request):
        return decoy_response()
        
    _sanitize_inbound_payload(payload)
    stream_settings = payload.streamSettings or {}
    
    # Run collision check
    err = validate_inbound_port_collision(payload.port, payload.protocol, stream_settings, exclude_inbound_id=inbound_id)
    if err:
        return {"success": False, "msg": err}

    lang = get_lang(request)

    if payload.protocol == "vless":
        enc_err = validate_vless_encryption_settings(payload.settings, lang=lang)
        if enc_err:
            return {"success": False, "msg": enc_err}

    # Save previous state for automatic database rollback if config validation fails
    from backend.database.crud.inbounds import get_inbound_by_id
    previous_ib = get_inbound_by_id(inbound_id)
            
    success = update_inbound(
        inbound_id=inbound_id,
        remark=payload.remark,
        port=payload.port,
        protocol=payload.protocol,
        core=payload.core or "xray",
        settings_dict=payload.settings,
        stream_settings_dict=stream_settings,
        sniffing_dict=payload.sniffing,
        enable=payload.enable,
        total=payload.total,
        expiry_time=payload.expiryTime
    )
    if success:
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "update_inbound", target=f"id:{inbound_id}", details=f"remark:{payload.remark}, port:{payload.port}, protocol:{payload.protocol}, core:{payload.core}, enable:{payload.enable}")
        xray_ok = restart_xray()
        restart_hysteria()
        singbox_ok = restart_singbox()
        target_core = payload.core or ("hysteria" if payload.protocol == "hysteria2" else "xray")
        if (target_core == "xray" and xray_ok is False) or (target_core == "singbox" and singbox_ok is False):
            # Rollback database record to previous working state
            if previous_ib:
                prev_settings = json.loads(previous_ib.get("settings") or "{}")
                prev_stream = json.loads(previous_ib.get("stream_settings") or "{}")
                prev_sniff = json.loads(previous_ib.get("sniffing") or "{}")
                update_inbound(
                    inbound_id=inbound_id,
                    remark=previous_ib["remark"],
                    port=previous_ib["port"],
                    protocol=previous_ib["protocol"],
                    core=previous_ib.get("core"),
                    settings_dict=prev_settings,
                    stream_settings_dict=prev_stream,
                    sniffing_dict=prev_sniff,
                    enable=previous_ib["enable"],
                    total=previous_ib["total"],
                    expiry_time=previous_ib["expiry_time"]
                )
                restart_xray()
                restart_singbox()
                restart_hysteria()

            if target_core == "xray":
                from backend.xray.service import get_last_xray_error
                last_err = get_last_xray_error() or "Failed to start or validate Xray process"
                return {"success": False, "msg": t("xray_config_error", lang=lang, category="backend", error=last_err)}
            else:
                from backend.singbox.service import get_last_singbox_error
                last_err = get_last_singbox_error() or "Failed to start or validate Sing-box process"
                return {"success": False, "msg": t("singbox_config_error", lang=lang, category="backend", error=last_err)}
        return {"success": True}
    return {"success": False, "msg": t("inbound_not_found_or_port_busy", lang=lang, category="backend")}

@router.post("/api/inbounds/delete/{inbound_id}")
async def delete_inbound_ui(request: Request, inbound_id: int):
    if not check_auth(request):
        return decoy_response()
    lang = get_lang(request)
    if delete_inbound(inbound_id):
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "delete_inbound", target=f"id:{inbound_id}")
        restart_services_background()
        return {"success": True}
    return {"success": False, "msg": t("inbound_not_found", lang=lang, category="backend")}

@router.post("/panel/api/inbounds/resetClientTraffic/{inbound_id}/{email}")
@router.post("/api/inbounds/resetClientTraffic/{inbound_id}/{email}")
async def reset_client_traffic_api(request: Request, inbound_id: int, email: str):
    if not check_auth(request):
        return decoy_response()
    lang = get_lang(request)
    from backend.database import reset_client_traffic_db
    from backend.sentinel_core_bridge import reset_unified_traffic_stats
    if reset_client_traffic_db(inbound_id, email):
        reset_unified_traffic_stats()
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "reset_client_traffic", target=email, details=f"inbound_id:{inbound_id}")
        return {"success": True, "msg": t("traffic_reset_success", lang=lang, category="backend", default="Traffic reset successfully")}
    return {"success": False, "msg": t("client_not_found", lang=lang, category="backend")}

@router.post("/panel/api/inbounds/resetAllClientTraffics/{inbound_id}")
@router.post("/api/inbounds/resetAllClientTraffics/{inbound_id}")
async def reset_all_client_traffics_api(request: Request, inbound_id: int):
    if not check_auth(request):
        return decoy_response()
    lang = get_lang(request)
    from backend.database import reset_all_client_traffics_for_inbound_db
    from backend.sentinel_core_bridge import reset_unified_traffic_stats
    if reset_all_client_traffics_for_inbound_db(inbound_id):
        reset_unified_traffic_stats()
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "reset_all_client_traffics", target=f"inbound_id:{inbound_id}")
        return {"success": True, "msg": t("traffic_reset_success", lang=lang, category="backend", default="Traffic reset successfully")}
    return {"success": False, "msg": t("inbound_not_found", lang=lang, category="backend")}

@router.post("/panel/api/inbounds/resetAllTraffics")
@router.post("/api/inbounds/resetAllTraffics")
async def reset_all_traffics_api(request: Request):
    if not check_auth(request):
        return decoy_response()
    lang = get_lang(request)
    from backend.database import reset_all_traffics_db
    from backend.sentinel_core_bridge import reset_unified_traffic_stats
    if reset_all_traffics_db():
        reset_unified_traffic_stats()
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "reset_all_traffics", target="global")
        return {"success": True, "msg": t("all_traffics_reset_success", lang=lang, category="backend", default="All traffics reset successfully")}
    return {"success": False, "msg": t("generic_error", lang=lang, category="backend")}

