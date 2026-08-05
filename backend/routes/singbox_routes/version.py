from fastapi import APIRouter, Request
import backend.routes.singbox
from backend.auth_utils import decoy_response
from backend.singbox import (
    get_latest_singbox_version_info, get_singbox_releases, get_installed_singbox_version,
    download_singbox_core, start_singbox, stop_singbox
)

router = APIRouter()

@router.get("/api/singbox/version")
async def singbox_version(request: Request, include_prerelease: bool = False):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()
    info = get_latest_singbox_version_info(include_prerelease=include_prerelease)
    releases = get_singbox_releases(include_prerelease=include_prerelease)
    current_installed = get_installed_singbox_version()

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

@router.post("/api/singbox/update")
async def singbox_update(request: Request, payload: dict):
    if not backend.routes.singbox.check_auth(request):
        return decoy_response()

    download_url = payload.get("download_url")
    try:
        stop_singbox()
        version = download_singbox_core(download_url)
        start_singbox()
        return {"success": True, "version": version}
    except Exception as e:
        start_singbox()
        return {"success": False, "msg": str(e)}
