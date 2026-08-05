from fastapi import APIRouter
from backend.auth_utils import check_auth, decoy_response
from backend.config import save_settings_to_env

from backend.routes.system.settings import router as settings_router
from backend.routes.system.status import router as status_router
from backend.routes.system.ssl import router as ssl_router
from backend.routes.system.warp import router as warp_router
from backend.routes.system.audit import router as audit_router

router = APIRouter()
router.include_router(settings_router)
router.include_router(status_router)
router.include_router(ssl_router)
router.include_router(warp_router)
router.include_router(audit_router)

__all__ = ["router", "check_auth", "decoy_response", "save_settings_to_env"]
