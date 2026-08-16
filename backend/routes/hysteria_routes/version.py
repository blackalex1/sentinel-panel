from fastapi import APIRouter, Request
import backend.routes.hysteria
from backend.auth_utils import decoy_response
from backend.hysteria import (
    get_latest_hysteria_version_info, get_hysteria_releases, get_installed_hysteria_version,
    download_hysteria_core, start_hysteria, stop_hysteria
)

router = APIRouter()

@router.get("/api/hysteria/version")
async def hysteria_version(request: Request, include_prerelease: bool = False):
    if not backend.routes.hysteria.check_auth(request):
        return decoy_response()
    info = get_latest_hysteria_version_info()
    releases = get_hysteria_releases(include_prerelease=include_prerelease)
    current_installed = get_installed_hysteria_version()

    latest_ver = "Unknown"
    download_url = None
    is_pre = False

    if info and info.get("version"):
        latest_ver = info["version"]
        download_url = info.get("download_url")
        is_pre = info.get("is_prerelease", False)
    elif releases and len(releases) > 0:
        latest_ver = releases[0].get("version", "Unknown")
        download_url = releases[0].get("download_url")
        is_pre = releases[0].get("is_prerelease", False)
    elif current_installed and current_installed not in ("Not installed", "Unknown"):
        latest_ver = current_installed

    return {
        "success": True, 
        "current": current_installed, 
        "latest": latest_ver,
        "download_url": download_url,
        "is_prerelease": is_pre,
        "versions": releases
    }

@router.post("/api/hysteria/update")
async def hysteria_update(request: Request, payload: dict):
    if not backend.routes.hysteria.check_auth(request):
        return decoy_response()

    download_url = payload.get("download_url")
    try:
        stop_hysteria()
        version = download_hysteria_core(download_url)
        start_hysteria()
        return {"success": True, "version": version}
    except Exception as e:
        start_hysteria()
        return {"success": False, "msg": str(e)}
