from fastapi import APIRouter

from backend.routes.security_routes.management import (
    router as management_router,
    client_by_connection,
    search_client,
    disable_client,
    enable_client,
    get_top_traffic
)
from backend.routes.security_routes.firewall import (
    router as firewall_router,
    block_ip_api,
    allow_ip_api
)

# Combined API router for all security client & firewall endpoints
router = APIRouter()
router.include_router(management_router)
router.include_router(firewall_router)

__all__ = [
    "router",
    "client_by_connection",
    "search_client",
    "disable_client",
    "enable_client",
    "get_top_traffic",
    "block_ip_api",
    "allow_ip_api"
]
