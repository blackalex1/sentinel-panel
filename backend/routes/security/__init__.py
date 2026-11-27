from fastapi import APIRouter
from backend.routes.security.clients import router as clients_router
from backend.routes.security.sessions import router as sessions_router
from backend.routes.security.bans import router as bans_router
from backend.routes.security.system import router as system_router

router = APIRouter()
router.include_router(clients_router)
router.include_router(sessions_router)
router.include_router(bans_router)
router.include_router(system_router)
