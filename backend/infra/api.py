from fastapi import APIRouter
from backend.routes.auth import router as auth_router
from backend.routes.inbounds import router as inbound_router
from backend.routes.clients.router import router as client_router
from backend.routes.xray.router import router as xray_router
from backend.routes.hysteria.router import router as hysteria_router
from backend.routes.singbox.router import router as singbox_router
from backend.routes.routing import router as routing_router
from backend.routes.system.router import router as system_router
from backend.routes.security import router as security_router
from backend.routes.nodes.router import router as nodes_router
from backend.routes.schema_routes import router as schema_router

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
router.include_router(schema_router)
