import json
from fastapi import APIRouter, Request

from backend.config import XRAY_CONFIG_PATH
from backend.i18n import t, get_lang

router = APIRouter()

@router.get("/api/xray/config")
async def xray_config(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    
    lang = get_lang(request)
    from backend.xray.config import generate_xray_config_json
    
    config_data = None
    if XRAY_CONFIG_PATH.exists():
        try:
            with open(XRAY_CONFIG_PATH, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            return {"success": False, "msg": t("xray_read_config_error", lang=lang, category="backend", error=str(e))}
            
    if not config_data:
        try:
            config_data = generate_xray_config_json()
        except Exception as e:
            return {"success": False, "msg": t("xray_generate_config_error", lang=lang, category="backend", error=str(e))}
            
    from backend.database import get_setting
    use_custom = get_setting("use_custom_xray_config") == "true"
    return {"success": True, "config": config_data, "use_custom": use_custom}

@router.post("/api/xray/config")
async def save_xray_config(request: Request, payload: dict):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
        
    lang = get_lang(request)
    config = payload.get("config")
    if not config:
        return {"success": False, "msg": t("xray_config_not_specified", lang=lang, category="backend")}
        
    try:
        from backend.xray import restart_xray
        from backend.database import set_setting
        
        if isinstance(config, dict) and "log" in config and isinstance(config["log"], dict):
            new_loglevel = config["log"].get("loglevel")
            if new_loglevel is not None:
                set_setting("xray_loglevel", str(new_loglevel))
            new_access = config["log"].get("access")
            if new_access is not None:
                set_setting("xray_access_log", str(new_access))
            new_error = config["log"].get("error")
            if new_error is not None:
                set_setting("xray_error_log", str(new_error))

        with open(XRAY_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            
        if payload.get("is_custom") is True:
            set_setting("use_custom_xray_config", "true")
        
        success = restart_xray()
        return {"success": success}
    except Exception as e:
        return {"success": False, "msg": str(e)}

@router.post("/api/xray/config/reset")
async def reset_xray_config(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
        
    try:
        from backend.database import set_setting
        from backend.xray import restart_xray
        
        set_setting("use_custom_xray_config", "false")
        
        success = restart_xray()
        return {"success": success}
    except Exception as e:
        return {"success": False, "msg": str(e)}
