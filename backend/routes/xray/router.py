from fastapi import APIRouter
from backend.routes.xray.control import router as control_router
from backend.routes.xray.version import router as version_router
from backend.routes.xray.keys import router as keys_router
from backend.routes.xray.config import router as config_router
from backend.routes.xray.geo import router as geo_router

router = APIRouter()
router.include_router(control_router)
router.include_router(version_router)
router.include_router(keys_router)
router.include_router(config_router)
router.include_router(geo_router)
