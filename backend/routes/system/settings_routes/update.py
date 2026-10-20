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
CACHE_TTL_SECONDS = 900  # 15 minutes


def _parse_version(v_str: str) -> tuple:
    """Extract numeric components for version comparison."""
    if not v_str:
        return (0, 0, 0)
    nums = re.findall(r"\d+", v_str)
    return tuple(int(x) for x in nums) if nums else (0, 0, 0)


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
