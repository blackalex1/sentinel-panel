# Facade for security routes.
# Exposes the main router, log paths, and log parser helper functions for backward compatibility.

from fastapi import APIRouter
from backend.config import XRAY_LOG_PATH, HYSTERIA_LOG_PATH
from backend.routes.security_routes.clients import (
    router as clients_router,
    find_email_in_hysteria_log,
    find_email_in_xray_log
)
from backend.routes.security_routes.sessions import router as sessions_router
from backend.routes.security_routes.bans import router as bans_router
from backend.routes.security_routes.system import router as system_router

router = APIRouter()

# Include all sub-routers
router.include_router(clients_router)
router.include_router(sessions_router)
router.include_router(bans_router)
router.include_router(system_router)
