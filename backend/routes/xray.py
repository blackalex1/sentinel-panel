# Facade for xray routes.
# Exposes the main router and auth functions for backward compatibility and test monkeypatching.

from fastapi import APIRouter
from backend.auth_utils import check_auth, decoy_response
from backend.routes.xray_routes.control import router as control_router
from backend.routes.xray_routes.version import router as version_router
from backend.routes.xray_routes.keys import router as keys_router
from backend.routes.xray_routes.config import router as config_router
from backend.routes.xray_routes.geo import router as geo_router

router = APIRouter()

# Include all submodules routers
router.include_router(control_router)
router.include_router(version_router)
router.include_router(keys_router)
router.include_router(config_router)
router.include_router(geo_router)
