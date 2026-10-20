# Facade for system settings routes.
# Exposes the main settings router.

from fastapi import APIRouter
from backend.routes.system.settings_routes.general import router as general_router
from backend.routes.system.settings_routes.backups import router as backups_router
from backend.routes.system.settings_routes.network import router as network_router
from backend.routes.system.settings_routes.telegram import router as telegram_router
from backend.routes.system.settings_routes.update import router as update_router

router = APIRouter()

# Include all settings sub-routers
router.include_router(general_router)
router.include_router(backups_router)
router.include_router(network_router)
router.include_router(telegram_router)
router.include_router(update_router)
