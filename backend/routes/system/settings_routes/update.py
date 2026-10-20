"""System update checking and management routes."""

import asyncio
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple

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
    candidates = [
        os.path.join(base_dir, "bin"),
        "/app/bin",
        "/opt/sentinel-panel/bin",
        os.path.abspath("bin"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    target = os.path.join(base_dir, "bin")
    os.makedirs(target, exist_ok=True)
    return target


def _ensure_updater_path() -> None:
    """Ensures panel directory containing the updater package is on sys.path."""
    cur_file = os.path.abspath(__file__)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(cur_file)))))
    candidates = [
        base_dir,
        os.path.abspath("."),
        "/opt/sentinel-panel",
        "/app",
    ]
    for p in candidates:
        if p and os.path.isdir(p) and p not in sys.path:
            if os.path.isdir(os.path.join(p, "updater")):
                sys.path.insert(0, p)


def _detect_installed_core_version(bin_dir: str) -> Tuple[bool, str]:
    """Detects installed Sentinel-Core version via updater or direct binary/FFI inspection."""
    _ensure_updater_path()
    try:
        from updater.core.sentinel_core import SentinelCoreManager
        mgr = SentinelCoreManager(bin_dir=bin_dir, auto_mode=True)
        return mgr.get_installed_version()
    except Exception as e:
        logger.debug(f"Direct updater.core.sentinel_core check failed: {e}")

    # Fallback 1: Query HostAgent socket if available
    sock_path = "/var/run/sentinel/agent.sock"
    if os.path.exists(sock_path):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(sock_path)
            cmd = json.dumps({"action": "get_core_version"}) + "\n"
            client.sendall(cmd.encode("utf-8"))
            resp_data = client.recv(4096).decode("utf-8")
            client.close()
            resp = json.loads(resp_data)
            if resp.get("success"):
                return bool(resp.get("is_installed", False)), str(resp.get("version", "Не установлена"))
        except Exception:
            pass

    # Fallback 2: Direct FFI inspection of libsentinel-core in bin_dir
    system = platform.system().lower()
    ext = ".dll" if "windows" in system else (".dylib" if "darwin" in system else ".so")
    so_candidates = [
        os.path.join(bin_dir, f"libsentinel-core{ext}"),
        os.path.join(bin_dir, "libsentinel-core.so"),
        os.path.join(bin_dir, f"sentinel-core{ext}"),
        os.path.join(bin_dir, "sentinel-core.so"),
    ]
    for so_path in so_candidates:
        if os.path.isfile(so_path):
            try:
                ffi_cmd = [
                    sys.executable,
                    "-c",
                    f'import ctypes, re; lib = ctypes.CDLL(r"{so_path}"); lib.SentinelGetEngineVersion.restype = ctypes.c_char_p; v = lib.SentinelGetEngineVersion().decode("utf-8").strip(); print("v" + v if re.match(r"^\\d+\\.\\d+", v) else v)',
                ]
                v_out = subprocess.check_output(ffi_cmd, stderr=subprocess.DEVNULL, timeout=2).decode().strip()
                if v_out and v_out != "dev":
                    return True, v_out
            except Exception:
                pass
            return True, "Установлена (.so найдена)"

    # Fallback 3: Direct CLI check of sentinel-core binary
    exe_name = "sentinel-core.exe" if platform.system() == "Windows" else "sentinel-core"
    exe_path = os.path.join(bin_dir, exe_name)
    if os.path.isfile(exe_path):
        for arg in ["version", "--version", "-v"]:
            try:
                out = subprocess.check_output([exe_path, arg], stderr=subprocess.STDOUT, timeout=3).decode().strip()
                match = re.search(r"v\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?", out)
                if match:
                    return True, match.group(0)
                if out:
                    return True, out
            except Exception:
                continue
        return True, "Установлена"

    return False, "Не установлена"


def _check_core_release(force: bool = False) -> Dict[str, Any]:
    """Queries Sentinel-Core releases and checks installed version."""
    now = time.time()
    if not force and _CORE_CACHE["data"] and (now - _CORE_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _CORE_CACHE["data"]

    bin_dir = _get_bin_dir()
    is_installed, current_ver = _detect_installed_core_version(bin_dir)

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


def _standalone_download_core_sync(bin_dir: str, target_tag: str, force: bool = False) -> Tuple[bool, str, str]:
    """Self-contained standalone downloader for Sentinel-Core when updater package is unavailable."""
    cur_file = os.path.abspath(__file__)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(cur_file)))))

    # Step A: Check if installation/fetch_core.sh exists
    fetch_candidates = [
        os.path.join(base_dir, "installation", "fetch_core.sh"),
        "/opt/sentinel-panel/installation/fetch_core.sh",
        os.path.abspath("installation/fetch_core.sh"),
    ]
    fetch_script = next((s for s in fetch_candidates if os.path.isfile(s)), None)
    if fetch_script and platform.system() != "Windows":
        try:
            cmd = ["bash", fetch_script, bin_dir, "--auto"]
            if force:
                cmd.append("--force")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                is_inst, ver = _detect_installed_core_version(bin_dir)
                return True, ver or target_tag, f"Sentinel-Core {ver or target_tag} успешно установлен через {os.path.basename(fetch_script)}."
        except Exception as e:
            logger.warning(f"fetch_core.sh standalone execution failed: {e}")

    # Step B: Direct urllib download of release assets with multi-mirror support
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_name = "windows" if "windows" in system else ("darwin" if "darwin" in system else "linux")
    arch = "arm64" if ("arm64" in machine or "aarch64" in machine) else ("armv7" if "arm" in machine else "amd64")
    lib_ext = ".dll" if os_name == "windows" else (".dylib" if os_name == "darwin" else ".so")
    exe_ext = ".exe" if os_name == "windows" else ""

    tag = target_tag or "latest"
    base_urls = [
        f"https://github.com/blackalex1/sentinel-core/releases/download/{tag}",
        f"https://gh-proxy.com/https://github.com/blackalex1/sentinel-core/releases/download/{tag}",
        f"https://ghfast.top/https://github.com/blackalex1/sentinel-core/releases/download/{tag}",
    ]

    lib_name = f"libsentinel-core-{os_name}-{arch}{lib_ext}"
    cli_name = f"sentinel-core-{os_name}-{arch}{exe_ext}"
    target_lib = os.path.join(bin_dir, f"libsentinel-core{lib_ext}")
    target_cli = os.path.join(bin_dir, f"sentinel-core{exe_ext}")

    lib_downloaded = False
    for base in base_urls:
        url = f"{base}/{lib_name}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Sentinel-Panel-Updater/0.0.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    with open(target_lib, "wb") as f:
                        shutil.copyfileobj(resp, f)
                    if os_name != "windows":
                        try:
                            os.chmod(target_lib, 0o755)
                        except Exception:
                            pass
                    lib_downloaded = True
                    break
        except Exception as e:
            logger.debug(f"Failed to download {url}: {e}")

    # Also attempt to download the CLI executable
    for base in base_urls:
        url = f"{base}/{cli_name}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Sentinel-Panel-Updater/0.0.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    with open(target_cli, "wb") as f:
                        shutil.copyfileobj(resp, f)
                    if os_name != "windows":
                        try:
                            os.chmod(target_cli, 0o755)
                        except Exception:
                            pass
                    break
        except Exception:
            pass

    # Create alias for sentinel-core.dll/so
    alt_lib = os.path.join(bin_dir, f"sentinel-core{lib_ext}")
    try:
        if not os.path.exists(alt_lib) and os.path.exists(target_lib):
            if os_name != "windows":
                os.symlink(target_lib, alt_lib)
            else:
                shutil.copy2(target_lib, alt_lib)
    except Exception:
        pass

    if lib_downloaded:
        is_inst, ver = _detect_installed_core_version(bin_dir)
        return True, ver or target_tag, f"Sentinel-Core {ver or target_tag} успешно установлен."

    return False, "", "Не удалось загрузить бинарные файлы ядра с GitHub и CDN-зеркал."


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
            client.settimeout(60.0)
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
            else:
                logger.warning(f"HostAgent core update reported: {resp.get('msg')}")
        except Exception as e:
            logger.warning(f"HostAgent core update socket invocation failed: {e}")

    # Method 2: Direct SentinelCoreManager download
    if not applied:
        _ensure_updater_path()
        try:
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
                details = "Ошибка загрузки файлов ядра с GitHub через SentinelCoreManager."
        except Exception as e:
            logger.warning(f"Direct core update via SentinelCoreManager failed: {e}")
            details = str(e)

    # Method 3: Standalone fallback downloader if updater package is missing
    if not applied:
        try:
            logger.info("Attempting standalone core download fallback...")
            success, installed_ver, fallback_msg = await asyncio.to_thread(
                _standalone_download_core_sync, bin_dir, target_tag, force
            )
            if success:
                applied = True
                details = fallback_msg
            else:
                details = f"Ошибка установки ядра: {fallback_msg or details}"
        except Exception as e:
            logger.error(f"Standalone core download fallback failed: {e}")
            details = f"Ошибка установки ядра: {str(e)}"

    _CORE_CACHE["data"] = None

    return JSONResponse(
        content={
            "success": applied,
            "version": installed_ver or target_tag,
            "msg": details,
        }
    )
