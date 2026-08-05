# Facade for nodes routes.
# Exposes the main router, auth checks, and decoys for backward compatibility and test monkeypatching.

from fastapi import APIRouter
from backend.auth_utils import check_auth, decoy_response, verify_node_token
from backend.routes.nodes_routes.admin import router as admin_router
from backend.routes.nodes_routes.reporting import router as reporting_router

router = APIRouter()

# Include submodules routers
router.include_router(admin_router)
router.include_router(reporting_router)
