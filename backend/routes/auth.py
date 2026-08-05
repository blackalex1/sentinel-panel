# Facade for authentication routes.
# Exposes the main router, rate limiting variables, and helpers for backward compatibility.

from fastapi import APIRouter
from backend.routes.auth_routes.login import (
    router as login_router,
    LOGIN_ATTEMPTS,
    is_ip_whitelisted_sync,
    check_rate_limit
)
from backend.routes.auth_routes.credentials import router as credentials_router
from backend.routes.auth_routes.two_factor import router as two_factor_router

router = APIRouter()

# Include submodules routers
router.include_router(login_router)
router.include_router(credentials_router)
router.include_router(two_factor_router)
