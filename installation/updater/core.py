"""Sentinel-Core Engine Downloader & Manager for Sentinel Panel."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

from .common import (
    BOLD,
    CYAN,
    DIM,
    GREEN,
    RED,
    RESET,
    YELLOW,
    log_banner,
    log_error,
    log_info,
    log_success,
    log_warn,
)


class CoreManager:
    """Manages querying GitHub releases, downloading binaries & shared libraries, and verifying digests."""

    REPO = "blackalex1/sentinel-core"

    def __init__(self, project_dir: str, proxy_url: Optional[str] = None, auto_mode: bool = False, force: bool = False) -> None:
        self.project_dir = project_dir
        self.bin_dir = os.path.join(project_dir, "bin")
        self.proxy_url = proxy_url
        self.auto_mode = auto_mode
        self.force = force
        self.direct_github_blocked = False

        os.makedirs(self.bin_dir, exist_ok=True)

    def _get_installed_version(self) -> Tuple[bool, str]:
        """Detects currently installed core version."""
        exe_path = os.path.join(self.bin_dir, "sentinel-core")
        if platform.system() == "Windows":
            exe_path += ".exe"

        if os.path.isfile(exe_path):
            try:
                out = subprocess.check_output([exe_path, "--version"], stderr=subprocess.STDOUT, timeout=3).decode().strip()
                match = re.search(r"v\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?", out)
                ver_tag = match.group(0) if match else out
                return True, ver_tag
            except Exception:
                return True, "Установлена (версия не определена)"

        so_path = os.path.join(self.bin_dir, "libsentinel-core.so")
        if os.path.isfile(so_path):
            return True, "Установлена (.so найдена)"

        return False, "Не установлена"

    def _fetch_releases(self) -> Tuple[str, str, str]:
        """Queries GitHub API (via proxy or mirrors) and returns (stable_ver, prerelease_ver, latest_any)."""
        log_info(f"Опрос GitHub Releases для {self.REPO}...")

        api_urls = [
            f"https://api.github.com/repos/{self.REPO}/releases",
            f"https://gh-proxy.com/https://api.github.com/repos/{self.REPO}/releases",
            f"https://ghfast.top/https://api.github.com/repos/{self.REPO}/releases",
            f"https://gh.ddlc.top/https://api.github.com/repos/{self.REPO}/releases",
        ]

        # First attempt via curl with socks5h support if available
        if shutil.which("curl"):
            curl_cmd = ["curl", "-fsSL", "-k", "-H", "User-Agent: SentinelPanel/1.0", "--connect-timeout", "6", "--max-time", "12"]
            if self.proxy_url:
                proxy_arg = self.proxy_url
                if proxy_arg.startswith("socks5://"):
                    proxy_arg = "socks5h://" + proxy_arg[len("socks5://") :]
                curl_cmd.extend(["-x", proxy_arg])

            for url in api_urls:
                try:
                    res = subprocess.run(curl_cmd + [url], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=14)
                    if res.returncode == 0 and '"tag_name"' in res.stdout:
                        releases = json.loads(res.stdout)
                        if isinstance(releases, list) and releases:
                            stable = next((r["tag_name"] for r in releases if not r.get("prerelease")), "")
                            prerelease = releases[0]["tag_name"] if releases[0].get("prerelease") else ""
                            latest_any = releases[0]["tag_name"]
                            return stable, prerelease, latest_any
                except Exception:
                    continue

        # Fallback via Python urllib
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        handlers: list = [urllib.request.HTTPSHandler(context=ctx)]
        if self.proxy_url and not self.proxy_url.startswith("socks"):
            handlers.append(urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url}))

        opener = urllib.request.build_opener(*handlers)

        for url in api_urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "SentinelPanel/1.0"})
                with opener.open(req, timeout=5) as response:
                    releases = json.loads(response.read().decode("utf-8"))
                    if isinstance(releases, list) and releases:
                        stable = next((r["tag_name"] for r in releases if not r.get("prerelease")), "")
                        prerelease = releases[0]["tag_name"] if releases[0].get("prerelease") else ""
                        latest_any = releases[0]["tag_name"]
                        return stable, prerelease, latest_any
            except Exception:
                continue

        return "", "", ""

    def select_version(self) -> Optional[str]:
        """Runs the interactive or automated version selector."""
        is_installed, current_ver = self._get_installed_version()
        stable_ver, prerelease_ver, latest_any = self._fetch_releases()

        # Non-interactive automated mode
        if not sys.stdin.isatty() or self.auto_mode:
            target = stable_ver or prerelease_ver or latest_any or "v0.0.8"
            if not self.force and is_installed and target in current_ver:
                log_info(f"Текущая версия ядра ({current_ver}) уже актуальна ({target}). Обновление не требуется.")
                return None
            return target

        log_banner("🛡️  ВЫБОР ВЕРСИИ ЯДРА SENTINEL-CORE")
        print(f"📌 Текущая версия:              {BOLD}{current_ver}{RESET}")
        print(f"🟢 Последняя стабильная (Stable): {GREEN}{stable_ver or 'Отсутствует'}{RESET}")
        print(f"🟡 Пре-релиз / Бета (Pre-release): {YELLOW}{prerelease_ver or 'Отсутствует'}{RESET}")
        print("=" * 60)

        current_tag_match = re.search(r"v\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?", current_ver)
        current_tag = current_tag_match.group(0) if current_tag_match else ""
        is_up_to_date = bool(is_installed and stable_ver and current_tag == stable_ver)

        if prerelease_ver and stable_ver:
            if not is_up_to_date:
                default_choice = "1"
                print(f"  1) 🟢 Установить стабильную версию ({stable_ver}) [Рекомендуется / По умолчанию]")
                print(f"  2) 🟡 Установить пре-релиз / бету ({prerelease_ver}) [Экспериментальная]")
                print(f"  3) ⏹️  Оставить текущую версию (пропустить)")
            else:
                default_choice = "3"
                print(f"  1) 🟢 Переустановить стабильную версию ({stable_ver})")
                print(f"  2) 🟡 Установить пре-релиз / бету ({prerelease_ver}) [Экспериментальная]")
                print(f"  3) ⏹️  Оставить текущую версию ({stable_ver}) [По умолчанию / Актуально]")
            print(f"  4) ✏️  Ввести тег/версию вручную")

            while True:
                try:
                    raw = input(f"Выберите вариант [1-4] (по умолчанию {default_choice}): ").strip()
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
                        tag_in = input(f"Введите тег релиза (например {stable_ver}): ").strip()
                        if tag_in:
                            return tag_in
                print(f"{RED}❌ Неверный ввод '{raw}'. Пожалуйста, введите цифру от 1 до 4.{RESET}")

        elif stable_ver:
            if not is_up_to_date:
                default_choice = "1"
                print(f"  1) 🟢 Установить стабильную версию ({stable_ver}) [Рекомендуется / По умолчанию]")
                print(f"  2) ⏹️  Оставить текущую версию (пропустить)")
            else:
                default_choice = "2"
                print(f"  1) 🟢 Переустановить стабильную версию ({stable_ver})")
                print(f"  2) ⏹️  Оставить текущую версию ({stable_ver}) [По умолчанию / Актуально]")
            print(f"  3) ✏️  Ввести тег/версию вручную")

            while True:
                try:
                    raw = input(f"Выберите вариант [1-3] (по умолчанию {default_choice}): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("")
                    raw = default_choice
                choice = re.sub(r"[^1-3]", "", raw) or default_choice
                if choice == "1":
                    return stable_ver
                elif choice == "2":
                    log_info("Обновление ядра пропущено.")
                    return None
                elif choice == "3":
                    while True:
                        tag_in = input(f"Введите тег релиза (например {stable_ver}): ").strip()
                        if tag_in:
                            return tag_in
                print(f"{RED}❌ Неверный ввод '{raw}'. Пожалуйста, введите цифру от 1 до 3.{RESET}")

        else:
            default_choice = "1"
            print(f"  1) 🟢 Скачать последний стабильный релиз (v0.0.8)")
            print(f"  2) ✏️  Ввести версию вручную")
            print(f"  3) ⏹️  Оставить текущую версию (пропустить) [По умолчанию]")

            while True:
                try:
                    raw = input(f"Выберите вариант [1-3] (по умолчанию {default_choice}): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("")
                    raw = default_choice
                choice = re.sub(r"[^1-3]", "", raw) or default_choice
                if choice == "1":
                    return "v0.0.8"
                elif choice == "2":
                    while True:
                        tag_in = input("Введите тег релиза вручную: ").strip()
                        if tag_in:
                            return tag_in
                elif choice == "3":
                    log_info("Обновление ядра пропущено.")
                    return None
                print(f"{RED}❌ Неверный ввод '{raw}'. Пожалуйста, введите цифру от 1 до 3.{RESET}")

    def _fetch_asset_digests(self, tag: str) -> Dict[str, Tuple[str, int]]:
        """Fetches SHA-256 digests and exact file sizes from release metadata."""
        digests: Dict[str, Tuple[str, int]] = {}
        urls = [
            f"https://api.github.com/repos/{self.REPO}/releases/tags/{tag}",
            f"https://gh-proxy.com/https://api.github.com/repos/{self.REPO}/releases/tags/{tag}",
            f"https://ghfast.top/https://api.github.com/repos/{self.REPO}/releases/tags/{tag}",
        ]

        if shutil.which("curl"):
            curl_cmd = ["curl", "-fsSL", "-k", "-H", "User-Agent: SentinelPanel/1.0", "--connect-timeout", "6", "--max-time", "12"]
            if self.proxy_url:
                proxy_arg = self.proxy_url
                if proxy_arg.startswith("socks5://"):
                    proxy_arg = "socks5h://" + proxy_arg[len("socks5://") :]
                curl_cmd.extend(["-x", proxy_arg])

            for u in urls:
                try:
                    res = subprocess.run(curl_cmd + [u], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=14)
                    if res.returncode == 0 and '"assets"' in res.stdout:
                        rel = json.loads(res.stdout)
                        for a in rel.get("assets", []):
                            name = a.get("name")
                            digest = a.get("digest", "")
                            size = a.get("size", 0)
                            if name:
                                digests[name] = (digest.replace("sha256:", ""), size)
                        if digests:
                            return digests
                except Exception:
                    continue

        return digests

    def _download_file(self, asset_name: str, dest_path: str, tag: str, expected_hash: str = "", expected_size: int = 0) -> bool:
        """Downloads a release file with live ANSI progress bar and SHA-256 verification."""
        candidate_bases = [
            f"https://github.com/{self.REPO}/releases/download/{tag}",
            f"https://gh-proxy.com/https://github.com/{self.REPO}/releases/download/{tag}",
            f"https://ghfast.top/https://github.com/{self.REPO}/releases/download/{tag}",
            f"https://gh.ddlc.top/https://github.com/{self.REPO}/releases/download/{tag}",
            f"https://ghproxy.net/https://github.com/{self.REPO}/releases/download/{tag}",
        ]

        tmp_file = f"/tmp/{asset_name}.{os.getpid()}"
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass

        for base in candidate_bases:
            is_mirror = any(m in base for m in ("gh-proxy", "ghfast", "ddlc", "ghproxy"))
            label = f"CDN-зеркало ({base.split('/')[2]})" if is_mirror else "Официальный GitHub"

            # Skip direct GitHub if already detected as blocked and no proxy configured
            if not is_mirror and self.direct_github_blocked and not self.proxy_url:
                continue

            url = f"{base}/{asset_name}"
            print(f"  ➜ Попытка загрузки {asset_name} из {label}...", flush=True)

            # Try curl download with streaming progress
            if shutil.which("curl"):
                curl_cmd = ["curl", "-fsSL", "-k"]
                if self.proxy_url:
                    p_arg = self.proxy_url
                    if p_arg.startswith("socks5://"):
                        p_arg = "socks5h://" + p_arg[len("socks5://") :]
                    curl_cmd.extend(["--connect-timeout", "10", "--max-time", "60", "-x", p_arg])
                elif is_mirror:
                    curl_cmd.extend(["--connect-timeout", "6", "--max-time", "45"])
                else:
                    # 2.5s fast probe for direct GitHub to immediately bypass throttled AWS S3
                    curl_cmd.extend(["--connect-timeout", "2", "--max-time", "3", "--speed-limit", "102400", "--speed-time", "2"])

                curl_cmd.extend([url, "-o", tmp_file])

                try:
                    res = subprocess.run(curl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=65)
                    if res.returncode != 0 and not is_mirror and not self.proxy_url:
                        self.direct_github_blocked = True
                except Exception:
                    if not is_mirror and not self.proxy_url:
                        self.direct_github_blocked = True

            # If curl didn't produce file, fallback to Python urllib streaming
            if not os.path.isfile(tmp_file) or os.path.getsize(tmp_file) < 100:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                handlers: list = [urllib.request.HTTPSHandler(context=ctx)]
                if self.proxy_url and not self.proxy_url.startswith("socks"):
                    handlers.append(urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url}))
                opener = urllib.request.build_opener(*handlers)

                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "SentinelPanel/1.0"})
                    start_time = time.time()
                    with opener.open(req, timeout=15) as resp, open(tmp_file, "wb") as f_out:
                        total_len = int(resp.headers.get("Content-Length", expected_size or 7442616))
                        downloaded = 0
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            downloaded += len(chunk)

                            elapsed = max(time.time() - start_time, 0.001)
                            speed_kb = (downloaded / 1024) / elapsed
                            pct = min(100.0, (downloaded / total_len) * 100) if total_len > 0 else 50.0
                            bar_len = int(pct // 5)
                            bar = "█" * bar_len + "░" * (20 - bar_len)
                            sys.stdout.write(f"\r   [{bar}] {pct:.1f}% ({downloaded / (1024*1024):.2f}/{total_len / (1024*1024):.2f} MB) {speed_kb:.1f} KB/s")
                            sys.stdout.flush()
                        print("")
                except Exception:
                    if not is_mirror and not self.proxy_url:
                        self.direct_github_blocked = True
                    if os.path.exists(tmp_file):
                        try:
                            os.remove(tmp_file)
                        except Exception:
                            pass
                    continue

            # Verify downloaded file
            if os.path.isfile(tmp_file) and os.path.getsize(tmp_file) > 100:
                file_size = os.path.getsize(tmp_file)

                # Check if file is HTML error page
                with open(tmp_file, "rb") as f_check:
                    head = f_check.read(256)
                    if b"<!DOCTYPE" in head or b"<html" in head or b"404: Not Found" in head or b'{"message":' in head:
                        os.remove(tmp_file)
                        continue

                # SHA-256 Verification
                if expected_hash:
                    with open(tmp_file, "rb") as f_hash:
                        actual_hash = hashlib.sha256(f_hash.read()).hexdigest()
                    if actual_hash != expected_hash:
                        log_warn(f"SHA-256 не совпадает для {asset_name}. Пробуем следующий источник...")
                        os.remove(tmp_file)
                        continue
                    log_success(f"SHA-256 проверен ({actual_hash[:16]}...)")
                elif expected_size > 0 and file_size != expected_size:
                    log_warn(f"Размер {asset_name} не совпадает ({file_size} != {expected_size}). Пробуем следующий источник...")
                    os.remove(tmp_file)
                    continue

                # Safe atomic replace and permissions
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                shutil.move(tmp_file, dest_path)
                if not asset_name.endswith(".h"):
                    try:
                        os.chmod(dest_path, 0o755)
                    except Exception:
                        pass
                log_success(f"Успешно установлен {asset_name} -> {dest_path}")
                return True

        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
        return False

    def update_core(self) -> bool:
        """Runs the complete core engine download and upgrade workflow."""
        selected_tag = self.select_version()
        if not selected_tag:
            return True

        log_info(f"Выбранная версия для загрузки: {BOLD}{selected_tag}{RESET}")

        digests = self._fetch_asset_digests(selected_tag)

        # Asset mappings
        assets = [
            ("sentinel-core-linux-amd64", os.path.join(self.bin_dir, "sentinel-core")),
            ("libsentinel-core-linux-amd64.so", os.path.join(self.bin_dir, "libsentinel-core.so")),
            ("sentinel-core.h", os.path.join(self.bin_dir, "sentinel-core.h")),
        ]

        all_ok = True
        for asset_name, dest_path in assets:
            expected_hash, expected_size = digests.get(asset_name, ("", 0))
            ok = self._download_file(asset_name, dest_path, selected_tag, expected_hash, expected_size)
            if not ok:
                log_error(f"Не удалось загрузить {asset_name}.")
                all_ok = False

        # Create symlinks in standard system search paths if on Linux
        if platform.system() != "Windows":
            so_src = os.path.join(self.bin_dir, "libsentinel-core.so")
            if os.path.isfile(so_src):
                for dest_link in ("/usr/local/lib/libsentinel-core.so", "/usr/lib/libsentinel-core.so"):
                    try:
                        if os.path.islink(dest_link) or os.path.isfile(dest_link):
                            os.remove(dest_link)
                        os.symlink(so_src, dest_link)
                    except Exception:
                        pass
                try:
                    subprocess.run(["ldconfig"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass

        return all_ok
