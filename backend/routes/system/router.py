from fastapi import APIRouter
from backend.routes.system.settings import router as settings_router
from backend.routes.system.status import router as status_router
from backend.routes.system.ssl import router as ssl_router
from backend.routes.system.warp import router as warp_router
from backend.routes.system.audit import router as audit_router
from backend.routes.system.components import router as components_router

router = APIRouter()
router.include_router(settings_router)
router.include_router(status_router)
router.include_router(ssl_router)
router.include_router(warp_router)
router.include_router(audit_router)
router.include_router(components_router)
