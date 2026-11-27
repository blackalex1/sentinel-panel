from fastapi import APIRouter
from backend.routes.clients.crud import router as crud_router
from backend.routes.clients.actions import router as actions_router

router = APIRouter()
router.include_router(crud_router)
router.include_router(actions_router)
