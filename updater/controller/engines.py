"""Sing-box & Xray-core Proxy Engine Manager for Sentinel Controller."""

from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from typing import Optional, Tuple

from ..core.common import (
    BOLD,
    CYAN,
    GREEN,
    RED,
    RESET,
    WHITE,
    YELLOW,
    log_banner,
    log_error,
    log_info,
    log_success,
    log_warn,
)
from ..core.downloader import Downloader


class ProxyEngineManager:
    """Manages version detection, downloading and updating Sing-box and Xray-core proxy engines."""

    def __init__(
        self,
        bin_dir: str,
        proxy_url: Optional[str] = None,
        auto_mode: bool = False,
    ) -> None:
        self.bin_dir = bin_dir
        self.proxy_url = proxy_url
        self.auto_mode = auto_mode
        self.downloader = Downloader(proxy_url=proxy_url)

        os.makedirs(self.bin_dir, exist_ok=True)

    def _get_platform_info(self) -> Tuple[str, str, str]:
        """Detects OS, Arch for singbox, and Arch for xray."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        os_name = "linux"
        if "darwin" in system:
            os_name = "darwin"
        elif "windows" in system:
            os_name = "windows"

        arch_singbox = "amd64"
        arch_xray = "64"

        if "aarch64" in machine or "arm64" in machine:
            arch_singbox = "arm64"
            arch_xray = "arm64-v8a"
        elif "armv7" in machine or "armhf" in machine:
            arch_singbox = "armv7"
            arch_xray = "arm32-v7a"
        elif "x86_64" in machine or "amd64" in machine:
            arch_singbox = "amd64"
            arch_xray = "64"

        return os_name, arch_singbox, arch_xray

    def get_installed_versions(self) -> Tuple[Optional[str], Optional[str]]:
        """Returns installed versions: (singbox_version, xray_version)."""
        sb_ver = None
        xray_ver = None

        # Sing-box
        sb_bin = os.path.join(self.bin_dir, "sing-box.exe" if platform.system() == "Windows" else "sing-box")
        if os.path.isfile(sb_bin):
            if platform.system() != "Windows":
                try:
                    os.chmod(sb_bin, 0o755)
                except Exception:
                    pass
            try:
                out = subprocess.check_output([sb_bin, "version"], stderr=subprocess.STDOUT, timeout=3).decode()
                m = re.search(r"sing-box version\s+([v\d\.\-]+)", out, re.IGNORECASE)
                if m:
                    sb_ver = m.group(1)
                else:
                    first_line = out.strip().split("\n")[0]
                    sb_ver = first_line.split()[2] if len(first_line.split()) > 2 else "установлен"
            except Exception:
                sb_ver = "установлен"

        # Xray-core
        xray_bin = os.path.join(self.bin_dir, "xray.exe" if platform.system() == "Windows" else "xray")
        if os.path.isfile(xray_bin):
            if platform.system() != "Windows":
                try:
                    os.chmod(xray_bin, 0o755)
                except Exception:
                    pass
            try:
                out = subprocess.check_output([xray_bin, "version"], stderr=subprocess.STDOUT, timeout=3).decode()
                m = re.search(r"Xray\s+([v\d\.\-]+)", out, re.IGNORECASE)
                if m:
                    xray_ver = m.group(1)
                else:
                    first_line = out.strip().split("\n")[0]
                    xray_ver = first_line.split()[1] if len(first_line.split()) > 1 else "установлен"
            except Exception:
                xray_ver = "установлен"

        return sb_ver, xray_ver

    def fetch_latest_release(self, repo: str) -> Optional[str]:
        """Queries GitHub API to find the latest release tag for a repository."""
        data = self.downloader.fetch_github_api(f"https://api.github.com/repos/{repo}/releases/latest")
        if isinstance(data, dict):
            tag = data.get("tag_name")
            if tag:
                return tag
        return None

    def download_singbox(self, tag: Optional[str] = None) -> bool:
        """Downloads and installs Sing-box binary into target bin directory."""
        if not tag:
            tag = self.fetch_latest_release("SagerNet/sing-box")
            if not tag:
                tag = "v1.13.20"

        if not tag.startswith("v") and not tag.startswith("V"):
            tag = "v" + tag

        clean_ver = tag.lstrip("v")
        os_name, arch_sb, _ = self._get_platform_info()

        log_info(f"Загрузка Sing-box {BOLD}{tag}{RESET} для {os_name}/{arch_sb}...")

        if os_name == "windows":
            filename = f"sing-box-{clean_ver}-windows-{arch_sb}.zip"
        elif os_name == "darwin":
            filename = f"sing-box-{clean_ver}-darwin-{arch_sb}.tar.gz"
        else:
            filename = f"sing-box-{clean_ver}-linux-{arch_sb}.tar.gz"

        direct_url = f"https://github.com/SagerNet/sing-box/releases/download/{tag}/{filename}"
        data = self.downloader.download_bytes_with_mirrors(direct_url, label_for_log=filename)
        if not data:
            log_error(f"Не удалось загрузить архив Sing-box {filename}")
            return False

        target_bin = os.path.join(self.bin_dir, "sing-box.exe" if os_name == "windows" else "sing-box")
        tmp_target = f"{target_bin}.tmp.{os.getpid()}"

        try:
            if filename.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for member in zf.namelist():
                        if member.endswith("sing-box") or member.endswith("sing-box.exe"):
                            with zf.open(member) as src, open(tmp_target, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            break
            else:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
                    for member in tf.getmembers():
                        if member.name.endswith("sing-box") or member.name.endswith("sing-box.exe"):
                            f = tf.extractfile(member)
                            if f:
                                with open(tmp_target, "wb") as dst:
                                    shutil.copyfileobj(f, dst)
                                break

            if os.path.isfile(tmp_target) and os.path.getsize(tmp_target) > 0:
                if os_name != "windows":
                    try:
                        os.chmod(tmp_target, 0o755)
                    except Exception:
                        pass
                if os.path.exists(target_bin):
                    try:
                        os.remove(target_bin)
                    except Exception:
                        pass
                os.replace(tmp_target, target_bin)
                log_success(f"Sing-box {tag} установлен -> {target_bin}")
                return True
        except Exception as e:
            if os.path.exists(tmp_target):
                try:
                    os.remove(tmp_target)
                except Exception:
                    pass
            log_error(f"Ошибка распаковки Sing-box: {e}")
            return False

        return False

    def download_xray(self, tag: Optional[str] = None) -> bool:
        """Downloads and installs Xray-core binary into target bin directory."""
        if not tag:
            tag = self.fetch_latest_release("XTLS/Xray-core")
            if not tag:
                tag = "v26.3.27"

        if not tag.startswith("v") and not tag.startswith("V"):
            tag = "v" + tag

        os_name, _, arch_xray = self._get_platform_info()
        log_info(f"Загрузка Xray-core {BOLD}{tag}{RESET} для {os_name}/{arch_xray}...")

        if os_name == "windows":
            filename = f"Xray-windows-{arch_xray}.zip"
        elif os_name == "darwin":
            filename = f"Xray-macos-{arch_xray}.zip"
        else:
            filename = f"Xray-linux-{arch_xray}.zip"

        direct_url = f"https://github.com/XTLS/Xray-core/releases/download/{tag}/{filename}"
        data = self.downloader.download_bytes_with_mirrors(direct_url, label_for_log=filename)
        if not data:
            log_error(f"Не удалось загрузить архив Xray-core {filename}")
            return False

        target_bin = os.path.join(self.bin_dir, "xray.exe" if os_name == "windows" else "xray")

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for member in zf.namelist():
                    base = os.path.basename(member)
                    if base in ["xray", "xray.exe", "geoip.dat", "geosite.dat"]:
                        target_file = os.path.join(self.bin_dir, base)
                        tmp_file = f"{target_file}.tmp.{os.getpid()}"
                        with zf.open(member) as src, open(tmp_file, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        if base in ["xray", "xray.exe"] and os_name != "windows":
                            try:
                                os.chmod(tmp_file, 0o755)
                            except Exception:
                                pass
                        if os.path.exists(target_file):
                            try:
                                os.remove(target_file)
                            except Exception:
                                pass
                        os.replace(tmp_file, target_file)

            if os.path.isfile(target_bin) and os.path.getsize(target_bin) > 0:
                log_success(f"Xray-core {tag} установлен -> {target_bin}")
                return True
        except Exception as e:
            log_error(f"Ошибка распаковки Xray-core: {e}")
            return False

        return False

    def manage_engines(self) -> None:
        """Interactive or automated menu for managing Sing-box and Xray-core proxy engines."""
        sb_cur, xray_cur = self.get_installed_versions()

        if not sys.stdin.isatty() or self.auto_mode:
            if not sb_cur:
                log_info("Sing-box не обнаружен. Автоматическая загрузка...")
                self.download_singbox()
            return

        sb_latest = self.fetch_latest_release("SagerNet/sing-box")
        xray_latest = self.fetch_latest_release("XTLS/Xray-core")

        log_banner("🚀 PROXY / VPN ДВИЖКИ", "Установка и обновление Sing-box / Xray-core")
        sb_disp = f"{GREEN}{sb_cur}{RESET}" if sb_cur else f"{RED}Не установлен{RESET}"
        xray_disp = f"{GREEN}{xray_cur}{RESET}" if xray_cur else f"{RED}Не установлен{RESET}"

        print(f"  • Sing-box:  {sb_disp} (GitHub: {CYAN}{sb_latest or '—'}{RESET})")
        print(f"  • Xray-core: {xray_disp} (GitHub: {CYAN}{xray_latest or '—'}{RESET})\n")

        is_sb_installed = bool(sb_cur)
        default_choice = "4" if is_sb_installed else "1"

        if not is_sb_installed:
            print(f"  {CYAN}1){RESET} 🟢 Установить Sing-box [Рекомендуется / По умолчанию]")
            print(f"  {CYAN}2){RESET} 🟢 Установить Xray-core")
            print(f"  {CYAN}3){RESET} 🌐 Установить оба движка (Sing-box + Xray-core)")
            print(f"  {CYAN}4){RESET} ⏹️  Пропустить установку движков\n")
        else:
            print(f"  {CYAN}1){RESET} 🔄 Обновить / переустановить Sing-box")
            print(f"  {CYAN}2){RESET} 🔄 Обновить / переустановить Xray-core")
            print(f"  {CYAN}3){RESET} 🌐 Обновить оба движка")
            print(f"  {CYAN}4){RESET} ⏹️  Оставить текущие версии [По умолчанию / Пропустить]\n")

        while True:
            try:
                raw = input(f"  {BOLD}Выберите вариант [1-4]{RESET} (по умолчанию {default_choice}): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("")
                raw = default_choice
            choice = re.sub(r"[^1-4]", "", raw) or default_choice

            if choice == "1":
                self.download_singbox(sb_latest)
                break
            elif choice == "2":
                self.download_xray(xray_latest)
                break
            elif choice == "3":
                self.download_singbox(sb_latest)
                self.download_xray(xray_latest)
                break
            elif choice == "4":
                log_info("Обновление прокси-движков пропущено.")
                break
