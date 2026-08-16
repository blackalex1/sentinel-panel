import os
from pathlib import Path
from fastapi import APIRouter, Request
from backend.auth_utils import check_auth, decoy_response
from backend.config import FRONTEND_DIR

router = APIRouter()

_COMPONENTS_CACHE = {}

@router.get("/api/components/bundle")
async def get_components_bundle(request: Request):
    """Returns bundled HTML components in a single payload to eliminate waterfall network requests."""
    if not check_auth(request):
        return decoy_response()

    components = {}
    comp_dir = FRONTEND_DIR / "components"
    if comp_dir.exists():
        for root, _, files in os.walk(comp_dir):
            for file in files:
                if file.endswith(".html"):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(FRONTEND_DIR).as_posix()
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            components[rel_path] = f.read()
                    except Exception:
                        pass

    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"success": True, "components": components},
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
