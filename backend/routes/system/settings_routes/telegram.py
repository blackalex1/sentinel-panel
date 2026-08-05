from fastapi import APIRouter, Request
from backend.database import get_setting

router = APIRouter()

@router.post("/api/system/telegram/restart")
async def restart_telegram_bot_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    
    try:
        from backend.bot_manager import restart_telegram_bot
        success = restart_telegram_bot()
        if success:
            from backend.audit import log_action, get_actor_username
            actor = get_actor_username(request)
            log_action(actor, "restart_telegram_bot", details="status:success")
            return {"success": True, "msg": "Telegram-бот успешно перезапущен!"}
        else:
            return {"success": False, "msg": "Не удалось запустить Telegram-бот. Проверьте логи."}
    except Exception as e:
        return {"success": False, "msg": f"Ошибка перезапуска бота: {str(e)}"}

@router.get("/api/settings/telegram/token")
async def get_telegram_token_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    try:
        token = get_setting("telegram_bot_token", "")
        return {"success": True, "token": token}
    except Exception as e:
        return {"success": False, "msg": f"Ошибка получения токена: {str(e)}"}
