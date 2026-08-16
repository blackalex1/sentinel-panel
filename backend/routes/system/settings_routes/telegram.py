from fastapi import APIRouter, Request
from backend.database import get_setting
from backend.i18n import t, get_lang

router = APIRouter()

@router.post("/api/system/telegram/restart")
async def restart_telegram_bot_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    
    lang = get_lang(request)
    try:
        from backend.bot_manager import restart_telegram_bot
        success = restart_telegram_bot()
        if success:
            from backend.audit import log_action, get_actor_username
            actor = get_actor_username(request)
            log_action(actor, "restart_telegram_bot", details="status:success")
            return {"success": True, "msg": t("telegram_bot_restarted_success", lang=lang, category="backend")}
        else:
            return {"success": False, "msg": t("telegram_bot_restart_failed", lang=lang, category="backend")}
    except Exception as e:
        return {"success": False, "msg": t("telegram_bot_restart_error", lang=lang, category="backend", error=str(e))}

@router.get("/api/settings/telegram/token")
async def get_telegram_token_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    lang = get_lang(request)
    try:
        token = get_setting("telegram_bot_token", "")
        return {"success": True, "token": token}
    except Exception as e:
        return {"success": False, "msg": t("telegram_bot_get_token_error", lang=lang, category="backend", error=str(e))}
