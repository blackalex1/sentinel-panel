from fastapi import APIRouter, Request
from backend.auth_utils import check_auth, decoy_response

router = APIRouter()

@router.get("/api/security/sessions")
async def get_active_sessions(request: Request):
    if not check_auth(request):
        return decoy_response()
    try:
        from backend.database import get_all_sessions_db
        current_sid = request.cookies.get("session_id")
        sessions = get_all_sessions_db()
        result = []
        for s in sessions:
            result.append({
                "session_id": s["session_id"],
                "username": s["username"],
                "created_at": s["created_at"],
                "expires_at": s["expires_at"],
                "ip_address": s["ip_address"] or "unknown",
                "user_agent": s["user_agent"] or "unknown",
                "is_current": s["session_id"] == current_sid
            })
        return {"success": True, "sessions": result}
    except Exception as e:
        return {"success": False, "msg": f"Failed to get active sessions: {str(e)}"}


@router.post("/api/security/sessions/terminate")
async def terminate_session(request: Request):
    if not check_auth(request):
        return decoy_response()
    try:
        body = await request.json()
        target_sid = body.get("session_id")
        if not target_sid:
            return {"success": False, "msg": "Session ID is required"}
            
        from backend.database import delete_session_db
        from backend.auth_utils import ACTIVE_SESSIONS, CSRF_TOKENS
        from backend.audit import log_action, get_actor_username
        
        actor = get_actor_username(request)
        success = delete_session_db(target_sid)
        
        ACTIVE_SESSIONS.discard(target_sid)
        CSRF_TOKENS.pop(target_sid, None)
        
        if success:
            log_action(actor, "terminate_session", target=target_sid, details="Session terminated successfully")
            return {"success": True, "msg": "Сессия успешно завершена"}
        else:
            return {"success": False, "msg": "Сессия не найдена"}
    except Exception as e:
        return {"success": False, "msg": f"Failed to terminate session: {str(e)}"}
