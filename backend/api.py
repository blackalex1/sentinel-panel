from fastapi import APIRouter
from backend.auth_utils import decoy_response
from backend.routes.auth import router as auth_router
from backend.routes.inbounds import router as inbound_router
from backend.routes.clients import router as client_router
from backend.routes.xray import router as xray_router
from backend.routes.hysteria import router as hysteria_router
from backend.routes.singbox import router as singbox_router
from backend.routes.routing import router as routing_router
from backend.routes.system import router as system_router
from backend.routes.security import router as security_router
from backend.routes.nodes import router as nodes_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(inbound_router)
router.include_router(client_router)
router.include_router(xray_router)
router.include_router(hysteria_router)
router.include_router(singbox_router)
router.include_router(routing_router)
router.include_router(system_router)
router.include_router(security_router)
router.include_router(nodes_router)


