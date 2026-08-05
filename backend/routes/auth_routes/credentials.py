from fastapi import APIRouter, Request
from backend.auth_utils import decoy_response, check_auth
from backend.database import authenticate_admin

router = APIRouter()

@router.post("/api/settings/credentials")
async def change_credentials_api(request: Request):
    """Change administrative login username and password credentials."""
    if not check_auth(request):
        return decoy_response()
    
    try:
        body = await request.json()
        current_password = body.get("current_password")
        new_username = body.get("new_username")
        new_password = body.get("new_password")
    except Exception:
        return {"success": False, "msg": "Неверный формат запроса"}
        
    if not current_password or not new_username:
        return {"success": False, "msg": "Текущий пароль и новый логин обязательны"}
        
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    if not authenticate_admin(actor, current_password):
        return {"success": False, "msg": "Неверный текущий пароль"}
        
    from backend.models import User
    from backend.database import db_session, update_admin_credentials
    with db_session() as session:
        existing = session.query(User).filter_by(username=new_username).first()
        if existing and existing.username != actor:
            return {"success": False, "msg": "Имя пользователя уже занято"}
            
    success = update_admin_credentials(actor, new_username, new_password)
    if success:
        log_action(actor, "change_credentials", details=f"Username changed to {new_username}")
        return {"success": True, "msg": "Учетные данные успешно изменены."}
    else:
        return {"success": False, "msg": "Не удалось обновить учетные данные"}
