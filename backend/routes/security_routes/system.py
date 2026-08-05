from fastapi import APIRouter, Request
from backend.auth_utils import check_auth, decoy_response
from backend.database import db_session
from backend.models import Inbound, ClientStats

router = APIRouter()

@router.get("/api/security/backup")
async def get_backup(request: Request):
    if not check_auth(request):
        return decoy_response()
        
    try:
        from backend.backup import create_backup_dump
        dump_data = create_backup_dump()
        return {"success": True, "dump": dump_data}
    except Exception as e:
        return {"success": False, "msg": f"Failed to create backup: {e}"}

@router.get("/api/security/system-status")
async def system_status(request: Request):
    if not check_auth(request):
        return decoy_response()
        
    try:
        from backend.host_client import host_client
        stats = host_client.send_command("get_system_stats")
    except Exception:
        stats = {}
        
    try:
        from backend.routes.clients.actions import _online_emails
        online_clients = len(_online_emails)
    except Exception:
        online_clients = 0
        
    with db_session() as session:
        total_inbounds = session.query(Inbound).count()
        total_clients = session.query(ClientStats).count()
        active_clients = session.query(ClientStats).filter_by(enable=1).count()
        blocked_clients = total_clients - active_clients
        
    return {
        "success": True,
        "stats": stats,
        "counts": {
            "total_inbounds": total_inbounds,
            "total_clients": total_clients,
            "active_clients": active_clients,
            "blocked_clients": blocked_clients,
            "online_clients": online_clients
        }
    }
