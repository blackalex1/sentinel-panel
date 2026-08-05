from fastapi import APIRouter
from backend.routes.singbox_routes.config import router as config_router
from backend.routes.singbox_routes.control import router as control_router
from backend.routes.singbox_routes.version import router as version_router

router = APIRouter()
router.include_router(config_router)
router.include_router(control_router)
router.include_router(version_router)
