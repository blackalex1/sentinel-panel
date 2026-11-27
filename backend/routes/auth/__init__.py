from fastapi import APIRouter
from backend.routes.auth.login import (
    router as login_router,
    LOGIN_ATTEMPTS,
    is_ip_whitelisted_sync,
    check_rate_limit,
)
from backend.routes.auth.credentials import router as credentials_router
from backend.routes.auth.two_factor import router as two_factor_router

router = APIRouter()
router.include_router(login_router)
router.include_router(credentials_router)
router.include_router(two_factor_router)
