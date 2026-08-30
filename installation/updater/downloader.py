"""Direct GitHub Downloader for Sentinel Controller Updater."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import urllib.request
from typing import Any, Dict, Optional

from .common import BOLD, RESET, log_error, log_info, log_success, log_warn


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class Downloader:
    """Handles file downloads, HTTP API requests, and SHA-256 validation directly from GitHub."""

    def __init__(self, proxy_url: Optional[str] = None) -> None:
        self.proxy_url = proxy_url

    def _build_opener(self) -> urllib.request.OpenerDirector:
        """Builds an urllib opener configured with SSL and optional proxy."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        handlers: list = [urllib.request.HTTPSHandler(context=ctx)]
        if self.proxy_url:
            p_dict = {
                "http": self.proxy_url,
                "https": self.proxy_url,
            }
            handlers.append(urllib.request.ProxyHandler(p_dict))

        return urllib.request.build_opener(*handlers)

    def _download_single_url(self, url: str, dest: str, use_proxy: bool = True, timeout: float = 120.0) -> bool:
        """Downloads from a single URL to destination with validation."""
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        tmp_dest = f"{dest}.tmp.{os.getpid()}"

        def _clean():
            if os.path.isfile(tmp_dest):
                try:
                    os.remove(tmp_dest)
                except Exception:
                    pass

        _clean()

        # 1. Try curl with resilient speed guard
        if shutil.which("curl"):
            try:
                is_interactive = sys.stdout.isatty()
                progress_flag = "-#" if is_interactive else "-s"
                curl_cmd = [
                    "curl", progress_flag, "-L", "-k",
                    "--connect-timeout", "6",
                    "--max-time", str(int(timeout)),
                    "--speed-time", "12",
                    "--speed-limit", "30720",  # 30 KB/s threshold (only drop dead/stalled connections)
                    "-H", f"User-Agent: {USER_AGENT}",
                    "-o", tmp_dest,
                ]

                if use_proxy and self.proxy_url:
                    p = self.proxy_url
                    if p.startswith("socks5://"):
                        p = "socks5h://" + p[len("socks5://"):]
                    curl_cmd.extend(["-x", p])
                else:
                    curl_cmd.extend(["--noproxy", "*"])

                curl_cmd.append(url)

                if is_interactive:
                    res = subprocess.run(curl_cmd, timeout=timeout + 5.0)
                else:
                    res = subprocess.run(curl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 5.0)

                if res.returncode == 0 and os.path.isfile(tmp_dest):
                    file_size = os.path.getsize(tmp_dest)
                    min_size = 3 * 1024 * 1024 if (dest.endswith(".so") or dest.endswith("sentinel-core")) else 1000
                    if file_size >= min_size:
                        with open(tmp_dest, "rb") as f_chk:
                            head = f_chk.read(256)
                            if not (b"<!DOCTYPE" in head or b"<html" in head or b"404: Not Found" in head):
                                if platform.system() != "Windows" and not dest.endswith(".h"):
                                    try:
                                        os.chmod(tmp_dest, 0o755)
                                    except Exception:
                                        pass
                                os.replace(tmp_dest, dest)
                                size_mb = file_size / (1024 * 1024)
                                log_info(f"  [✓] Загружено: {size_mb:.1f} MB")
                                return True
            except Exception:
                pass
            finally:
                _clean()

        # 2. Try urllib fallback
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT},
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers = [urllib.request.HTTPSHandler(context=ctx)]
            if use_proxy and self.proxy_url and not self.proxy_url.startswith("socks"):
                handlers.append(urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url}))
            opener = urllib.request.build_opener(*handlers)

            start_time = time.time()
            with opener.open(req, timeout=timeout) as resp, open(tmp_dest, "wb") as f_out:
                if resp.status == 200:
                    total_len = int(resp.headers.get("Content-Length", 0))
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

            if os.path.isfile(tmp_dest):
                file_size = os.path.getsize(tmp_dest)
                min_size = 3 * 1024 * 1024 if (dest.endswith(".so") or dest.endswith("sentinel-core")) else 1000
                if file_size >= min_size:
                    with open(tmp_dest, "rb") as f_chk:
                        head = f_chk.read(256)
                        if not (b"<!DOCTYPE" in head or b"<html" in head or b"404: Not Found" in head):
                            if platform.system() != "Windows" and not dest.endswith(".h"):
                                try:
                                    os.chmod(tmp_dest, 0o755)
                                except Exception:
                                    pass
                            os.replace(tmp_dest, dest)
                            size_mb = file_size / (1024 * 1024)
                            log_info(f"  [✓] Загружено: {size_mb:.1f} MB")
                            return True
        except Exception:
            pass
        finally:
            _clean()

        return False

    def _download_bytes_single_url(self, url: str, use_proxy: bool = True, timeout: float = 120.0) -> Optional[bytes]:
        """Downloads bytes from a single URL into memory."""
        # 1. Try curl
        if shutil.which("curl"):
            try:
                curl_cmd = [
                    "curl", "-sSL", "-k",
                    "--connect-timeout", "6",
                    "--max-time", str(int(timeout)),
                    "--speed-time", "12",
                    "--speed-limit", "30720",
                    "-H", f"User-Agent: {USER_AGENT}",
                ]
                if use_proxy and self.proxy_url:
                    p = self.proxy_url
                    if p.startswith("socks5://"):
                        p = "socks5h://" + p[len("socks5://"):]
                    curl_cmd.extend(["-x", p])
                else:
                    curl_cmd.extend(["--noproxy", "*"])

                curl_cmd.append(url)
                res = subprocess.run(curl_cmd, capture_output=True, timeout=timeout + 5.0)
                if res.returncode == 0 and res.stdout and len(res.stdout) > 1024:
                    if not (b"<!DOCTYPE" in res.stdout[:256] or b"<html" in res.stdout[:256] or b"404: Not Found" in res.stdout[:256]):
                        return res.stdout
            except Exception:
                pass

        # 2. Try urllib
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT},
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers = [urllib.request.HTTPSHandler(context=ctx)]
            if use_proxy and self.proxy_url and not self.proxy_url.startswith("socks"):
                handlers.append(urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url}))
            opener = urllib.request.build_opener(*handlers)
            with opener.open(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if data and len(data) > 1024 and not (b"<!DOCTYPE" in data[:256] or b"<html" in data[:256]):
                        return data
        except Exception:
            pass

        return None

    def download_file_with_mirrors(self, direct_url: str, dest_path: str, filename_for_log: str = "") -> bool:
        """Downloads a file with automated failover through high-speed CDN mirrors and VPN proxy."""
        log_name = filename_for_log or os.path.basename(dest_path)
        log_info(f"  ➜ Загрузка {log_name}...")

        # Fast CDN mirrors first, followed by VPN proxy & direct GitHub
        candidate_urls = [
            (f"https://ghproxy.net/{direct_url}", False),
            (f"https://gh-proxy.com/{direct_url}", False),
            (f"https://ghfast.top/{direct_url}", False),
            (f"https://gh.ddlc.top/{direct_url}", False),
            (f"https://gh.con.sh/{direct_url}", False),
            (direct_url, True),
            (direct_url, False),
        ]

        for url, use_proxy in candidate_urls:
            ok = self._download_single_url(url, dest_path, use_proxy=use_proxy)
            if ok:
                return True

        log_error(f"Не удалось загрузить {log_name} ни с одного источника.")
        return False

    def download_bytes_with_mirrors(self, direct_url: str, label_for_log: str = "") -> Optional[bytes]:
        """Downloads bytes with automated failover through high-speed CDN mirrors and VPN proxy."""
        if label_for_log:
            log_info(f"  ➜ Загрузка {label_for_log}...")

        candidate_urls = [
            (f"https://ghproxy.net/{direct_url}", False),
            (f"https://gh-proxy.com/{direct_url}", False),
            (f"https://ghfast.top/{direct_url}", False),
            (f"https://gh.ddlc.top/{direct_url}", False),
            (f"https://gh.con.sh/{direct_url}", False),
            (direct_url, True),
            (direct_url, False),
        ]

        for url, use_proxy in candidate_urls:
            data = self._download_bytes_single_url(url, use_proxy=use_proxy)
            if data:
                return data

        return None

    def fetch_github_api(self, endpoint_url: str, timeout: float = 8.0) -> Optional[Any]:
        """Queries GitHub REST API with mirror fallback."""
        api_candidates = [
            (endpoint_url, True),
            (f"https://gh-proxy.com/{endpoint_url}", False),
            (f"https://ghfast.top/{endpoint_url}", False),
            (endpoint_url, False),
        ]

        for api_url, use_proxy in api_candidates:
            # 1. Try curl
            if shutil.which("curl"):
                try:
                    curl_cmd = [
                        "curl", "-fsSL", "-k",
                        "--connect-timeout", "4",
                        "--max-time", str(int(timeout)),
                        "-H", f"User-Agent: {USER_AGENT}",
                        "-H", "Accept: application/vnd.github.v3+json",
                    ]
                    if use_proxy and self.proxy_url:
                        p = self.proxy_url
                        if p.startswith("socks5://"):
                            p = "socks5h://" + p[len("socks5://"):]
                        curl_cmd.extend(["-x", p])
                    else:
                        curl_cmd.extend(["--noproxy", "*"])

                    curl_cmd.append(api_url)
                    res = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=timeout + 2.0)
                    if res.returncode == 0 and res.stdout.strip():
                        return json.loads(res.stdout)
                except Exception:
                    pass

            # 2. Try urllib fallback
            try:
                req = urllib.request.Request(
                    api_url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                handlers = [urllib.request.HTTPSHandler(context=ctx)]
                if use_proxy and self.proxy_url and not self.proxy_url.startswith("socks"):
                    handlers.append(urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url}))
                opener = urllib.request.build_opener(*handlers)
                with opener.open(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass

        return None

    @staticmethod
    def compute_sha256(file_path: str) -> str:
        """Calculates SHA-256 hash of a local file."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
