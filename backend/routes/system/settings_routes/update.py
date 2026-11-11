"""System update checking and management routes."""

import asyncio
import hashlib
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
import threading
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from backend.auth_utils import check_auth, decoy_response
from backend.version import PANEL_VERSION

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_UPDATE_CHANNELS = ("stable", "beta")

_CACHE: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
    "channel": None,
}
_CORE_CACHE: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
    "channel": None,
}
CACHE_TTL_SECONDS = 900  # 15 minutes

_PROGRESS_LOCK = threading.Lock()
_CORE_DOWNLOAD_PROGRESS: Dict[str, Any] = {
    "active": False,
    "percent": 0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "speed": "0.0 KB/s",
    "eta": "--",
    "stage": "",
    "filename": "",
    "finished": False,
    "success": False,
    "error": "",
}


def _set_core_progress(
    active: Optional[bool] = None,
    percent: Optional[int] = None,
    downloaded_bytes: Optional[int] = None,
    total_bytes: Optional[int] = None,
    speed: Optional[str] = None,
    eta: Optional[str] = None,
    stage: Optional[str] = None,
    filename: Optional[str] = None,
    finished: Optional[bool] = None,
    success: Optional[bool] = None,
    error: Optional[str] = None,
) -> None:
    with _PROGRESS_LOCK:
        if active is not None:
            _CORE_DOWNLOAD_PROGRESS["active"] = active
        if percent is not None:
            _CORE_DOWNLOAD_PROGRESS["percent"] = percent
        if downloaded_bytes is not None:
            _CORE_DOWNLOAD_PROGRESS["downloaded_bytes"] = downloaded_bytes
        if total_bytes is not None:
            _CORE_DOWNLOAD_PROGRESS["total_bytes"] = total_bytes
        if speed is not None:
            _CORE_DOWNLOAD_PROGRESS["speed"] = speed
        if eta is not None:
            _CORE_DOWNLOAD_PROGRESS["eta"] = eta
        if stage is not None:
            _CORE_DOWNLOAD_PROGRESS["stage"] = stage
        if filename is not None:
            _CORE_DOWNLOAD_PROGRESS["filename"] = filename
        if finished is not None:
            _CORE_DOWNLOAD_PROGRESS["finished"] = finished
        if success is not None:
            _CORE_DOWNLOAD_PROGRESS["success"] = success
        if error is not None:
            _CORE_DOWNLOAD_PROGRESS["error"] = error


def _on_core_download_progress(data: Dict[str, Any]) -> None:
    _set_core_progress(
        active=True,
        percent=data.get("percent"),
        downloaded_bytes=data.get("downloaded_bytes"),
        total_bytes=data.get("total_bytes"),
        speed=data.get("speed"),
        eta=data.get("eta"),
        stage=data.get("stage"),
        filename=data.get("filename"),
        finished=data.get("finished"),
        success=data.get("success"),
        error=data.get("error", ""),
    )


def _normalize_update_channel(channel: Optional[str]) -> str:
    """Normalize update channel value to 'stable' (default) or 'beta'."""
    val = str(channel or "").strip().lower()
    if val in ("beta", "prerelease", "pre-release", "pre", "all"):
        return "beta"
    return "stable"


def _get_update_channel() -> str:
    """Read configured update channel from DB settings, defaulting cleanly to 'stable'."""
    try:
        from backend.database.crud.settings import get_setting
        return _normalize_update_channel(get_setting("update_channel", "stable"))
    except Exception:
        return "stable"


def _invalidate_update_caches() -> None:
    """Reset both panel and sentinel-core update check caches."""
    _CACHE["data"] = None
    _CACHE["timestamp"] = 0.0
    _CACHE["channel"] = None
    _CORE_CACHE["data"] = None
    _CORE_CACHE["timestamp"] = 0.0
    _CORE_CACHE["channel"] = None


def _get_loaded_core_version_safe() -> Optional[str]:
    """Return the version of sentinel-core currently mapped into this process's RAM, if any."""
    try:
        from backend.sentinel_core_bridge import get_loaded_core_version
        return get_loaded_core_version()
    except Exception:
        return None


def _is_prerelease_tag(v_str: str, prerelease_flag: bool = False) -> bool:
    """Return True if marked as prerelease or if the SemVer tag carries a pre-release suffix."""
    if prerelease_flag:
        return True
    if not v_str:
        return False
    s = str(v_str).strip().lstrip("vV").split("+", 1)[0]
    if "-" not in s:
        return False
    base_part, pre_part = s.split("-", 1)
    return bool(re.match(r"^\d+(?:\.\d+)*$", base_part) and pre_part.strip())


def _normalize_version_str(v_str: Optional[str]) -> str:
    """Normalize a version tag for equality checks (strips leading 'v' and non-version text)."""
    if not v_str:
        return ""
    s = str(v_str).strip()
    lower = s.lower()
    if lower in ("dev", "не установлена", "unknown") or lower.startswith("установлена"):
        return ""
    match = re.search(r"v?(\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?)", s)
    if match:
        return match.group(1).lower()
    return s.lstrip("vV").lower()


def _version_sort_key(v_str: str) -> tuple:
    """SemVer sort key where stable 0.0.26 > 0.0.26-beta.2 > 0.0.26-beta > 0.0.25."""
    if not v_str:
        return ((0, 0, 0), 0, ())
    s = str(v_str).strip().lstrip("vV").split("+", 1)[0]
    if "-" in s and re.match(r"^\d+(?:\.\d+)*-", s):
        base_part, pre_part = s.split("-", 1)
    else:
        base_part, pre_part = s, ""

    nums = [int(x) for x in re.findall(r"\d+", base_part)] or [0, 0, 0]
    while len(nums) < 3:
        nums.append(0)

    is_stable = 0 if pre_part.strip() else 1
    pre_tokens = []
    if pre_part.strip():
        for seg in re.split(r"[.\-]+", pre_part.strip()):
            if not seg:
                continue
            for sub in re.findall(r"\d+|[a-zA-Z]+", seg):
                if sub.isdigit():
                    pre_tokens.append((0, int(sub)))
                else:
                    pre_tokens.append((1, sub.lower()))
    return (tuple(nums), is_stable, tuple(pre_tokens))


def _is_newer_version(candidate: str, current: str) -> bool:
    """Return True strictly when candidate SemVer is newer than current SemVer."""
    cand_norm = _normalize_version_str(candidate)
    curr_norm = _normalize_version_str(current)
    if not cand_norm or not curr_norm:
        return False
    return _version_sort_key(cand_norm) > _version_sort_key(curr_norm)


def _is_restart_required(is_installed: bool, disk_version: str, loaded_version: Optional[str]) -> bool:
    """Return True when a different core library is already mapped in RAM vs installed on disk."""
    if not is_installed or loaded_version is None:
        return False
    disk_norm = _normalize_version_str(disk_version)
    loaded_raw = str(loaded_version).strip().lower()
    if loaded_raw == "dev":
        return bool(disk_norm)
    loaded_norm = _normalize_version_str(loaded_version)
    if disk_norm and loaded_norm:
        return loaded_norm != disk_norm
    return False


def _parse_version(v_str: str) -> tuple:
    """Extract numeric components for version comparison."""
    if not v_str:
        return (0, 0, 0)
    base_str = str(v_str).strip().split("+", 1)[0].split("-", 1)[0]
    nums = re.findall(r"\d+", base_str)
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


def _query_host_agent(
    payload: Dict[str, Any],
    timeout: float = 3.0,
    sock_path: str = "/var/run/sentinel/agent.sock",
) -> Optional[Dict[str, Any]]:
    """Send a JSON command to HostAgent over its Unix socket and return parsed JSON."""
    if not hasattr(socket, "AF_UNIX") or not os.path.exists(sock_path):
        return None
    client = None
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        client.connect(sock_path)
        cmd = json.dumps(payload) + "\n"
        client.sendall(cmd.encode("utf-8"))
        resp_data = client.recv(4096).decode("utf-8")
        return json.loads(resp_data)
    except Exception as e:
        logger.warning(f"HostAgent socket invocation ({payload.get('action')}) failed: {e}")
        return None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


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
    resp = _query_host_agent({"action": "get_core_version"}, timeout=2.0)
    if isinstance(resp, dict) and resp.get("success"):
        return bool(resp.get("is_installed", False)), str(resp.get("version", "Не установлена"))

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


def _check_core_release(force: bool = False, channel: Optional[str] = None) -> Dict[str, Any]:
    """Queries Sentinel-Core releases, filtering by update channel ('stable' or 'beta')."""
    active_channel = _normalize_update_channel(channel) if channel is not None else _get_update_channel()
    now = time.time()
    if (
        not force
        and _CORE_CACHE["data"]
        and _CORE_CACHE.get("channel") == active_channel
        and (now - _CORE_CACHE["timestamp"] < CACHE_TTL_SECONDS)
    ):
        cached = dict(_CORE_CACHE["data"])
        loaded_ver = _get_loaded_core_version_safe()
        cached["loaded_version"] = loaded_ver
        cached["restart_required"] = _is_restart_required(
            bool(cached.get("is_installed")),
            str(cached.get("current_version", "")),
            loaded_ver,
        )
        return cached

    bin_dir = _get_bin_dir()
    is_installed, current_ver = _detect_installed_core_version(bin_dir)

    api_url = "https://api.github.com/repos/blackalex1/sentinel-core/releases"
    all_releases = []
    fetch_ok = False

    if not api_url.startswith(("https://", "http://")):
        return {"success": False, "error": "Invalid update API URL"}

    import requests
    try:
        resp = requests.get(
            api_url,
            headers={
                "User-Agent": f"Sentinel-Panel-Updater/{PANEL_VERSION}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=6
        )
        if resp.status_code == 200:
            raw_data = resp.json()
            fetch_ok = True
            if isinstance(raw_data, list):
                for r in raw_data:
                    if not isinstance(r, dict) or r.get("draft"):
                        continue
                    t = r.get("tag_name", "")
                    if not t:
                        continue
                    all_releases.append({
                        "tag": t,
                        "name": r.get("name") or t,
                        "prerelease": _is_prerelease_tag(t, bool(r.get("prerelease"))),
                        "published_at": r.get("published_at", ""),
                        "body": r.get("body", ""),
                    })
                all_releases.sort(
                    key=lambda item: (_version_sort_key(item["tag"]), item.get("published_at", "")),
                    reverse=True,
                )
    except Exception as e:
        logger.warning(f"Failed to fetch Sentinel Core releases from GitHub: {e}")

    stable_releases = [r for r in all_releases if not r["prerelease"]]
    visible_releases = all_releases if active_channel == "beta" else stable_releases

    stable_ver = stable_releases[0]["tag"] if stable_releases else ""
    latest_any_ver = all_releases[0]["tag"] if all_releases else ""
    chosen_release = visible_releases[0] if visible_releases else None
    latest_ver = chosen_release["tag"] if chosen_release else ""
    latest_is_prerelease = bool(chosen_release["prerelease"]) if chosen_release else False

    if not latest_ver:
        has_update = False
    elif not is_installed or "dev" in current_ver.lower() or "не установлена" in current_ver.lower():
        has_update = True
    else:
        has_update = _is_newer_version(latest_ver, current_ver)

    loaded_ver = _get_loaded_core_version_safe()
    restart_required = _is_restart_required(is_installed, current_ver, loaded_ver)

    result = {
        "success": True,
        "channel": active_channel,
        "is_installed": is_installed,
        "current_version": current_ver,
        "latest_version": latest_ver or current_ver,
        "stable_version": stable_ver or current_ver,
        "latest_any_version": latest_any_ver or current_ver,
        "latest_is_prerelease": latest_is_prerelease,
        "has_update": has_update,
        "loaded_version": loaded_ver,
        "restart_required": restart_required,
        "releases": visible_releases[:15],
        "release_url": "https://github.com/blackalex1/sentinel-core/releases",
    }
    if fetch_ok:
        _CORE_CACHE["data"] = result
        _CORE_CACHE["timestamp"] = now
        _CORE_CACHE["channel"] = active_channel
    return result


def _check_github_release(force: bool = False, channel: Optional[str] = None) -> Dict[str, Any]:
    active_channel = _normalize_update_channel(channel) if channel is not None else _get_update_channel()
    now = time.time()
    if (
        not force
        and _CACHE["data"]
        and _CACHE.get("channel") == active_channel
        and (now - _CACHE["timestamp"] < CACHE_TTL_SECONDS)
    ):
        return _CACHE["data"]

    current_ver = PANEL_VERSION
    base_api = "https://api.github.com/repos/blackalex1/sentinel-panel"
    headers = {
        "User-Agent": f"Sentinel-Panel-Updater/{PANEL_VERSION}",
        "Accept": "application/vnd.github.v3+json",
    }

    def _entry_from_raw(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict) or raw.get("draft"):
            return None
        tag_name = str(raw.get("tag_name") or "").strip()
        if not tag_name:
            return None
        return {
            "tag_name": tag_name,
            "prerelease": _is_prerelease_tag(tag_name, bool(raw.get("prerelease"))),
            "body": raw.get("body", "") or "",
            "html_url": raw.get("html_url", "") or f"https://github.com/blackalex1/sentinel-panel/releases/tag/{tag_name}",
            "published_at": raw.get("published_at", "") or "",
        }

    import requests
    chosen: Optional[Dict[str, Any]] = None
    stable_entry: Optional[Dict[str, Any]] = None
    github_reachable = False

    try:
        if active_channel == "beta":
            resp = requests.get(f"{base_api}/releases", headers=headers, timeout=6)
            if resp.status_code == 200:
                github_reachable = True
                raw_data = resp.json()
                raw_items = raw_data if isinstance(raw_data, list) else [raw_data]
                entries = [e for e in (_entry_from_raw(item) for item in raw_items) if e]
                entries.sort(
                    key=lambda item: (_version_sort_key(item["tag_name"]), item.get("published_at", "")),
                    reverse=True,
                )
                if entries:
                    chosen = entries[0]
                    stable_entry = next((e for e in entries if not e["prerelease"]), None)
        else:
            resp = requests.get(f"{base_api}/releases/latest", headers=headers, timeout=6)
            if resp.status_code == 200:
                github_reachable = True
                raw_data = resp.json()
                raw_items = raw_data if isinstance(raw_data, list) else [raw_data]
                entries = [e for e in (_entry_from_raw(item) for item in raw_items) if e and not e["prerelease"]]
                entries.sort(
                    key=lambda item: (_version_sort_key(item["tag_name"]), item.get("published_at", "")),
                    reverse=True,
                )
                if entries:
                    chosen = entries[0]
                    stable_entry = chosen

            # If /releases/latest returned 404 (e.g. only pre-releases exist) or gave a beta-tagged release, check /releases
            if chosen is None and resp.status_code in (200, 404):
                list_resp = requests.get(f"{base_api}/releases", headers=headers, timeout=6)
                if list_resp.status_code == 200:
                    github_reachable = True
                    raw_list = list_resp.json()
                    raw_items = raw_list if isinstance(raw_list, list) else [raw_list]
                    stable_entries = [e for e in (_entry_from_raw(item) for item in raw_items) if e and not e["prerelease"]]
                    stable_entries.sort(
                        key=lambda item: (_version_sort_key(item["tag_name"]), item.get("published_at", "")),
                        reverse=True,
                    )
                    if stable_entries:
                        chosen = stable_entries[0]
                        stable_entry = chosen
    except Exception as e:
        logger.warning(f"Failed to check GitHub releases: {e}")

    if chosen is not None:
        tag_name = chosen["tag_name"]
        clean_latest = tag_name.lstrip("vV")
        has_update = _is_newer_version(clean_latest, current_ver)
        result = {
            "success": True,
            "channel": active_channel,
            "current_version": current_ver,
            "latest_version": clean_latest,
            "stable_version": stable_entry["tag_name"].lstrip("vV") if stable_entry else "",
            "tag_name": tag_name,
            "is_prerelease": bool(chosen["prerelease"]),
            "has_update": has_update,
            "release_notes": chosen["body"],
            "release_url": chosen["html_url"],
            "published_at": chosen["published_at"],
        }
        _CACHE["data"] = result
        _CACHE["timestamp"] = now
        _CACHE["channel"] = active_channel
        return result

    if github_reachable:
        # GitHub responded cleanly, e.g. only pre-releases exist while user is on 'stable' channel.
        no_stable_result = {
            "success": True,
            "channel": active_channel,
            "current_version": current_ver,
            "latest_version": current_ver,
            "stable_version": "",
            "tag_name": f"v{current_ver.lstrip('vV')}",
            "is_prerelease": False,
            "has_update": False,
            "release_notes": "",
            "release_url": "https://github.com/blackalex1/sentinel-panel/releases",
            "published_at": "",
        }
        _CACHE["data"] = no_stable_result
        _CACHE["timestamp"] = now
        _CACHE["channel"] = active_channel
        return no_stable_result

    # Fallback response if offline or GitHub API rate-limited
    fallback = {
        "success": False,
        "channel": active_channel,
        "current_version": current_ver,
        "latest_version": current_ver,
        "stable_version": "",
        "tag_name": f"v{current_ver}",
        "is_prerelease": False,
        "has_update": False,
        "release_notes": "",
        "release_url": "https://github.com/blackalex1/sentinel-panel/releases",
        "published_at": "",
        "error": "Не удалось связаться с сервером обновлений GitHub",
    }
    return fallback


def _sha256_file(file_path: str) -> str:
    """Compute lowercase SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _parse_checksums_map(raw_text: str) -> Dict[str, str]:
    """Parse sha256sum-style checksums.txt content into {filename: sha256}."""
    mapping: Dict[str, str] = {}
    for line in (raw_text or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            fname = parts[-1].lstrip("*").split("/")[-1]
            mapping[fname] = parts[0].lower()
    return mapping


def _download_staged_asset(
    base_urls: list,
    asset_name: str,
    dest_path: str,
    progress_callback: Optional[Any] = None,
) -> Tuple[bool, str]:
    """Download asset_name across mirror base URLs into dest_path, returning (ok, base_url)."""
    import requests

    part_path = f"{dest_path}.part"
    for base in base_urls:
        url = f"{base}/{asset_name}"
        if not url.startswith(("https://", "http://")):
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": f"Sentinel-Panel-Updater/{PANEL_VERSION}"}, stream=True, timeout=30)
            if resp.status_code != 200:
                continue
            cl_header = resp.headers.get("Content-Length")
            total_bytes = int(cl_header) if cl_header and cl_header.isdigit() else 0
            downloaded = 0
            start_time = time.time()
            last_cb_time = start_time
            with open(part_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if progress_callback and (now - last_cb_time >= 0.1 or (total_bytes > 0 and downloaded >= total_bytes)):
                        last_cb_time = now
                        elapsed = max(0.001, now - start_time)
                        speed = downloaded / elapsed
                        spd_str = f"{speed / (1024*1024):.1f} MB/s" if speed >= 1024*1024 else f"{speed / 1024:.1f} KB/s"
                        pct = int((downloaded / total_bytes) * 100) if total_bytes > 0 else 0
                        rem = max(0, total_bytes - downloaded)
                        eta_s = int(rem / speed) if speed > 0 and total_bytes > 0 else 0
                        eta_str = f"{eta_s}s" if eta_s < 60 else f"{eta_s // 60}m {eta_s % 60}s"
                        progress_callback({
                            "stage": f"Загрузка {asset_name}",
                            "percent": pct,
                            "downloaded_bytes": downloaded,
                            "total_bytes": total_bytes,
                            "speed": spd_str,
                            "eta": eta_str,
                            "filename": asset_name,
                            "finished": False,
                        })
            if downloaded > 0:
                os.replace(part_path, dest_path)
                return True, base
        except Exception as e:
            logger.debug(f"Failed to download {url}: {e}")
        finally:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass
    return False, ""


def _standalone_download_core_sync(
    bin_dir: str,
    target_tag: str,
    force: bool = False,
    progress_callback: Optional[Any] = None,
    channel: str = "stable",
) -> Tuple[bool, str, str]:
    """Self-contained standalone downloader for Sentinel-Core with atomic staging."""
    active_channel = _normalize_update_channel(channel)
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
            if progress_callback:
                progress_callback({"stage": "Запуск fetch_core.sh...", "percent": 10})
            cmd = ["bash", fetch_script, bin_dir, "--auto"]
            if target_tag:
                cmd.extend(["--tag", target_tag])
            if active_channel == "beta" or _is_prerelease_tag(target_tag):
                cmd.append("--beta")
            if force:
                cmd.append("--force")
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                is_inst, ver = _detect_installed_core_version(bin_dir)
                expected_norm = _normalize_version_str(target_tag)
                actual_norm = _normalize_version_str(ver)
                if is_inst and (not expected_norm or not actual_norm or actual_norm == expected_norm):
                    if progress_callback:
                        progress_callback({"stage": "Sentinel-Core успешно установлен!", "percent": 100, "finished": True, "success": True})
                    return True, ver or target_tag, f"Sentinel-Core {ver or target_tag} успешно установлен через {os.path.basename(fetch_script)}."
                logger.warning(
                    f"fetch_core.sh finished but version mismatch (expected={target_tag}, got={ver}); falling back to direct download."
                )
        except Exception as e:
            logger.warning(f"fetch_core.sh standalone execution failed: {e}")

    # Step B: Direct staged download of release assets with multi-mirror support
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_name = "windows" if "windows" in system else ("darwin" if "darwin" in system else "linux")
    arch = "arm64" if ("arm64" in machine or "aarch64" in machine) else ("armv7" if "arm" in machine else "amd64")
    lib_ext = ".dll" if os_name == "windows" else (".dylib" if os_name == "darwin" else ".so")
    exe_ext = ".exe" if os_name == "windows" else ""

    tag = (target_tag or "").strip()
    if not tag:
        info = _check_core_release(force=True, channel=active_channel)
        rel_list = info.get("releases") or []
        if rel_list:
            tag = rel_list[0].get("tag", "")
        elif active_channel == "beta":
            return False, "", "Не найден доступный релиз Sentinel-Core для выбранного канала."

    if tag:
        base_urls = [
            f"https://github.com/blackalex1/sentinel-core/releases/download/{tag}",
            f"https://gh-proxy.com/https://github.com/blackalex1/sentinel-core/releases/download/{tag}",
            f"https://ghfast.top/https://github.com/blackalex1/sentinel-core/releases/download/{tag}",
        ]
    else:
        base_urls = [
            "https://github.com/blackalex1/sentinel-core/releases/latest/download",
            "https://gh-proxy.com/https://github.com/blackalex1/sentinel-core/releases/latest/download",
            "https://ghfast.top/https://github.com/blackalex1/sentinel-core/releases/latest/download",
        ]

    os.makedirs(bin_dir, exist_ok=True)
    lib_name = f"libsentinel-core-{os_name}-{arch}{lib_ext}"
    cli_name = f"sentinel-core-{os_name}-{arch}{exe_ext}"
    target_lib = os.path.join(bin_dir, f"libsentinel-core{lib_ext}")
    target_cli = os.path.join(bin_dir, f"sentinel-core{exe_ext}")

    staging_dir = os.path.join(bin_dir, f".staging.{os.getpid()}")
    os.makedirs(staging_dir, exist_ok=True)
    staged_lib = os.path.join(staging_dir, f"libsentinel-core{lib_ext}")
    staged_cli = os.path.join(staging_dir, f"sentinel-core{exe_ext}")

    try:
        lib_downloaded, matched_base = _download_staged_asset(
            base_urls, lib_name, staged_lib, progress_callback=progress_callback
        )
        if not lib_downloaded:
            return False, "", "Не удалось загрузить бинарные файлы ядра с GitHub и CDN-зеркал."

        # Verify optional checksums.txt if published with release
        checksums: Dict[str, str] = {}
        try:
            import requests
            cs_urls = [f"{matched_base}/checksums.txt"] + [f"{b}/checksums.txt" for b in base_urls if b != matched_base]
            for cs_url in cs_urls:
                cs_resp = requests.get(cs_url, headers={"User-Agent": f"Sentinel-Panel-Updater/{PANEL_VERSION}"}, timeout=10)
                if cs_resp.status_code == 200 and cs_resp.text:
                    checksums = _parse_checksums_map(cs_resp.text)
                    if checksums:
                        break
        except Exception as e:
            logger.debug(f"Optional checksums.txt fetch skipped: {e}")

        if lib_name in checksums:
            actual_sha = _sha256_file(staged_lib)
            if actual_sha != checksums[lib_name]:
                return False, "", f"Ошибка проверки SHA-256 для {lib_name} (ожидался {checksums[lib_name][:12]}..., получен {actual_sha[:12]}...)."

        cli_urls = [matched_base] + [b for b in base_urls if b != matched_base]
        cli_downloaded, _ = _download_staged_asset(
            cli_urls, cli_name, staged_cli, progress_callback=progress_callback
        )
        if cli_downloaded and cli_name in checksums:
            if _sha256_file(staged_cli) != checksums[cli_name]:
                logger.warning(f"SHA-256 mismatch for optional CLI asset {cli_name}; skipping CLI replacement.")
                cli_downloaded = False

        if os_name != "windows":
            try:
                # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
                os.chmod(staged_lib, 0o755)
            except Exception:
                pass
        os.replace(staged_lib, target_lib)

        if cli_downloaded and os.path.exists(staged_cli):
            if os_name != "windows":
                try:
                    # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
                    os.chmod(staged_cli, 0o755)
                except Exception:
                    pass
            os.replace(staged_cli, target_cli)

        # Refresh alias sentinel-core.so/dll atomically
        alt_lib = os.path.join(bin_dir, f"sentinel-core{lib_ext}")
        tmp_alias = os.path.join(staging_dir, f"sentinel-core{lib_ext}")
        try:
            if os_name != "windows":
                os.symlink(os.path.basename(target_lib), tmp_alias)
            else:
                shutil.copy2(target_lib, tmp_alias)
            os.replace(tmp_alias, alt_lib)
        except Exception:
            pass

        if progress_callback:
            progress_callback({
                "stage": "Sentinel-Core успешно установлен!",
                "percent": 100,
                "finished": True,
                "success": True,
            })
        is_inst, ver = _detect_installed_core_version(bin_dir)
        return True, ver or target_tag, f"Sentinel-Core {ver or target_tag} успешно установлен."
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


@router.get("/api/system/settings/update/channel")
async def get_update_channel_api(request: Request):
    """Get active release update channel ('stable' or 'beta')."""
    if not check_auth(request):
        return decoy_response()

    return JSONResponse(content={"success": True, "channel": _get_update_channel()})


@router.post("/api/system/settings/update/channel")
async def set_update_channel_api(request: Request):
    """Persist release update channel ('stable' or 'beta') and clear update caches."""
    if not check_auth(request):
        return decoy_response()

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    raw = str(payload.get("channel", "")).strip().lower()
    if raw in ("stable", "release"):
        new_channel = "stable"
    elif raw in ("beta", "prerelease", "pre-release", "pre"):
        new_channel = "beta"
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "msg": "Некорректный канал обновлений (допустимо: stable, beta)."},
        )

    try:
        from backend.database.crud.settings import set_setting
        set_setting("update_channel", new_channel)
    except Exception as e:
        logger.error(f"Failed to persist update_channel setting: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "msg": f"Ошибка сохранения канала обновлений: {e}"},
        )

    _invalidate_update_caches()
    return JSONResponse(
        content={
            "success": True,
            "channel": new_channel,
            "msg": (
                "Включены бета-версии (Pre-release) для панели и ядра."
                if new_channel == "beta"
                else "Выбран канал только стабильных релизов (Stable)."
            ),
        }
    )


@router.post("/api/system/settings/panel/restart")
async def restart_panel_api(request: Request):
    """Schedule graceful panel process restart to reload updated core library from disk."""
    if not check_auth(request):
        return decoy_response()

    _CORE_CACHE["data"] = None
    restarting = False
    try:
        from backend.runtime import schedule_panel_restart
        restarting = schedule_panel_restart(delay_seconds=1.0, reason="manual restart after core update")
    except Exception as e:
        logger.error(f"Failed to schedule panel restart: {e}")
        return JSONResponse(status_code=500, content={"success": False, "restarting": False, "msg": str(e)})

    return JSONResponse(
        content={
            "success": True,
            "restarting": restarting,
            "msg": (
                "Панель перезапускается для применения обновлённой библиотеки ядра..."
                if restarting
                else "Запрос перезапуска выполнен (в тестовом окружении пропущен)."
            ),
        }
    )


@router.get("/api/system/settings/update/check")
async def check_update(request: Request, force: bool = Query(False), channel: Optional[str] = Query(None)):
    """Check for latest Sentinel Panel release on GitHub."""
    if not check_auth(request):
        return decoy_response()

    result = _check_github_release(force=force, channel=channel)
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
    resp = await asyncio.to_thread(_query_host_agent, {"action": "trigger_panel_update"}, 3.0)
    if isinstance(resp, dict) and resp.get("success"):
        applied = True
        details = resp.get("msg", "HostAgent принял команду на обновление.")

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
                        ["bash", p, "--auto"],
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
async def check_core_update(request: Request, force: bool = Query(False), channel: Optional[str] = Query(None)):
    """Check for latest Sentinel-Core engine releases on GitHub."""
    if not check_auth(request):
        return decoy_response()

    result = _check_core_release(force=force, channel=channel)
    return JSONResponse(content=result)


@router.get("/api/system/settings/update/core/progress")
async def get_core_update_progress(request: Request):
    """Returns real-time Sentinel-Core download and installation progress."""
    if not check_auth(request):
        return decoy_response()

    with _PROGRESS_LOCK:
        local_active = _CORE_DOWNLOAD_PROGRESS["active"]
        data = dict(_CORE_DOWNLOAD_PROGRESS)

    if not local_active:
        resp = _query_host_agent({"action": "get_core_progress"}, timeout=1.5)
        if isinstance(resp, dict) and resp.get("success") and resp.get("progress"):
            return JSONResponse(content=resp["progress"])

    return JSONResponse(content=data)


@router.post("/api/system/settings/update/core/apply")
async def apply_core_update(request: Request):
    """Update or reinstall Sentinel Core engine."""
    if not check_auth(request):
        return decoy_response()

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    target_tag = str(payload.get("version", "") or "").strip()
    force = bool(payload.get("force", False))
    active_channel = _normalize_update_channel(payload.get("channel")) if payload.get("channel") else _get_update_channel()

    logger.info(
        f"Initiating Sentinel Core installation (tag={target_tag or 'latest'}, force={force}, channel={active_channel})..."
    )
    bin_dir = _get_bin_dir()

    _set_core_progress(
        active=True,
        percent=0,
        downloaded_bytes=0,
        total_bytes=0,
        speed="0.0 KB/s",
        eta="--",
        stage=f"Подготовка к установке Sentinel-Core {target_tag or 'latest'}...",
        filename="",
        finished=False,
        success=False,
        error="",
    )

    applied = False
    details = ""
    installed_ver = ""

    # Method 1: HostAgent socket if available
    resp = await asyncio.to_thread(
        _query_host_agent,
        {
            "action": "trigger_core_update",
            "version": target_tag,
            "force": force,
            "channel": active_channel,
        },
        60.0,
    )
    if isinstance(resp, dict):
        if resp.get("success"):
            _, disk_ver = _detect_installed_core_version(bin_dir)
            expected_norm = _normalize_version_str(target_tag)
            disk_norm = _normalize_version_str(disk_ver)
            if expected_norm and disk_norm and disk_norm != expected_norm:
                logger.warning(
                    f"HostAgent reported success but disk core version is '{disk_ver}' instead of requested '{target_tag}'; falling back."
                )
            else:
                applied = True
                installed_ver = disk_ver or resp.get("version", target_tag)
                details = resp.get("msg", "HostAgent успешно выполнил установку ядра.")
        else:
            logger.warning(f"HostAgent core update reported: {resp.get('msg')}")

    # Method 2: Direct SentinelCoreManager download
    if not applied:
        _ensure_updater_path()
        try:
            from updater.core.sentinel_core import SentinelCoreManager

            mgr = SentinelCoreManager(
                bin_dir=bin_dir,
                auto_mode=True,
                force=force,
                progress_callback=_on_core_download_progress,
            )
            if not target_tag:
                stable_v, pre_v, latest_v = await asyncio.to_thread(mgr.fetch_releases)
                if active_channel == "beta":
                    target_tag = latest_v or pre_v or stable_v
                else:
                    target_tag = stable_v or (latest_v if not pre_v else "")

            if not target_tag:
                _set_core_progress(
                    active=False,
                    finished=True,
                    success=False,
                    error="Не удалось определить версию ядра для загрузки",
                )
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
            import inspect
            sig = inspect.signature(_standalone_download_core_sync)
            kwargs: Dict[str, Any] = {}
            if "progress_callback" in sig.parameters:
                kwargs["progress_callback"] = _on_core_download_progress
            if "channel" in sig.parameters:
                kwargs["channel"] = active_channel
            success, installed_ver, fallback_msg = await asyncio.to_thread(
                _standalone_download_core_sync, bin_dir, target_tag, force, **kwargs
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
    _CORE_CACHE["channel"] = None

    _set_core_progress(
        active=False,
        percent=100 if applied else 0,
        finished=True,
        success=applied,
        stage="Sentinel-Core успешно установлен!" if applied else "Ошибка установки",
        error="" if applied else details,
    )

    restarting = False
    if applied:
        try:
            from backend.runtime import schedule_panel_restart
            restarting = schedule_panel_restart(
                delay_seconds=1.2,
                reason=f"sentinel-core updated to {installed_ver or target_tag}",
            )
        except Exception as e:
            logger.warning(f"Failed to schedule panel restart after core update: {e}")

    loaded_ver = _get_loaded_core_version_safe()
    final_ver = installed_ver or target_tag
    restart_required = _is_restart_required(applied, final_ver, loaded_ver)

    return JSONResponse(
        content={
            "success": applied,
            "version": final_ver,
            "channel": active_channel,
            "loaded_version": loaded_ver,
            "restart_required": restart_required or restarting,
            "restarting": restarting,
            "msg": details,
        }
    )
