from fastapi import APIRouter, Request

from backend.database import db_session
from backend.models import AuditLog
import backend.routes.system

router = APIRouter()

@router.get("/api/audit-logs")
async def get_audit_logs_api(request: Request, page: int = 1, limit: int = 50, search: str = ""):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
    
    with db_session() as session:
        query = session.query(AuditLog)
        if search:
            query = query.filter(
                (AuditLog.username.ilike(f"%{search}%")) |
                (AuditLog.action.ilike(f"%{search}%")) |
                (AuditLog.target.ilike(f"%{search}%")) |
                (AuditLog.details.ilike(f"%{search}%"))
            )
        total = query.count()
        logs = query.order_by(AuditLog.timestamp.desc()).offset((page - 1) * limit).limit(limit).all()
        
        logs_list = [{
            "id": log.id,
            "timestamp": log.timestamp,
            "username": log.username,
            "action": log.action,
            "target": log.target,
            "details": log.details
        } for log in logs]
        
        return {
            "success": True,
            "obj": {
                "logs": logs_list,
                "total": total,
                "page": page,
                "limit": limit
            }
        }
