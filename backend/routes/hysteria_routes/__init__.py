from fastapi import APIRouter
from backend.routes.hysteria_routes.config import router as config_router
from backend.routes.hysteria_routes.control import router as control_router
from backend.routes.hysteria_routes.version import router as version_router
from backend.routes.hysteria_routes.auth import router as auth_router

router = APIRouter()
router.include_router(config_router)
router.include_router(control_router)
router.include_router(version_router)
router.include_router(auth_router)
