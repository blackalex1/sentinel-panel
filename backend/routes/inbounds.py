# Facade for inbounds routes.
# Exposes the main router and helper functions for backward compatibility.

from fastapi import APIRouter
from backend.routes.inbound_routes.validation import (
    router as validation_router,
    parse_hop_ports,
    validate_inbound_port_collision
)
from backend.routes.inbound_routes.crud import router as crud_router

router = APIRouter()

# Include submodules routers
router.include_router(validation_router)
router.include_router(crud_router)
