import os
import time
import logging
import zipfile
import shutil
import subprocess
import requests
import platform
import backend.xray

# Дефолтные URL для geo-файлов (официальный репозиторий Loyalsoldier)
DEFAULT_GEOIP_URL = "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
DEFAULT_GEOSITE_URL = "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SentinelPanel/1.0"}
import xml.etree.ElementTree as ET

_XRAY_RELEASES_CACHE = {}
CACHE_TTL = 3600  # 1 hour cache for releases

def _fetch_xray_releases_atom(include_prerelease: bool = False, limit: int = 20) -> list[dict]:
    try:
        url = "https://github.com/XTLS/Xray-core/releases.atom"
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
            if backend.xray.IS_WINDOWS:
                target_name = f"Xray-windows-arm64-v8a.zip" if is_arm else f"Xray-windows-64.zip"
            else:
                target_name = f"Xray-linux-arm64-v8a.zip" if is_arm else f"Xray-linux-64.zip"
            download_url = f"https://github.com/XTLS/Xray-core/releases/download/{tag}/{target_name}"
            releases.append({
                "version": tag,
                "download_url": download_url,
                "is_prerelease": is_pre
            })
            if len(releases) >= limit:
                break
        return releases
    except Exception as e:
        logging.error(f"Failed to fetch Xray releases atom feed: {e}")
        return []

def get_xray_releases(include_prerelease: bool = False, limit: int = 20) -> list[dict]:
    """Получает список всех доступных релизов Xray с GitHub с кэшированием в памяти"""
    cache_key = f"releases_{include_prerelease}_{limit}"
    now = time.time()

    # Сначала проверяем горячий кэш
    if cache_key in _XRAY_RELEASES_CACHE:
        ts, cached = _XRAY_RELEASES_CACHE[cache_key]
        if now - ts < CACHE_TTL and cached:
            return cached

    url = "https://api.github.com/repos/XTLS/Xray-core/releases"
    releases = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=6)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                arch = platform.machine().lower()
                is_arm = "arm64" in arch or "aarch64" in arch
                if backend.xray.IS_WINDOWS:
                    target_name = "Xray-windows-arm64-v8a.zip" if is_arm else "Xray-windows-64.zip"
                else:
                    target_name = "Xray-linux-arm64-v8a.zip" if is_arm else "Xray-linux-64.zip"

                for item in data:
                    is_pre = bool(item.get("prerelease", False))
                    if not include_prerelease and is_pre:
                        continue
                    tag_name = item.get("tag_name")
                    download_url = None
                    for asset in item.get("assets", []):
                        if asset.get("name") == target_name:
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
        logging.error(f"Failed to fetch Xray releases list from GitHub API: {e}")

    if releases:
        _XRAY_RELEASES_CACHE[cache_key] = (now, releases)
        return releases

    # Резервный опрос через Atom feed
    releases = _fetch_xray_releases_atom(include_prerelease=include_prerelease, limit=limit)
    if releases:
        _XRAY_RELEASES_CACHE[cache_key] = (now, releases)
        return releases

    # Если опрос не удался, но есть устаревший кэш — отдаем его
    if cache_key in _XRAY_RELEASES_CACHE:
        return _XRAY_RELEASES_CACHE[cache_key][1]

    return []

def get_latest_xray_version_info(include_prerelease: bool = False):
    """Получает информацию о последнем релизе Xray-core из кэша релизов"""
    releases = get_xray_releases(include_prerelease=include_prerelease, limit=5)
    if releases and len(releases) > 0:
        return releases[0]
    return None

def download_xray_core(download_url: str = None):
    """Скачивает и распаковывает ядро Xray"""
    if not download_url:
        info = backend.xray.get_latest_xray_version_info()
        if not info or not info["download_url"]:
            raise Exception("Could not find Xray download URL automatically.")
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
                and path_lower.startswith("/xtls/xray-core/releases/download/")
            )
        except Exception:
            is_safe = False
            
        if not is_safe:
            raise ValueError("Недопустимый URL для скачивания. Разрешены только официальные релизы Xray-core на GitHub.")
            
        version = "custom"

    zip_path = backend.xray.BIN_DIR / "xray_temp.zip"
    temp_extract_dir = backend.xray.BIN_DIR / "xray_temp_extract"
    
    logging.info(f"Downloading Xray from {download_url}...")
    try:
        response = requests.get(download_url, stream=True, timeout=30)
        response.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        logging.info("Extracting Xray archive to temporary directory...")
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)
        temp_extract_dir.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_extract_dir)
            
        temp_xray_bin_path = temp_extract_dir / backend.xray.XRAY_BIN_NAME
        if not temp_xray_bin_path.exists():
            raise Exception(f"Xray binary '{backend.xray.XRAY_BIN_NAME}' not found in the downloaded archive.")
            
        if not backend.xray.IS_WINDOWS:
            try:
                os.chmod(temp_xray_bin_path, 0o755)  # nosec B103
                logging.info("Chmod +x set on temporary Xray binary.")
            except Exception as e:
                logging.error(f"Failed to set executable permission on temporary Linux binary: {e}")
                
        # Проверяем работоспособность временного бинарника
        try:
            cmd = [str(temp_xray_bin_path), "version"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)  # nosec B603
            if result.returncode != 0:
                err_msg = result.stderr.strip() or result.stdout.strip()
                raise Exception(f"Self-test returned non-zero code {result.returncode}: {err_msg}")
        except Exception as e:
            raise Exception(f"Downloaded Xray binary failed self-test verification: {str(e)}")
            
        # Ensure core process is stopped so Windows file lock is released
        try:
            from backend.xray.service import stop_xray
            stop_xray()
            time.sleep(0.5)
        except Exception:
            pass

        # Копируем/переносим файлы в рабочую папку BIN_DIR
        for item in temp_extract_dir.iterdir():
            dest = backend.xray.BIN_DIR / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.move(str(item), str(dest))
            else:
                if dest.exists():
                    for _ in range(5):
                        try:
                            os.remove(dest)
                            break
                        except Exception as e:
                            time.sleep(0.3)
                shutil.move(str(item), str(dest))
                
        if not backend.xray.IS_WINDOWS:
            try:
                os.chmod(backend.xray.XRAY_BIN_PATH, 0o755)  # nosec B103
            except Exception:
                pass
                
        logging.info("Xray core successfully verified and installed.")
    finally:
        if zip_path.exists():
            try:
                os.remove(zip_path)
            except Exception:
                pass
        if temp_extract_dir.exists():
            try:
                shutil.rmtree(temp_extract_dir)
            except Exception:
                pass
                
    return version


def download_geo_files(geoip_url: str = None, geosite_url: str = None) -> dict:
    """
    Скачивает geoip.dat и geosite.dat по указанным URL.
    Если URL не указаны, берёт сохранённые в БД или использует дефолтные.
    Возвращает словарь: {'geoip': True/False, 'geosite': True/False, 'errors': [...]}
    """
    from backend.database import get_setting

    if not geoip_url:
        geoip_url = get_setting("geo_geoip_url", "") or DEFAULT_GEOIP_URL
    if not geosite_url:
        geosite_url = get_setting("geo_geosite_url", "") or DEFAULT_GEOSITE_URL

    result = {"geoip": False, "geosite": False, "errors": []}

    def _safe_download(url: str, dest_name: str) -> bool:
        """Скачивает один файл по URL и сохраняет его в BIN_DIR."""
        try:
            # Проверяем URL — должен быть https и заканчиваться на .dat
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http"):
                raise ValueError(f"Недопустимая схема URL: {parsed.scheme}. Используйте https://")
            if not url.lower().endswith(".dat"):
                raise ValueError(f"URL должен указывать на .dat файл")

            dest_path = backend.xray.BIN_DIR / dest_name
            tmp_path = backend.xray.BIN_DIR / f"{dest_name}.tmp"

            logging.info(f"Скачивание {dest_name} из {url}...")
            response = requests.get(url, stream=True, timeout=60, allow_redirects=True)
            response.raise_for_status()

            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Проверяем что файл не пустой
            if tmp_path.stat().st_size < 1024:
                raise ValueError(f"Скачанный файл слишком мал ({tmp_path.stat().st_size} байт) — возможно, неверный URL")

            # Атомарная замена
            if dest_path.exists():
                os.remove(dest_path)
            shutil.move(str(tmp_path), str(dest_path))
            logging.info(f"{dest_name} успешно обновлён ({dest_path.stat().st_size} байт)")
            return True
        except Exception as e:
            logging.error(f"Ошибка при скачивании {dest_name}: {e}")
            result["errors"].append(f"{dest_name}: {str(e)}")
            # Удаляем временный файл если остался
            tmp_path = backend.xray.BIN_DIR / f"{dest_name}.tmp"
            if tmp_path.exists():
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    result["geoip"] = _safe_download(geoip_url, "geoip.dat")
    result["geosite"] = _safe_download(geosite_url, "geosite.dat")
    return result


def get_geo_files_info() -> dict:
    """
    Возвращает метаданные установленных geo-файлов (размер, дата обновления).
    """
    from backend.database import get_setting
    info = {}
    for name in ("geoip.dat", "geosite.dat"):
        path = backend.xray.BIN_DIR / name
        if path.exists():
            stat = path.stat()
            info[name] = {
                "exists": True,
                "size_kb": round(stat.st_size / 1024, 1),
                "updated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(stat.st_mtime))
            }
        else:
            info[name] = {"exists": False, "size_kb": 0, "updated_at": None}

    info["geoip_url"] = get_setting("geo_geoip_url", "") or DEFAULT_GEOIP_URL
    info["geosite_url"] = get_setting("geo_geosite_url", "") or DEFAULT_GEOSITE_URL
    return info

def ensure_xray_installed():
    """Проверяет наличие Xray, скачивает при необходимости"""
    need_install = False
    if not backend.xray.XRAY_BIN_PATH.exists():
        need_install = True
    else:
        try:
            cmd = [str(backend.xray.XRAY_BIN_PATH), "version"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            if result.returncode != 0:
                need_install = True
        except Exception:
            need_install = True
            
    if need_install:
        logging.info("Xray core not found or not working (wrong architecture?). Installing/Updating...")
        try:
            backend.xray.download_xray_core()
        except Exception as e:
            logging.error(f"Error during Xray core installation: {e}")

def get_installed_xray_version() -> str:
    """Gets the currently installed version dynamically via sentinel-core."""
    if not backend.xray.XRAY_BIN_PATH.exists():
        return "Not Installed"
    try:
        from backend.sentinel_core_bridge import get_core_version
        v = get_core_version("xray", str(backend.xray.XRAY_BIN_PATH))
        if v and v != "Unknown":
            return v
    except Exception as e:
        logging.error(f"Failed to check Xray version via sentinel-core: {e}")
    return "Unknown"
