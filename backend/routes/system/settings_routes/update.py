"""System update checking and management routes."""

import json
import logging
import os
import re
import socket
import subprocess
import time
import urllib.request
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from backend.auth_utils import check_auth, decoy_response
from backend.version import PANEL_VERSION

logger = logging.getLogger(__name__)
router = APIRouter()

_CACHE: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
}
_CORE_CACHE: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
}
CACHE_TTL_SECONDS = 900  # 15 minutes


def _parse_version(v_str: str) -> tuple:
    """Extract numeric components for version comparison."""
    if not v_str:
        return (0, 0, 0)
    nums = re.findall(r"\d+", v_str)
    return tuple(int(x) for x in nums) if nums else (0, 0, 0)


def _get_bin_dir() -> str:
    """Locates the bin directory for Sentinel Core."""
    cur_file = os.path.abspath(__file__)
    # update.py -> settings_routes -> system -> routes -> backend -> panel
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(cur_file)))))
    bin_dir = os.path.join(base_dir, "bin")
    if not os.path.isdir(bin_dir):
        bin_dir = os.path.abspath("bin")
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir


def _check_core_release(force: bool = False) -> Dict[str, Any]:
    """Queries Sentinel-Core releases and checks installed version."""
    now = time.time()
    if not force and _CORE_CACHE["data"] and (now - _CORE_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _CORE_CACHE["data"]

    bin_dir = _get_bin_dir()
    try:
        from updater.core.sentinel_core import SentinelCoreManager
        mgr = SentinelCoreManager(bin_dir=bin_dir, auto_mode=True)
        is_installed, current_ver = mgr.get_installed_version()
    except Exception as e:
        logger.warning(f"Error checking installed core version: {e}")
        is_installed, current_ver = False, "Не установлена"

    api_url = "https://api.github.com/repos/blackalex1/sentinel-core/releases"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "Sentinel-Panel-Updater/0.0.1",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    releases = []
    stable_ver = ""
    latest_ver = ""

    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                raw_data = json.loads(resp.read().decode("utf-8"))
                if isinstance(raw_data, list):
                    for r in raw_data:
                        t = r.get("tag_name", "")
                        if not t:
                            continue
                        releases.append({
                            "tag": t,
                            "name": r.get("name") or t,
                            "prerelease": bool(r.get("prerelease")),
                            "published_at": r.get("published_at", ""),
                            "body": r.get("body", ""),
                        })
                    if releases:
                        stable_ver = next((r["tag"] for r in releases if not r["prerelease"]), releases[0]["tag"])
                        latest_ver = releases[0]["tag"]
    except Exception as e:
        logger.warning(f"Failed to fetch Sentinel Core releases from GitHub: {e}")

    clean_curr = re.sub(r"^[^\d]*", "", current_ver)
    clean_latest = re.sub(r"^[^\d]*", "", latest_ver or stable_ver)

    if not is_installed or "dev" in current_ver.lower() or "не установлена" in current_ver.lower():
        has_update = bool(latest_ver or stable_ver)
    elif clean_latest and clean_curr:
        has_update = _parse_version(clean_latest) > _parse_version(clean_curr)
    else:
        has_update = False

    result = {
        "success": True,
        "is_installed": is_installed,
        "current_version": current_ver,
        "latest_version": latest_ver or current_ver,
        "stable_version": stable_ver or current_ver,
        "has_update": has_update,
        "releases": releases[:15],
        "release_url": "https://github.com/blackalex1/sentinel-core/releases",
    }
    _CORE_CACHE["data"] = result
    _CORE_CACHE["timestamp"] = now
    return result


def _check_github_release(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not force and _CACHE["data"] and (now - _CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _CACHE["data"]

    current_ver = PANEL_VERSION
    api_url = "https://api.github.com/repos/blackalex1/sentinel-panel/releases/latest"

    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "Sentinel-Panel-Updater/0.0.1",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag_name = data.get("tag_name", "v0.0.1")
                clean_latest = tag_name.lstrip("v")
                body = data.get("body", "")
                html_url = data.get("html_url", "")
                published_at = data.get("published_at", "")

                has_update = _parse_version(clean_latest) > _parse_version(current_ver)

                result = {
                    "success": True,
                    "current_version": current_ver,
                    "latest_version": clean_latest,
                    "tag_name": tag_name,
                    "has_update": has_update,
                    "release_notes": body,
                    "release_url": html_url,
                    "published_at": published_at,
                }
                _CACHE["data"] = result
                _CACHE["timestamp"] = now
                return result
    except Exception as e:
        logger.warning(f"Failed to check GitHub releases: {e}")

    # Fallback response if offline or GitHub API rate-limited
    fallback = {
        "success": False,
        "current_version": current_ver,
        "latest_version": current_ver,
        "tag_name": f"v{current_ver}",
        "has_update": False,
        "release_notes": "",
        "release_url": "https://github.com/blackalex1/sentinel-panel/releases",
        "published_at": "",
        "error": "Не удалось связаться с сервером обновлений GitHub",
    }
    return fallback


@router.get("/api/system/settings/update/check")
async def check_update(request: Request, force: bool = Query(False)):
    """Check for latest Sentinel Panel release on GitHub."""
    if not check_auth(request):
        return decoy_response()

    result = _check_github_release(force=force)
    return JSONResponse(content=result)


@router.post("/api/system/settings/update/apply")
async def apply_update(request: Request):
    """Trigger background update of the panel."""
    if not check_auth(request):
        return decoy_response()

    logger.info("Initiating Sentinel Panel update...")
    applied = False
    details = ""

    # Method 1: Unix socket to HostAgent
    sock_path = "/var/run/sentinel/agent.sock"
    if os.path.exists(sock_path):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(3.0)
            client.connect(sock_path)
            cmd = json.dumps({"action": "trigger_panel_update"}) + "\n"
            client.sendall(cmd.encode("utf-8"))
            resp_data = client.recv(4096).decode("utf-8")
            client.close()
            resp = json.loads(resp_data)
            if resp.get("success"):
                applied = True
                details = resp.get("msg", "HostAgent принял команду на обновление.")
        except Exception as e:
            logger.warning(f"HostAgent update socket invocation failed: {e}")

    # Method 2: Fallback to update.sh invocation
    if not applied:
        possible_paths = [
            "/opt/sentinel-panel/update.sh",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "update.sh"),
            "update.sh",
        ]
        for p in possible_paths:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                try:
                    subprocess.Popen(
                        ["bash", p],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    applied = True
                    details = f"Скрипт обновления {p} запущен в фоне."
                    break
                except Exception as e:
                    logger.warning(f"Failed to spawn {p}: {e}")

    # Method 3: Fallback inside Docker (docker compose pull)
    if not applied:
        try:
            subprocess.Popen(
                "docker compose pull && docker compose up -d",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            applied = True
            details = "Запущена фоновая загрузка Docker-образов."
        except Exception as e:
            details = f"Ошибка запуска обновления: {e}"

    # Clear cache so next check will query freshly
    _CACHE["data"] = None

    return JSONResponse(
        content={
            "success": applied,
            "msg": details or "Команда на обновление передана. Панель перезагрузится через несколько секунд.",
        }
    )


@router.get("/api/system/settings/update/core/check")
async def check_core_update(request: Request, force: bool = Query(False)):
    """Check for latest Sentinel-Core engine releases on GitHub."""
    if not check_auth(request):
        return decoy_response()

    result = _check_core_release(force=force)
    return JSONResponse(content=result)


@router.post("/api/system/settings/update/core/apply")
async def apply_core_update(request: Request):
    """Update or reinstall Sentinel Core engine."""
    if not check_auth(request):
        return decoy_response()

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    target_tag = payload.get("version", "").strip()
    force = bool(payload.get("force", False))

    logger.info(f"Initiating Sentinel Core installation (tag={target_tag or 'latest'}, force={force})...")
    bin_dir = _get_bin_dir()

    applied = False
    details = ""
    installed_ver = ""

    # Method 1: HostAgent socket if available
    sock_path = "/var/run/sentinel/agent.sock"
    if os.path.exists(sock_path):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(12.0)
            client.connect(sock_path)
            cmd = json.dumps({"action": "trigger_core_update", "version": target_tag, "force": force}) + "\n"
            client.sendall(cmd.encode("utf-8"))
            resp_data = client.recv(4096).decode("utf-8")
            client.close()
            resp = json.loads(resp_data)
            if resp.get("success"):
                applied = True
                installed_ver = resp.get("version", target_tag)
                details = resp.get("msg", "HostAgent успешно выполнил установку ядра.")
        except Exception as e:
            logger.warning(f"HostAgent core update socket invocation failed: {e}")

    # Method 2: Direct SentinelCoreManager download
    if not applied:
        try:
            import asyncio
            from updater.core.sentinel_core import SentinelCoreManager

            mgr = SentinelCoreManager(bin_dir=bin_dir, auto_mode=True, force=force)
            if not target_tag:
                stable_v, pre_v, latest_v = await asyncio.to_thread(mgr.fetch_releases)
                target_tag = stable_v or latest_v

            if not target_tag:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "msg": "Не удалось определить версию ядра для загрузки"},
                )

            success = await asyncio.to_thread(mgr.download_core, target_tag)
            if success:
                applied = True
                _, installed_ver = mgr.get_installed_version()
                details = f"Sentinel-Core {installed_ver or target_tag} успешно {'переустановлен' if force else 'обновлен'}."
            else:
                details = "Ошибка загрузки файлов ядра с GitHub."
        except Exception as e:
            logger.error(f"Direct core update failed: {e}")
            details = f"Ошибка установки ядра: {str(e)}"

    _CORE_CACHE["data"] = None

    return JSONResponse(
        content={
            "success": applied,
            "version": installed_ver or target_tag,
            "msg": details,
        }
    )
