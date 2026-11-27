from fastapi import APIRouter
from backend.routes.nodes.admin import router as admin_router
from backend.routes.nodes.reporting import router as reporting_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(reporting_router)
