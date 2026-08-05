from fastapi import APIRouter
from backend.auth_utils import check_auth, decoy_response

from backend.routes.clients.crud import router as crud_router
from backend.routes.clients.actions import router as actions_router
from backend.routes.clients.actions import update_online_emails

router = APIRouter()
router.include_router(crud_router)
router.include_router(actions_router)

__all__ = ["router", "update_online_emails", "check_auth", "decoy_response"]
