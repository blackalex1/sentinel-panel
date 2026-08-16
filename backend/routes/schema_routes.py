from fastapi import APIRouter, Request
from backend.sentinel_core_bridge import get_capabilities_schema
from backend.auth_utils import check_auth, decoy_response

router = APIRouter()

@router.get("/api/v1/schema/capabilities")
@router.get("/api/schema/capabilities")
@router.get("/api/v1/capabilities/schema")
@router.get("/api/capabilities/schema")
async def capabilities_schema_api(request: Request):
    """Returns the dynamic capability schema (engines, protocols, transports, security, sniffing)."""
    if not check_auth(request):
        return decoy_response()
    
    lang = request.query_params.get("lang", "ru")
    schema = get_capabilities_schema(lang)
    return {"success": True, "obj": schema}
