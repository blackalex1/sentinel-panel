import json
from fastapi import APIRouter, Request
import backend.routes.singbox
from backend.auth_utils import decoy_response
from backend.config import SINGBOX_CONFIG_PATH
from backend.singbox import generate_singbox_config_json, write_singbox_config, is_singbox_running, restart_singbox

router = APIRouter()

@router.get("/api/singbox/config")
async def singbox_config(request: Request):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()

    config_dict = None
    if SINGBOX_CONFIG_PATH.exists():
        try:
            with open(SINGBOX_CONFIG_PATH, "r", encoding="utf-8") as f:
                config_dict = json.load(f)
        except Exception as e:
            return {"success": False, "msg": f"Ошибка чтения конфигурационного файла: {e}"}

    if not config_dict:
        try:
            config_dict = generate_singbox_config_json()
            write_singbox_config(config_dict)
        except Exception as e:
            return {"success": False, "msg": f"Ошибка генерации конфигурации: {e}"}

    from backend.database import get_setting
    use_custom = get_setting("use_custom_singbox_config") == "true"
    return {"success": True, "config": config_dict, "use_custom": use_custom}

@router.post("/api/singbox/config")
@router.post("/api/singbox/config/save")
async def singbox_config_save(request: Request, payload: dict):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()

    try:
        from backend.database import set_setting
        raw_config = payload.get("config")
        if isinstance(raw_config, str):
            config_dict = json.loads(raw_config)
        else:
            config_dict = raw_config

        if isinstance(config_dict, dict) and "log" in config_dict and isinstance(config_dict["log"], dict):
            new_level = config_dict["log"].get("level")
            if new_level:
                set_setting("singbox_loglevel", str(new_level))

        if payload.get("is_custom") is True:
            set_setting("use_custom_singbox_config", "true")

        success = write_singbox_config(config_dict)
        if success and is_singbox_running():
            restart_singbox()
        return {"success": success}
    except Exception as e:
        return {"success": False, "msg": str(e)}

@router.post("/api/singbox/config/reset")
async def singbox_config_reset(request: Request):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()

    try:
        from backend.database import set_setting
        set_setting("use_custom_singbox_config", "false")
        config_dict = generate_singbox_config_json()
        success = write_singbox_config(config_dict)
        if success and is_singbox_running():
            restart_singbox()
        return {"success": True, "config": config_dict}
    except Exception as e:
        return {"success": False, "msg": str(e)}
