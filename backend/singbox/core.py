import os
import sys
import time
import logging
import zipfile
import tarfile
import shutil
import subprocess
import requests
import platform
from pathlib import Path
from backend.config import BIN_DIR, SINGBOX_BIN_PATH, SINGBOX_BIN_NAME, IS_WINDOWS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_installed_singbox_version() -> str:
    """Возвращает версию локально установленного ядра sing-box через sentinel-core"""
    if not SINGBOX_BIN_PATH.exists():
        return "Not installed"
    try:
        from backend.sentinel_core_bridge import get_core_version
        v = get_core_version("sing-box", str(SINGBOX_BIN_PATH))
        if v and v != "Unknown":
            return v
    except Exception as e:
        logging.error(f"Error getting installed sing-box version via sentinel-core: {e}")
    return "Unknown"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SentinelPanel/1.0"}

import xml.etree.ElementTree as ET

_SINGBOX_RELEASES_CACHE = {}
CACHE_TTL = 3600  # 1 hour cache for releases

def _fetch_singbox_releases_atom(include_prerelease: bool = False, limit: int = 20) -> list[dict]:
    try:
        url = "https://github.com/SagerNet/sing-box/releases.atom"
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code != 200:
            return []
        raw_content = getattr(resp, "content", None)
        if raw_content is None:
            raw_content = getattr(resp, "text", "").encode("utf-8")
        if not raw_content:
            return []
        root = ET.fromstring(raw_content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        arch = platform.machine().lower()
        is_arm = "arm64" in arch or "aarch64" in arch
        releases = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            title_text = title.text.strip() if title is not None and title.text else ""
            tag = title_text.split()[-1] if title_text else ""
            if not tag:
                continue
            if not tag.startswith("v"):
                tag = "v" + tag
            v_clean = tag.lstrip("v")
            is_pre = any(k in tag.lower() for k in ("beta", "alpha", "rc", "pre"))
            if not include_prerelease and is_pre:
                continue
            if IS_WINDOWS:
                target_name = f"sing-box-{v_clean}-windows-arm64.zip" if is_arm else f"sing-box-{v_clean}-windows-amd64.zip"
            else:
                target_name = f"sing-box-{v_clean}-linux-arm64.tar.gz" if is_arm else f"sing-box-{v_clean}-linux-amd64.tar.gz"
            download_url = f"https://github.com/SagerNet/sing-box/releases/download/{tag}/{target_name}"
            releases.append({
                "version": tag,
                "download_url": download_url,
                "is_prerelease": is_pre
            })
            if len(releases) >= limit:
                break
        return releases
    except Exception as e:
        logging.error(f"Failed to fetch sing-box releases atom feed: {e}")
        return []

def get_singbox_releases(include_prerelease: bool = False, limit: int = 20) -> list[dict]:
    """Получает список всех доступных релизов sing-box с GitHub с кэшированием в памяти"""
    cache_key = f"releases_{include_prerelease}_{limit}"
    now = time.time()

    # Сначала проверяем горячий кэш
    if cache_key in _SINGBOX_RELEASES_CACHE:
        ts, cached = _SINGBOX_RELEASES_CACHE[cache_key]
        if now - ts < CACHE_TTL and cached:
            return cached

    url = "https://api.github.com/repos/SagerNet/sing-box/releases"
    releases = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=6)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                arch = platform.machine().lower()
                is_arm = "arm64" in arch or "aarch64" in arch
                os_str = "windows" if IS_WINDOWS else "linux"
                arch_str = "arm64" if is_arm else "amd64"

                for item in data:
                    is_pre = bool(item.get("prerelease", False))
                    if not include_prerelease and is_pre:
                        continue
                    tag_name = item.get("tag_name")
                    download_url = None
                    for asset in item.get("assets", []):
                        name = asset.get("name", "").lower()
                        if os_str in name and arch_str in name and (name.endswith(".zip") or name.endswith(".tar.gz")):
                            download_url = asset.get("browser_download_url")
                            break
                    if not download_url and item.get("assets"):
                        download_url = item["assets"][0].get("browser_download_url")
                    if tag_name and download_url:
                        releases.append({
                            "version": tag_name,
                            "download_url": download_url,
                            "is_prerelease": is_pre
                        })
                    if len(releases) >= limit:
                        break
    except Exception as e:
        logging.error(f"Failed to fetch sing-box releases list from GitHub API: {e}")

    if releases:
        _SINGBOX_RELEASES_CACHE[cache_key] = (now, releases)
        return releases

    # Резервный опрос через Atom feed
    releases = _fetch_singbox_releases_atom(include_prerelease=include_prerelease, limit=limit)
    if releases:
        _SINGBOX_RELEASES_CACHE[cache_key] = (now, releases)
        return releases

    # Если опрос не удался, но есть устаревший кэш — отдаем его
    if cache_key in _SINGBOX_RELEASES_CACHE:
        return _SINGBOX_RELEASES_CACHE[cache_key][1]

    return []

def get_latest_singbox_version_info(include_prerelease: bool = False):
    """Получает информацию о последнем релизе sing-box из кэша релизов"""
    releases = get_singbox_releases(include_prerelease=include_prerelease, limit=5)
    if releases and len(releases) > 0:
        return releases[0]
    return None

def download_singbox_core(download_url: str = None):
    """Скачивает и распаковывает ядро sing-box"""
    if not download_url:
        info = get_latest_singbox_version_info()
        if not info or not info["download_url"]:
            raise Exception("Could not find sing-box download URL automatically.")
        download_url = info["download_url"]
        version = info["version"]
    else:
        from urllib.parse import urlparse, unquote
        try:
            parsed = urlparse(download_url)
            path_lower = unquote(parsed.path).lower()
            is_safe = (
                parsed.scheme == "https"
                and parsed.netloc.lower() == "github.com"
                and path_lower.startswith("/sagernet/sing-box/releases/download/")
            )
        except Exception:
            is_safe = False

        if not is_safe:
            raise ValueError("Недопустимый URL для скачивания. Разрешены только официальные релизы sing-box на GitHub.")

        version = "custom"

    is_tar = download_url.endswith(".tar.gz") or download_url.endswith(".tgz")
    archive_path = BIN_DIR / ("singbox_temp.tar.gz" if is_tar else "singbox_temp.zip")
    temp_extract_dir = BIN_DIR / "singbox_temp_extract"

    logging.info(f"Downloading sing-box from {download_url}...")
    try:
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logging.info("Extracting sing-box archive to temporary directory...")
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)
        temp_extract_dir.mkdir(parents=True, exist_ok=True)

        if is_tar:
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                tar_ref.extractall(temp_extract_dir)
        else:
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(temp_extract_dir)

        # Находим исполняемый файл sing-box в распакованной структуре
        extracted_bin = None
        target_name = "sing-box.exe" if IS_WINDOWS else "sing-box"
        for root, dirs, files in os.walk(temp_extract_dir):
            for file in files:
                if file.lower() == target_name.lower():
                    extracted_bin = Path(root) / file
                    break
            if extracted_bin:
                break

        if not extracted_bin or not extracted_bin.exists():
            raise Exception(f"Executable '{target_name}' not found in the downloaded archive.")

        if not IS_WINDOWS:
            try:
                os.chmod(extracted_bin, 0o755)
            except Exception as e:
                logging.error(f"Failed to set chmod +x on temporary sing-box binary: {e}")

        # Проверяем работоспособность самотестированием
        try:
            cmd = [str(extracted_bin), "version"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)
            if result.returncode != 0:
                err_msg = result.stderr.strip() or result.stdout.strip()
                raise Exception(f"Self-test returned non-zero code {result.returncode}: {err_msg}")
        except Exception as e:
            raise Exception(f"Downloaded sing-box binary failed self-test verification: {str(e)}")

        # Заменяем рабочий исполняемый файл
        if SINGBOX_BIN_PATH.exists():
            try:
                os.remove(SINGBOX_BIN_PATH)
            except Exception as e:
                logging.warning(f"Could not remove old sing-box binary: {e}")

        shutil.move(str(extracted_bin), str(SINGBOX_BIN_PATH))

        if not IS_WINDOWS:
            try:
                os.chmod(SINGBOX_BIN_PATH, 0o755)
            except Exception:
                pass

        logging.info("Sing-box core successfully verified and installed.")
    finally:
        if archive_path.exists():
            try:
                os.remove(archive_path)
            except Exception:
                pass
        if temp_extract_dir.exists():
            try:
                shutil.rmtree(temp_extract_dir)
            except Exception:
                pass

    return version

def ensure_singbox_installed() -> bool:
    """Проверяет наличие sing-box и при необходимости скачивает дефолтное ядро"""
    if SINGBOX_BIN_PATH.exists():
        return True
    try:
        logging.info("Sing-box binary not found. Installing latest release...")
        download_singbox_core()
        return True
    except Exception as e:
        logging.error(f"Failed to ensure sing-box installation: {e}")
        return False
