import json
import logging
from fastapi import APIRouter, Request
from backend.database import get_all_inbounds, get_clients_for_inbound, get_setting, set_setting
import backend.hysteria
import backend.routes.hysteria as hysteria_facade
from backend.hysteria import restart_hysteria
from backend.i18n import t, get_lang

router = APIRouter()

@router.get("/api/hysteria/config")
async def hysteria_config(request: Request):
    if not hysteria_facade.check_auth(request):
        return hysteria_facade.decoy_response()

    
    lang = get_lang(request)
    try:
        inbounds = get_all_inbounds()
        hysteria_inbounds = [
            ib for ib in inbounds
            if str(ib.get("protocol", "")).lower() in ["hysteria2", "hysteria"] or str(ib.get("core", "")).lower() == "hysteria"
        ]
        
        configs_list = []
        for ib in hysteria_inbounds:
            ib_id = ib["id"]
            config_path = backend.hysteria.BIN_DIR / f"hysteria_{ib_id}.json"
            
            config_data = None
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                except Exception as e:
                    logging.warning(f"Failed to read custom config for hysteria inbound {ib_id}: {e}")
                    
            clients = get_clients_for_inbound(ib_id)
            active_clients = [c for c in clients if c and c.get("enable")]

            if config_data:
                config_data = backend.hysteria.ensure_hysteria_quic_and_log(config_data)
            else:
                try:
                    stream_settings = json.loads(ib["stream_settings"] or "{}")
                except Exception:
                    stream_settings = {}
                config_data = backend.hysteria.generate_hysteria_config(
                    ib_id, ib["port"], active_clients, stream_settings
                )
            
            use_custom = get_setting(f"use_custom_hysteria_config_{ib_id}") == "true"
            configs_list.append({
                "inbound_id": ib_id,
                "port": ib["port"],
                "remark": ib["remark"],
                "config": config_data,
                "clients": active_clients,
                "use_custom": use_custom
            })
            
        return {"success": True, "configs": configs_list}
    except Exception as e:
        logging.error(f"Error in hysteria_config API: {e}", exc_info=True)
        return {"success": False, "msg": t("generic_error", lang=lang, category="backend", error=str(e))}

@router.post("/api/hysteria/config")
async def save_hysteria_config(request: Request, payload: dict):
    if not hysteria_facade.check_auth(request):
        return hysteria_facade.decoy_response()
        
    lang = get_lang(request)
    inbound_id = payload.get("inbound_id")
    config = payload.get("config")
    if inbound_id is None or not config:
        return {"success": False, "msg": t("invalid_params", lang=lang, category="backend")}
        
    try:
        if isinstance(config, dict) and "log" in config and isinstance(config["log"], dict):
            new_level = config["log"].get("level")
            if new_level:
                set_setting("hysteria_loglevel", str(new_level))

        config_path = backend.hysteria.BIN_DIR / f"hysteria_{inbound_id}.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            
        if payload.get("is_custom") is True:
            set_setting(f"use_custom_hysteria_config_{inbound_id}", "true")
        
        success = restart_hysteria()
        if not success:
            return {"success": False, "msg": t("hysteria_restart_failed", lang=lang, category="backend")}
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": str(e)}

@router.post("/api/hysteria/config/reset")
async def reset_hysteria_config(request: Request, payload: dict = None):
    if not hysteria_facade.check_auth(request):
        return hysteria_facade.decoy_response()

        
    payload = payload or {}
    inbound_id = payload.get("inbound_id")
        
    try:
        if inbound_id is not None:
            set_setting(f"use_custom_hysteria_config_{inbound_id}", "false")
        else:
            inbounds = get_all_inbounds()
            for ib in inbounds:
                set_setting(f"use_custom_hysteria_config_{ib['id']}", "false")
        success = restart_hysteria()
        return {"success": success}
    except Exception as e:
        return {"success": False, "msg": str(e)}

