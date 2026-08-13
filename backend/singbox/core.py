import os
import sys
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
    """Возвращает версию локально установленного ядра sing-box"""
    if not SINGBOX_BIN_PATH.exists():
        return "Not installed"
    try:
        cmd = [str(SINGBOX_BIN_PATH), "version"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            for line in lines:
                if "sing-box version" in line.lower() or "version" in line.lower():
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2]
                    return parts[-1]
            if lines:
                return lines[0].split()[-1]
    except Exception as e:
        logging.error(f"Error getting installed sing-box version: {e}")
    return "Unknown"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SentinelPanel/1.0"}

def get_latest_singbox_version_info(include_prerelease: bool = False):
    """Получает информацию о последнем релизе sing-box с GitHub (SagerNet/sing-box)"""
    if include_prerelease:
        url = "https://api.github.com/repos/SagerNet/sing-box/releases"
    else:
        url = "https://api.github.com/repos/SagerNet/sing-box/releases/latest"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            if include_prerelease and isinstance(res_data, list):
                if not res_data:
                    return None
                data = res_data[0]
            elif isinstance(res_data, dict):
                data = res_data
            else:
                return None

            tag_name = data.get("tag_name")
            if tag_name and tag_name.startswith("v"):
                version_num = tag_name[1:]
            else:
                version_num = tag_name

            is_prerelease = bool(data.get("prerelease", False))
            assets = data.get("assets", [])

            arch = platform.machine().lower()
            is_arm = "arm64" in arch or "aarch64" in arch

            if IS_WINDOWS:
                os_str = "windows"
            else:
                os_str = "linux"

            arch_str = "arm64" if is_arm else "amd64"

            download_url = None
            for asset in assets:
                name = asset.get("name", "").lower()
                if os_str in name and arch_str in name and (name.endswith(".zip") or name.endswith(".tar.gz")):
                    download_url = asset.get("browser_download_url")
                    break

            return {
                "version": tag_name,
                "download_url": download_url,
                "is_prerelease": is_prerelease
            }
    except Exception as e:
        logging.error(f"Failed to fetch sing-box version info from GitHub: {e}")
    return None

def get_singbox_releases(include_prerelease: bool = False, limit: int = 20) -> list[dict]:
    """Получает список всех доступных релизов sing-box с GitHub"""
    url = "https://api.github.com/repos/SagerNet/sing-box/releases"
    releases = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
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
                    if tag_name and download_url:
                        releases.append({
                            "version": tag_name,
                            "download_url": download_url,
                            "is_prerelease": is_pre
                        })
                    if len(releases) >= limit:
                        break
    except Exception as e:
        logging.error(f"Failed to fetch sing-box releases list from GitHub: {e}")
    return releases

def download_singbox_core(download_url: str = None):
    """Скачивает и распаковывает ядро sing-box"""
    if not download_url:
        info = get_latest_singbox_version_info()
        if not info or not info["download_url"]:
            raise Exception("Could not find sing-box download URL automatically.")
        download_url = info["download_url"]
        version = info["version"]
    else:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(download_url)
            is_safe = (
                parsed.scheme == "https"
                and parsed.netloc.lower() == "github.com"
                and (
                    parsed.path.startswith("/SagerNet/sing-box/releases/download/")
                    or parsed.path.startswith("/sagernet/sing-box/releases/download/")
                )
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
