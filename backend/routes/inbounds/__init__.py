from fastapi import APIRouter
from backend.routes.inbounds.validation import (
    router as validation_router,
    parse_hop_ports,
    validate_inbound_port_collision,
)
from backend.routes.inbounds.crud import router as crud_router

router = APIRouter()
router.include_router(validation_router)
router.include_router(crud_router)
