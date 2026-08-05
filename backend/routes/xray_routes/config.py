import json
from fastapi import APIRouter, Request

from backend.config import XRAY_CONFIG_PATH

router = APIRouter()

@router.get("/api/xray/config")
async def xray_config(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    
    from backend.xray.config import generate_xray_config_json
    
    config_data = None
    if XRAY_CONFIG_PATH.exists():
        try:
            with open(XRAY_CONFIG_PATH, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            return {"success": False, "msg": f"Ошибка чтения конфигурационного файла: {e}"}
            
    if not config_data:
        try:
            config_data = generate_xray_config_json()
        except Exception as e:
            return {"success": False, "msg": f"Ошибка генерации конфигурации: {e}"}
            
    return {"success": True, "config": config_data}

@router.post("/api/xray/config")
async def save_xray_config(request: Request, payload: dict):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
        
    config = payload.get("config")
    if not config:
        return {"success": False, "msg": "Не указана конфигурация"}
        
    try:
        from backend.xray import restart_xray
        from backend.database import set_setting
        
        with open(XRAY_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            
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
