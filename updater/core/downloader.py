"""Direct GitHub and Multi-Mirror Downloader with live ProgressBar and SHA-256 validation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

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
    ProgressBar,
    log_error,
    log_info,
    log_success,
    log_warn,
)

socket.setdefaulttimeout(8.0)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# High-speed CDN mirror prefixes (ordered by reliability)
FAST_MIRRORS = [
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://gh.ddlc.top/",
    "https://ghproxy.net/",
]


class Downloader:
    """Handles resilient file downloads with real-time ProgressBar, HTTP API requests, and SHA-256 validation."""

    def __init__(self, proxy_url: Optional[str] = None) -> None:
        self.proxy_url = proxy_url

    def _query_content_length(self, url: str, use_proxy: bool) -> int:
        """Fetches Content-Length header by following redirects (-L)."""
        if shutil.which("curl"):
            try:
                cmd = ["curl", "-sIL", "-k", "--connect-timeout", "3", "--max-time", "5", "-H", f"User-Agent: {USER_AGENT}"]
                if use_proxy and self.proxy_url:
                    p = self.proxy_url
                    if p.startswith("socks5://"):
                        p = "socks5h://" + p[len("socks5://"):]
                    cmd.extend(["-x", p])
                else:
                    cmd.extend(["--noproxy", "*"])
                cmd.append(url)
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=5.5).decode("utf-8", errors="ignore")
                content_lengths = []
                for line in out.splitlines():
                    if line.lower().startswith("content-length:"):
                        val = line.split(":", 1)[1].strip()
                        if val.isdigit():
                            content_lengths.append(int(val))
                if content_lengths:
                    return content_lengths[-1]
            except Exception:
                pass
        return 0

    def _download_with_curl(
        self,
        url: str,
        dest: str,
        use_proxy: bool,
        filename_label: str,
        expected_size: int = 0,
        timeout: float = 30.0,
    ) -> bool:
        """Executes curl with live ProgressBar updating as file chunks arrive on disk."""
        if not shutil.which("curl"):
            return False

        tmp_dest = f"{dest}.tmp.{os.getpid()}"
        if os.path.isfile(tmp_dest):
            try:
                os.remove(tmp_dest)
            except Exception:
                pass

        total_size = expected_size if expected_size > 0 else self._query_content_length(url, use_proxy)
        pbar = ProgressBar(filename=filename_label, total_bytes=total_size)

        curl_cmd = [
            "curl", "-fsSL", "-k",
            "--connect-timeout", "4",
            "--max-time", str(int(timeout)),
            "--speed-time", "4",
            "--speed-limit", "20000",
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

        try:
            proc = subprocess.Popen(curl_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            last_size = 0

            while proc.poll() is None:
                if os.path.isfile(tmp_dest):
                    cur_size = os.path.getsize(tmp_dest)
                    delta = cur_size - last_size
                    if delta > 0:
                        pbar.update(delta)
                        last_size = cur_size
                time.sleep(0.06)

            if proc.returncode == 0 and os.path.isfile(tmp_dest):
                file_size = os.path.getsize(tmp_dest)
                delta = file_size - last_size
                if delta > 0:
                    pbar.update(delta)

                min_size = 2 * 1024 * 1024 if (dest.endswith(".so") or dest.endswith("sentinel-core") or dest.endswith(".dll")) else 100
                if file_size >= min_size:
                    if platform.system() != "Windows" and not dest.endswith(".h"):
                        try:
                            os.chmod(tmp_dest, 0o755)
                        except Exception:
                            pass
                    os.replace(tmp_dest, dest)
                    pbar.finish(success=True)
                    return True
        except Exception:
            pass
        finally:
            pbar.finish(success=False)
            if os.path.isfile(tmp_dest):
                try:
                    os.remove(tmp_dest)
                except Exception:
                    pass

        return False

    def _download_with_urllib(
        self,
        url: str,
        dest: str,
        use_proxy: bool,
        filename_label: str,
        expected_size: int = 0,
        timeout: float = 25.0,
    ) -> bool:
        """Fallback urllib streaming downloader with live ProgressBar."""
        tmp_dest = f"{dest}.tmp.{os.getpid()}"
        if os.path.isfile(tmp_dest):
            try:
                os.remove(tmp_dest)
            except Exception:
                pass

        pbar: Optional[ProgressBar] = None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers: list = [urllib.request.HTTPSHandler(context=ctx)]

            if use_proxy and self.proxy_url and not self.proxy_url.startswith("socks"):
                handlers.append(urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url}))

            opener = urllib.request.build_opener(*handlers)
            start_time = time.time()

            with opener.open(req, timeout=6.0) as resp, open(tmp_dest, "wb") as f_out:
                if resp.status == 200:
                    cl_header = resp.headers.get("Content-Length")
                    total_bytes = expected_size if expected_size > 0 else (int(cl_header) if cl_header and cl_header.isdigit() else 0)
                    pbar = ProgressBar(filename=filename_label, total_bytes=total_bytes)

                    while True:
                        if time.time() - start_time > timeout:
                            break
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        pbar.update(len(chunk))

            if os.path.isfile(tmp_dest):
                file_size = os.path.getsize(tmp_dest)
                min_size = 2 * 1024 * 1024 if (dest.endswith(".so") or dest.endswith("sentinel-core") or dest.endswith(".dll")) else 100
                if file_size >= min_size:
                    if platform.system() != "Windows" and not dest.endswith(".h"):
                        try:
                            os.chmod(tmp_dest, 0o755)
                        except Exception:
                            pass
                    os.replace(tmp_dest, dest)
                    if pbar:
                        pbar.finish(success=True)
                    return True
        except Exception:
            pass
        finally:
            if pbar:
                pbar.finish(success=False)
            if os.path.isfile(tmp_dest):
                try:
                    os.remove(tmp_dest)
                except Exception:
                    pass

        return False

    def download_file_with_mirrors(
        self,
        direct_url: str,
        dest_path: str,
        filename_for_log: str = "",
        expected_size: int = 0,
    ) -> bool:
        """Downloads a file trying active proxy FIRST if available, then fast CDN mirrors."""
        log_name = filename_for_log or os.path.basename(dest_path)
        log_info(f"Загрузка {BOLD}{log_name}{RESET}...")

        candidate_urls: List[Tuple[str, bool]] = []
        if self.proxy_url:
            candidate_urls.append((direct_url, True))

        for prefix in FAST_MIRRORS:
            candidate_urls.append((f"{prefix}{direct_url}", False))

        if not self.proxy_url:
            candidate_urls.append((direct_url, False))

        for url, use_proxy in candidate_urls:
            if self._download_with_curl(url, dest_path, use_proxy=use_proxy, filename_label=log_name, expected_size=expected_size, timeout=30.0):
                return True
            if self._download_with_urllib(url, dest_path, use_proxy=use_proxy, filename_label=log_name, expected_size=expected_size, timeout=25.0):
                return True

        log_error(f"Не удалось загрузить {log_name} ни с одного источника.")
        return False

    def download_bytes_with_mirrors(
        self,
        direct_url: str,
        label_for_log: str = "",
        expected_size: int = 0,
    ) -> Optional[bytes]:
        """Downloads bytes directly into memory with live ProgressBar and automated failover."""
        log_name = label_for_log or "архива"
        log_info(f"Загрузка архива {BOLD}{log_name}{RESET}...")

        tmp_dest = f"/tmp/download_bytes_{os.getpid()}.tmp"
        if platform.system() == "Windows":
            tmp_dest = os.path.join(os.environ.get("TEMP", "."), f"download_bytes_{os.getpid()}.tmp")

        try:
            if self.download_file_with_mirrors(direct_url, tmp_dest, filename_for_log=log_name, expected_size=expected_size):
                if os.path.isfile(tmp_dest):
                    with open(tmp_dest, "rb") as f:
                        return f.read()
        finally:
            if os.path.isfile(tmp_dest):
                try:
                    os.remove(tmp_dest)
                except Exception:
                    pass

        return None

    def fetch_github_api(self, endpoint_url: str, timeout: float = 5.0) -> Optional[Any]:
        """Queries GitHub REST API with mirror fallback and strict timeout."""
        api_candidates = []
        if self.proxy_url:
            api_candidates.append((endpoint_url, True))

        api_candidates.extend([
            (f"https://gh-proxy.com/{endpoint_url}", False),
            (f"https://ghfast.top/{endpoint_url}", False),
        ])

        if not self.proxy_url:
            api_candidates.append((endpoint_url, False))

        for api_url, use_proxy in api_candidates:
            if shutil.which("curl"):
                try:
                    curl_cmd = [
                        "curl", "-fsSL", "-k",
                        "--connect-timeout", "3",
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
                    res = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=timeout + 1.0)
                    if res.returncode == 0 and res.stdout.strip():
                        return json.loads(res.stdout)
                except Exception:
                    pass

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
