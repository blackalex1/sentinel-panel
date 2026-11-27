from fastapi import APIRouter
from backend.routes.routing.outbounds import router as outbounds_router
from backend.routes.routing.rules import router as rules_router
from backend.routes.routing.testing import (
    router as testing_router,
    tcp_ping,
    system_ping,
    test_outbound_transit,
)

router = APIRouter()
router.include_router(outbounds_router)
router.include_router(rules_router)
router.include_router(testing_router)
