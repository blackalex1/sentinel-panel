"""Sentinel-Core Binary, Shared Library and Header Manager."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from typing import Dict, Optional, Tuple

from .common import (
    BOLD,
    CYAN,
    DARK_GRAY,
    DIM,
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
from .downloader import Downloader


class SentinelCoreManager:
    """Manages Sentinel-Core GitHub releases, binary/library downloading, and digest verification."""

    REPO = "blackalex1/sentinel-core"

    def __init__(
        self,
        bin_dir: str,
        proxy_url: Optional[str] = None,
        auto_mode: bool = False,
        force: bool = False,
    ) -> None:
        self.bin_dir = bin_dir
        self.proxy_url = proxy_url
        self.auto_mode = auto_mode
        self.force = force
        self.downloader = Downloader(proxy_url=proxy_url)

        os.makedirs(self.bin_dir, exist_ok=True)

    def _get_platform_info(self) -> Tuple[str, str, str]:
        """Detects OS, Arch, and dynamic library extension."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        os_name = "linux"
        if "darwin" in system:
            os_name = "darwin"
        elif "windows" in system:
            os_name = "windows"

        arch = "amd64"
        if "aarch64" in machine or "arm64" in machine:
            arch = "arm64"
        elif "arm" in machine:
            arch = "armv7"
        elif "x86_64" in machine or "amd64" in machine:
            arch = "amd64"

        ext = ".so"
        if os_name == "windows":
            ext = ".dll"
        elif os_name == "darwin":
            ext = ".dylib"

        return os_name, arch, ext

    def get_installed_version(self) -> Tuple[bool, str]:
        """Detects currently installed core version via C-shared library ctypes FFI or binary CLI."""
        _, _, ext = self._get_platform_info()
        so_path = os.path.join(self.bin_dir, f"libsentinel-core{ext}")
        if not os.path.isfile(so_path):
            so_path = os.path.join(self.bin_dir, "libsentinel-core.so")

        if os.path.isfile(so_path):
            try:
                ffi_cmd = [
                    sys.executable, "-c",
                    f'import ctypes, re; lib = ctypes.CDLL("{so_path}"); lib.SentinelGetEngineVersion.restype = ctypes.c_char_p; v = lib.SentinelGetEngineVersion().decode("utf-8").strip(); print("v" + v if re.match(r"^\\d+\\.\\d+", v) else v)'
                ]
                v_out = subprocess.check_output(ffi_cmd, stderr=subprocess.DEVNULL, timeout=2).decode().strip()
                if v_out and v_out != "dev":
                    return True, v_out
            except Exception:
                pass

        exe_path = os.path.join(self.bin_dir, "sentinel-core")
        if platform.system() == "Windows":
            exe_path += ".exe"

        if os.path.isfile(exe_path):
            if platform.system() != "Windows":
                try:
                    os.chmod(exe_path, 0o755)
                except Exception:
                    pass
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

        if os.path.isfile(so_path):
            return True, "Установлена (.so найдена)"

        return False, "Не установлена"


    def fetch_releases(self) -> Tuple[str, str, str]:
        """Queries GitHub API (via proxy or mirrors) and returns (stable_ver, prerelease_ver, latest_any)."""
        log_info(f"Опрос GitHub Releases для {BOLD}{self.REPO}{RESET}...")

        data = self.downloader.fetch_github_api(f"https://api.github.com/repos/{self.REPO}/releases", timeout=5.0)
        if isinstance(data, list) and len(data) > 0:
            stable = next((r["tag_name"] for r in data if not r.get("prerelease")), "")
            prerelease = data[0]["tag_name"] if data[0].get("prerelease") else ""
            latest_any = data[0]["tag_name"]
            return stable, prerelease, latest_any

        # Fallback to git ls-remote
        if shutil.which("git"):
            remotes = [
                f"https://github.com/{self.REPO}.git",
                f"https://ghfast.top/https://github.com/{self.REPO}.git",
                f"https://gh-proxy.com/https://github.com/{self.REPO}.git",
            ]
            for remote in remotes:
                try:
                    cmd = ["git", "-c", "http.connectTimeout=4", "-c", "http.timeout=8", "ls-remote", "--tags", remote]
                    env = os.environ.copy()
                    if self.proxy_url:
                        env["http_proxy"] = self.proxy_url
                        env["https_proxy"] = self.proxy_url
                        env["all_proxy"] = self.proxy_url
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=8.0, env=env)
                    if res.returncode == 0 and res.stdout.strip():
                        tags = []
                        for line in res.stdout.splitlines():
                            parts = line.strip().split()
                            if len(parts) == 2 and "refs/tags/" in parts[1]:
                                raw_t = parts[1].split("refs/tags/")[1]
                                if not raw_t.endswith("^{}"):
                                    tags.append(raw_t)
                        if tags:
                            def _ver_key(v: str):
                                nums = [int(x) for x in re.findall(r"\d+", v)]
                                return nums or [0]
                            tags.sort(key=_ver_key, reverse=True)
                            stable = next((t for t in tags if not any(x in t.lower() for x in ["beta", "alpha", "rc", "dev", "pre"])), "")
                            prerelease = next((t for t in tags if any(x in t.lower() for x in ["beta", "alpha", "rc", "dev", "pre"])), "")
                            latest_any = tags[0]
                            return stable, prerelease, latest_any
                except Exception:
                    continue

        return "", "", ""

    def select_version(self) -> Optional[str]:
        """Interactive or automated version selector."""
        is_installed, current_ver = self.get_installed_version()
        stable_ver, prerelease_ver, latest_any = self.fetch_releases()

        current_tag_match = re.search(r"v\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?", current_ver)
        current_tag = current_tag_match.group(0) if current_tag_match else ""

        if not sys.stdin.isatty() or self.auto_mode:
            target = stable_ver or prerelease_ver or latest_any
            if not target:
                log_warn("Не удалось автоматически определить версию ядра с GitHub. Пропуск...")
                return None
            if not self.force and is_installed and current_tag and target == current_tag:
                log_info(f"Ядро Sentinel-Core ({current_ver}) уже актуально ({target}).")
                return None
            return target

        log_banner("📦 ВЫБОР ВЕРСИИ SENTINEL-CORE", "Загрузка бинарников и динамических библиотек")
        print(f"  📌 Текущая версия:              {BOLD}{current_ver}{RESET}")
        print(f"  🟢 Последняя стабильная (Stable): {GREEN}{stable_ver or 'Не определена'}{RESET}")
        print(f"  🟡 Пре-релиз / Бета (Pre-release): {YELLOW}{prerelease_ver or 'Отсутствует'}{RESET}\n")

        is_up_to_date = bool(is_installed and stable_ver and current_tag == stable_ver)

        if prerelease_ver and stable_ver:
            default_choice = "3" if is_up_to_date else "1"
            print(f"  {CYAN}1){RESET} 🟢 Установить стабильную версию ({stable_ver})")
            print(f"  {CYAN}2){RESET} 🟡 Установить пре-релиз / бету ({prerelease_ver})")
            print(f"  {CYAN}3){RESET} ⏹️  Оставить текущую версию (пропустить)")
            print(f"  {CYAN}4){RESET} ✏️  Ввести тег/версию вручную\n")

            while True:
                try:
                    raw = input(f"  {BOLD}Выберите вариант [1-4]{RESET} (по умолчанию {default_choice}): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("")
                    raw = default_choice
                choice = re.sub(r"[^1-4]", "", raw) or default_choice
                if choice == "1":
                    return stable_ver
                elif choice == "2":
                    return prerelease_ver
                elif choice == "3":
                    log_info("Обновление ядра пропущено.")
                    return None
                elif choice == "4":
                    while True:
                        custom_tag = input("  Введите тег версии (например v0.0.8): ").strip()
                        if custom_tag:
                            if not custom_tag.startswith("v"):
                                custom_tag = "v" + custom_tag
                            return custom_tag
        else:
            active_ver = stable_ver or latest_any
            if active_ver:
                default_choice = "2" if is_up_to_date else "1"
                print(f"  {CYAN}1){RESET} 🟢 Установить версию ({active_ver})")
                print(f"  {CYAN}2){RESET} ⏹️  Оставить текущую версию (пропустить)")
                print(f"  {CYAN}3){RESET} ✏️  Ввести тег/версию вручную\n")

                while True:
                    try:
                        raw = input(f"  {BOLD}Выберите вариант [1-3]{RESET} (по умолчанию {default_choice}): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("")
                        raw = default_choice
                    choice = re.sub(r"[^1-3]", "", raw) or default_choice
                    if choice == "1":
                        return active_ver
                    elif choice == "2":
                        log_info("Обновление ядра пропущено.")
                        return None
                    elif choice == "3":
                        while True:
                            custom_tag = input("  Введите тег версии (например v0.0.8): ").strip()
                            if custom_tag:
                                if not custom_tag.startswith("v"):
                                    custom_tag = "v" + custom_tag
                                return custom_tag
            else:
                print(f"  {CYAN}1){RESET} ✏️  Ввести тег/версию вручную")
                print(f"  {CYAN}2){RESET} ⏹️  Пропустить обновление ядра\n")
                while True:
                    try:
                        raw = input(f"  {BOLD}Выберите вариант [1-2]{RESET} (по умолчанию 1): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("")
                        raw = "1"
                    choice = re.sub(r"[^1-2]", "", raw) or "1"
                    if choice == "1":
                        while True:
                            custom_tag = input("  Введите тег версии (например v0.0.8): ").strip()
                            if custom_tag:
                                if not custom_tag.startswith("v"):
                                    custom_tag = "v" + custom_tag
                                return custom_tag
                    elif choice == "2":
                        log_info("Обновление ядра пропущено.")
                        return None

    def _fetch_release_metadata(self, tag: str) -> Tuple[Dict[str, str], Dict[str, int]]:
        """Fetches SHA-256 digests and asset sizes from GitHub release metadata."""
        endpoint = f"https://api.github.com/repos/{self.REPO}/releases/tags/{tag}"
        if tag == "latest":
            endpoint = f"https://api.github.com/repos/{self.REPO}/releases/latest"

        data = self.downloader.fetch_github_api(endpoint)
        checksum_map: Dict[str, str] = {}
        size_map: Dict[str, int] = {}
        if isinstance(data, dict):
            for a in data.get("assets", []):
                name = a.get("name")
                digest = a.get("digest", "")
                size = a.get("size", 0)
                if name:
                    if size:
                        size_map[name] = size
                    if digest:
                        if ":" in digest:
                            digest = digest.split(":", 1)[1]
                        checksum_map[name] = digest
        return checksum_map, size_map

    def download_core(self, tag: str) -> bool:
        """Downloads only the single C-shared dynamic library (libsentinel-core.so / .dll)."""
        log_info(f"Установка Sentinel-Core (C-FFI) {BOLD}{tag}{RESET} в {self.bin_dir}...")

        os_name, arch, lib_ext = self._get_platform_info()
        base_release_url = f"https://github.com/{self.REPO}/releases/download/{tag}"
        checksum_map, size_map = self._fetch_release_metadata(tag)

        lib_asset = f"libsentinel-core-{os_name}-{arch}{lib_ext}"
        target_lib = os.path.join(self.bin_dir, f"libsentinel-core{lib_ext}")

        # Download Shared Library
        lib_ok = self.downloader.download_file_with_mirrors(
            f"{base_release_url}/{lib_asset}",
            target_lib,
            filename_for_log=lib_asset,
            expected_size=size_map.get(lib_asset, 0),
        )
        if not lib_ok:
            log_error(f"Не удалось загрузить библиотеку {lib_asset}")
            return False

        if os_name != "windows":
            try:
                os.chmod(target_lib, 0o755)
            except Exception:
                pass

        if lib_asset in checksum_map:
            actual = Downloader.compute_sha256(target_lib)
            if actual.lower() == checksum_map[lib_asset].lower():
                log_success(f"SHA-256 проверен ({actual[:16]}...)")
            else:
                log_warn(f"Несовпадение SHA-256 для {lib_asset}!")

        # Download CLI Binary if present in release assets
        exe_ext = ".exe" if os_name == "windows" else ""
        cli_asset = f"sentinel-core-{os_name}-{arch}{exe_ext}"
        target_cli = os.path.join(self.bin_dir, f"sentinel-core{exe_ext}")
        if cli_asset in size_map or cli_asset in checksum_map:
            cli_ok = self.downloader.download_file_with_mirrors(
                f"{base_release_url}/{cli_asset}",
                target_cli,
                filename_for_log=cli_asset,
                expected_size=size_map.get(cli_asset, 0),
            )
            if cli_ok and os_name != "windows" and os.path.exists(target_cli):
                try:
                    os.chmod(target_cli, 0o755)
                except Exception:
                    pass

        # Create alias symlink sentinel-core.so in project bin if needed
        alt_lib = os.path.join(self.bin_dir, f"sentinel-core{lib_ext}")
        try:
            if not os.path.exists(alt_lib) and os_name != "windows":
                os.symlink(target_lib, alt_lib)
        except Exception:
            pass

        return True

