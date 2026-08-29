import os
import sys

# Ensure panel root is the first entry and script directory does not shadow stdlib modules (e.g. backend/ssl)
_current_dir = os.path.dirname(os.path.abspath(__file__))
_panel_root = os.path.dirname(_current_dir)
while _current_dir in sys.path:
    sys.path.remove(_current_dir)
if _panel_root not in sys.path:
    sys.path.insert(0, _panel_root)

import asyncio
import json
import logging
import re
import shutil
import signal
import socket
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Optional, List, Dict, Any, Tuple

from backend import sentinel_core_bridge

logger = logging.getLogger(__name__)

# ТИР 1: Черные списки (Hysteria 2 / Trojan / VLESS Reality / Shadowsocks)
BLACK_LIST_SOURCES = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_SS%2BAll_RUS.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS_mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS.txt",
]

# ТИР 2: Белые списки (VLESS Reality CIDR/SNI)
WHITE_LIST_SOURCES = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-checked.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-SNI-RU-all.txt",
]

# ТИР 3: Открытые SOCKS5 прокси (Крайний случай)
SOCKS5_FALLBACK_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all&ssl=all&anonymity=all"
]


def _free_port(port: int):
    """Освобождает указанный локальный порт на Linux/Unix."""
    if sys.platform == "win32":
        return
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def parse_vpn_uri(uri: str) -> Optional[Dict[str, Any]]:
    """Парсит URI подписки через Go-ядро sentinel-core."""
    try:
        res = sentinel_core_bridge.parse_subscription(uri)
        if res and isinstance(res, list) and len(res) > 0:
            return res[0]
    except Exception as e:
        logger.debug("Failed to parse URI %s via core: %s", uri[:30], e)
    return None


class SocksProxyRotator:
    def __init__(self):
        self.cached_proxies = []
        self.last_scrape_time = 0
        self.scrape_cooldown = 300
        self._singbox_proc: Optional[subprocess.Popen] = None
        self._last_working_source_tier: str = ""
        self._current_engine: str = "singbox"

    def _find_proxy_engine_bin(self) -> Tuple[Optional[str], str]:
        """Ищет бинарник sing-box или xray на сервере."""
        bin_dir = os.path.join(_panel_root, "bin")

        singbox_candidates = [
            os.path.join(bin_dir, "sing-box.exe" if sys.platform == "win32" else "sing-box"),
            os.path.join(bin_dir, "singbox.exe" if sys.platform == "win32" else "singbox"),
            shutil.which("sing-box"),
            shutil.which("singbox"),
            "/usr/local/bin/sing-box",
            "/usr/bin/sing-box"
        ]
        for c in singbox_candidates:
            if c and os.path.isfile(c) and (sys.platform == "win32" or os.access(c, os.X_OK)):
                return c, "singbox"

        xray_candidates = [
            os.path.join(bin_dir, "xray.exe" if sys.platform == "win32" else "xray"),
            shutil.which("xray"),
            "/usr/local/bin/xray",
            "/usr/bin/xray"
        ]
        for c in xray_candidates:
            if c and os.path.isfile(c) and (sys.platform == "win32" or os.access(c, os.X_OK)):
                return c, "xray"

        return None, ""

    def stop_tunnel(self):
        """Останавливает запущенный фоновый процесс прокси и всю его группу процессов."""
        if self._singbox_proc:
            try:
                if sys.platform != "win32":
                    try:
                        os.killpg(os.getpgid(self._singbox_proc.pid), signal.SIGTERM)
                    except Exception:
                        self._singbox_proc.terminate()
                else:
                    self._singbox_proc.terminate()
                self._singbox_proc.wait(timeout=1.5)
            except Exception:
                try:
                    if sys.platform != "win32":
                        try:
                            os.killpg(os.getpgid(self._singbox_proc.pid), signal.SIGKILL)
                        except Exception:
                            self._singbox_proc.kill()
                    else:
                        self._singbox_proc.kill()
                except Exception:
                    pass
            self._singbox_proc = None

        try:
            if sys.platform != "win32":
                subprocess.run(["pkill", "-9", "-f", "singbox_failover.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["pkill", "-9", "-f", "xray_failover.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        _free_port(10818)
        _free_port(10819)

    def _get_cache_file_path(self) -> str:
        """Путь к локальному дисковому кэшу рабочих VPN-нод."""
        config_dir = os.path.join(_panel_root, "config")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "cached_vpn_nodes.json")

    @staticmethod
    def _get_env_proxy_uri() -> Optional[str]:
        """Считывает настроенный PROXY_URL из .env файлов."""
        env_paths = [
            os.path.join(_panel_root, "config", ".env"),
            os.path.join(_panel_root, ".env"),
            os.path.join(os.path.dirname(_panel_root), ".env"),
        ]
        for p in env_paths:
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("PROXY_URL="):
                                val = line.split("=", 1)[1].strip(" '\"")
                                if val:
                                    return val
                except Exception:
                    pass
        return None

    def _load_cached_nodes_from_disk(self, exclude_env: bool = True) -> List[str]:
        cache_file = self._get_cache_file_path()
        nodes = []
        if os.path.isfile(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        nodes = [str(x) for x in data if x]
            except Exception as e:
                logger.debug("Failed to read cached VPN nodes: %s", e)

        if exclude_env:
            env_uri = self._get_env_proxy_uri()
            if env_uri:
                env_clean = env_uri.strip()
                nodes = [n for n in nodes if n.strip() != env_clean and env_clean not in n]

        return nodes

    def _save_working_nodes_to_disk(self, uris: List[str]):
        if not uris:
            return
        env_uri = self._get_env_proxy_uri()
        env_clean = env_uri.strip() if env_uri else ""
        cache_file = self._get_cache_file_path()
        try:
            existing = self._load_cached_nodes_from_disk(exclude_env=True)
            combined = []
            seen = set()
            for u in uris + existing:
                if u and u not in seen:
                    if env_clean and (u.strip() == env_clean or env_clean in u):
                        continue
                    seen.add(u)
                    combined.append(u)
            combined = combined[:50]
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(combined, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("Failed to write cached VPN nodes: %s", e)

    async def start_or_reload_singbox_tunnel(self, config_json: str, port: int = 10818, engine_type: str = "singbox", target_host: str = "objects.githubusercontent.com") -> bool:
        """Запускает процесс клиента Sing-box с отказоустойчивым multi-node конфигом."""
        self.stop_tunnel()
        _free_port(port)
        _free_port(port + 1)

        bin_path, detected_engine = self._find_proxy_engine_bin()
        if not bin_path:
            logger.warning("Neither sing-box nor xray binary found in PATH or bin/ directory.")
            return False

        engine_type = detected_engine or engine_type
        cfg_dir = os.path.join(_panel_root, "bin")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, f"{engine_type}_failover.json")
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(config_json)
        except Exception as e:
            logger.error("Failed to write failover client config to %s: %s", cfg_path, e)
            return False

        env = os.environ.copy()
        cmd = [bin_path, "run", "-c", cfg_path]
        try:
            extra_kwargs = {}
            if sys.platform != "win32":
                extra_kwargs["preexec_fn"] = os.setsid

            log_path = os.path.join(cfg_dir, f"{engine_type}_rotator.log")
            log_file = open(log_path, "w", encoding="utf-8", errors="ignore")

            self._singbox_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
                env=env,
                **extra_kwargs
            )
            self._current_engine = engine_type

            import threading
            def _stream_logs():
                try:
                    for line in iter(self._singbox_proc.stdout.readline, ''):
                        clean_line = line.strip()
                        if clean_line:
                            log_file.write(clean_line + "\n")
                            log_file.flush()
                except Exception:
                    pass
                finally:
                    log_file.close()

            log_thread = threading.Thread(target=_stream_logs, daemon=True)
            log_thread.start()

            # Brief settle time for Sing-box engine inbounds to bind
            await asyncio.sleep(1.0)

            for attempt in range(1, 6):
                if self._singbox_proc.poll() is not None:
                    logger.warning("%s process terminated with exit code %d (see %s)", engine_type, self._singbox_proc.returncode, log_path)
                    self._singbox_proc = None
                    return False

                logger.debug("[Tunnel] Probing %s via local tunnel (attempt %d/5)...", target_host, attempt)
                ok, lat = await self.test_proxy_alive(f"socks5://127.0.0.1:{port}", target_host=target_host, timeout=2.5)
                if ok:
                    logger.info("Started local %s failover tunnel on port %d (latency: %.1f ms)", engine_type, port, lat)
                    return True

                await asyncio.sleep(0.5)

            logger.warning("%s started on port %d but failed health probe to %s.", engine_type, port, target_host)
            self.stop_tunnel()
            return False
        except Exception as e:
            logger.exception("Failed to launch %s client process: %s", engine_type, e)
            self.stop_tunnel()
            return False

    async def _test_and_activate_nodes(self, uris: List[str], tier_name: str = "Tier", target_host: str = "objects.githubusercontent.com") -> Optional[str]:
        """Тестирует список нод через ядро и поднимает отказоустойчивую группу Sing-box."""
        if not uris:
            return None

        valid_uris = []
        for u in uris:
            u_clean = u.strip()
            # Filter out corrupt entries and restrict to stable modern protocols supported by Sing-box failover
            if (
                u_clean
                and u_clean.startswith(("vless://", "ss://", "shadowsocks://", "trojan://", "hy2://", "hysteria2://"))
                and u_clean not in valid_uris
            ):
                valid_uris.append(u_clean)
            if len(valid_uris) >= 60:
                break

        if not valid_uris:
            return None

        logger.info("[%s] Checking %d nodes via sentinel-core...", tier_name, len(valid_uris))

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None,
            lambda: sentinel_core_bridge.check_proxies(valid_uris, target_host=target_host, timeout_ms=3000, concurrency=32)
        )

        working = [r for r in results if r.get("success") or r.get("alive") or r.get("isAlive")]
        if not working:
            logger.warning("[%s] 0 / %d nodes alive", tier_name, len(valid_uris))
            return None

        working.sort(key=lambda x: x.get("latencyMs", 999999))
        best = working[0]
        best_label = best.get("name") or (best.get("proxyUrl", "")[:35] if best.get("proxyUrl") else "Node")
        logger.info("%s: %d / %d nodes alive. Best: %s (%.1f ms)", tier_name, len(working), len(valid_uris), best_label, best.get("latencyMs", 0))

        # Парсим живые ноды в профили для генерации sing-box конфига
        top_alive_uris = [w.get("proxyUrl") for w in working[:10] if w.get("proxyUrl")]
        parsed_profiles = []
        for u in top_alive_uris:
            p = parse_vpn_uri(u)
            if p:
                parsed_profiles.append(p)

        if not parsed_profiles:
            return None

        logger.info("[Failover] Compiling Sing-box multi-node client config for %d alive nodes...", len(parsed_profiles))
        health_check_endpoint = f"https://{target_host}" if target_host else "https://objects.githubusercontent.com"
        cfg_json = sentinel_core_bridge.build_failover_client_config(
            parsed_profiles,
            socks_port=10818,
            http_port=10819,
            health_url=health_check_endpoint
        )
        if not cfg_json:
            logger.error("[Failover] Failed to compile Sing-box client config from alive profiles")
            return None

        logger.info("[Tunnel] Launching Sing-box client process and activating fastest route...")
        ok = await self.start_or_reload_singbox_tunnel(cfg_json, port=10818, target_host=target_host)
        if ok:
            working_uris = [p.get("proxyUrl") for p in parsed_profiles if p.get("proxyUrl")]
            self._save_working_nodes_to_disk(working_uris)
            self._last_working_source_tier = tier_name
            return "socks5://127.0.0.1:10818"

        return None

    async def _fetch_single_source(self, base_url: str) -> List[str]:
        """Скачивает файл подписки напрямую с GitHub."""
        loop = asyncio.get_running_loop()

        def _fetch_url(target_url: str) -> str:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sentinel/1.0"}
            )
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as response:
                return response.read().decode("utf-8", errors="ignore")

        try:
            content = await loop.run_in_executor(None, _fetch_url, base_url)
            if content and len(content) > 10:
                return [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        except Exception as e:
            logger.debug("Failed to fetch VPN source %s: %s", base_url, e)
        return []

    async def _check_vpn_sources(self, sources: List[str], tier_name: str = "Tier", target_host: str = "objects.githubusercontent.com") -> Optional[str]:
        """Параллельно скачивает подписки и активирует лучший Sing-box туннель."""
        tasks = [self._fetch_single_source(url) for url in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        uris = []
        for r in results:
            if isinstance(r, list):
                uris.extend(r)

        return await self._test_and_activate_nodes(uris, tier_name=tier_name, target_host=target_host)

    async def get_working_proxy(self, target_host: str = "objects.githubusercontent.com") -> Optional[str]:
        """Осуществляет трехуровневый поиск рабочего прокси/VPN-соединения."""
        # Tier 0: Дисковый кэш ранее работавших нод
        cached_nodes = self._load_cached_nodes_from_disk(exclude_env=True)
        if cached_nodes:
            logger.info("[Failover] Checking %d local cached VPN nodes...", len(cached_nodes))
            proxy = await self._test_and_activate_nodes(cached_nodes, tier_name="Disk Cache", target_host=target_host)
            if proxy:
                logger.info("[Failover] Successfully activated cached VPN node: %s", proxy)
                return proxy

        # Tier 1: Черные списки (Hysteria 2 / Trojan / VLESS Reality / Shadowsocks)
        logger.info("[Failover] Checking Tier 1: Black lists (Hysteria 2 / Trojan / VLESS Reality)...")
        proxy = await self._check_vpn_sources(BLACK_LIST_SOURCES, tier_name="Tier 1", target_host=target_host)
        if proxy:
            return proxy

        # Tier 2: Белые списки (VLESS Reality CIDR/SNI)
        logger.info("[Failover] Checking Tier 2: White lists (VLESS Reality)...")
        proxy = await self._check_vpn_sources(WHITE_LIST_SOURCES, tier_name="Tier 2", target_host=target_host)
        if proxy:
            return proxy

        # Tier 3: Открытые SOCKS5 прокси
        logger.info("[Failover] Checking Tier 3: SOCKS5 Fallback proxies...")
        proxy = await self._check_socks5_sources(SOCKS5_FALLBACK_SOURCES)
        if proxy:
            return proxy

        return None

    async def start_tunnel_for_node(self, node_uri: str, port: int = 10818, target_host: str = "objects.githubusercontent.com") -> bool:
        """Запускает туннель для конкретной VPN ссылки через ядро sentinel-core."""
        parsed = parse_vpn_uri(node_uri)
        if parsed:
            try:
                cfg_json = sentinel_core_bridge.build_failover_client_config(
                    [parsed],
                    socks_port=port,
                    http_port=port+1,
                    health_url=f"https://{target_host}" if target_host else "https://objects.githubusercontent.com"
                )
                if cfg_json:
                    ok = await self.start_or_reload_singbox_tunnel(cfg_json, port=port, target_host=target_host)
                    if ok:
                        self._save_working_nodes_to_disk([node_uri])
                        return True
            except Exception as e:
                logger.error("start_tunnel_for_node error: %s", e)
        return False

    async def test_proxy_alive(self, proxy_url: str, target_host: str = "objects.githubusercontent.com", target_port: int = 443, timeout: float = 4.0) -> Tuple[bool, float]:
        """Проверяет доступность SOCKS5/HTTP прокси через быстрый curl-проб с фолбэком на RFC 1928 сокет."""
        loop = asyncio.get_running_loop()

        def _probe():
            start = time.monotonic()
            # 1. First try curl (robust TLS 1.3 + ALPN + SOCKS5h + SNI implementation)
            if shutil.which("curl"):
                try:
                    p = proxy_url
                    if p.startswith("socks5://"):
                        p = "socks5h://" + p[len("socks5://"):]
                    cmd = [
                        "curl", "-sI", "-k",
                        "--connect-timeout", "3",
                        "--max-time", str(int(timeout)),
                        "-x", p,
                        f"https://{target_host}",
                    ]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1.0)
                    if res.returncode == 0 and ("HTTP/" in res.stdout or "HTTP" in res.stdout):
                        lat = (time.monotonic() - start) * 1000.0
                        return True, lat
                except Exception:
                    pass

            # 2. Raw socket fallback
            try:
                parsed = urllib.parse.urlparse(proxy_url)
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port or 1080
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, port))
                if proxy_url.startswith("socks5://") or proxy_url.startswith("socks5h://"):
                    # SOCKS5 greeting
                    s.sendall(b"\x05\x01\x00")
                    resp = s.recv(2)
                    if resp != b"\x05\x00":
                        s.close()
                        return False, 999999.0

                    # SOCKS5 CONNECT to target host (FQDN type 0x03)
                    host_bytes = target_host.encode("utf-8")
                    port_bytes = (target_port).to_bytes(2, byteorder="big")
                    req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + port_bytes
                    s.sendall(req)

                    rep_hdr = s.recv(4)
                    if len(rep_hdr) < 4 or rep_hdr[1] != 0:
                        s.close()
                        return False, 999999.0

                    atyp = rep_hdr[3]
                    if atyp == 1:
                        bnd = b""
                        while len(bnd) < 6:
                            chunk = s.recv(6 - len(bnd))
                            if not chunk:
                                break
                            bnd += chunk
                    elif atyp == 3:
                        l_byte = s.recv(1)
                        if l_byte:
                            target_len = l_byte[0] + 2
                            bnd = b""
                            while len(bnd) < target_len:
                                chunk = s.recv(target_len - len(bnd))
                                if not chunk:
                                    break
                                bnd += chunk
                    elif atyp == 4:
                        bnd = b""
                        while len(bnd) < 18:
                            chunk = s.recv(18 - len(bnd))
                            if not chunk:
                                break
                            bnd += chunk

                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    tls_sock = ctx.wrap_socket(s, server_hostname=target_host)
                    tls_sock.settimeout(timeout)
                    http_probe = f"HEAD / HTTP/1.1\r\nHost: {target_host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
                    tls_sock.sendall(http_probe.encode("utf-8"))
                    http_resp = tls_sock.recv(64)
                    tls_sock.close()
                    if http_resp and (b"HTTP/" in http_resp or b"HTTP" in http_resp):
                        lat = (time.monotonic() - start) * 1000.0
                        return True, lat
                    return False, 999999.0
                elif proxy_url.startswith("socks4://"):
                    s.close()
                    lat = (time.monotonic() - start) * 1000.0
                    return True, lat
                else:
                    s.sendall(f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n".encode("utf-8"))
                    resp = s.recv(12)
                    if b"200" in resp or b"HTTP" in resp:
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        tls_sock = ctx.wrap_socket(s, server_hostname=target_host)
                        tls_sock.settimeout(timeout)
                        http_probe = f"HEAD / HTTP/1.1\r\nHost: {target_host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
                        tls_sock.sendall(http_probe.encode("utf-8"))
                        http_resp = tls_sock.recv(16)
                        tls_sock.close()
                        if http_resp and (b"HTTP/" in http_resp or b"HTTP" in http_resp):
                            lat = (time.monotonic() - start) * 1000.0
                            return True, lat
                    s.close()
                    return False, 999999.0
            except Exception as e:
                logger.debug("test_proxy_alive error for %s (%s): %s", proxy_url, target_host, e)
                return False, 999999.0

        return await loop.run_in_executor(None, _probe)

    async def _check_socks5_sources(self, sources: List[str]) -> Optional[str]:
        """Парсит и тестирует открытые SOCKS5 источники (Tier 3)."""
        return await self._check_vpn_sources(sources, tier_name="Tier 3")


# Singleton instance
proxy_rotator = SocksProxyRotator()


if __name__ == "__main__":
    import argparse
    import ssl

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Sentinel Proxy Rotator")
    parser.add_argument("--find-and-start", action="store_true", help="Find working VPN node and start local tunnel on port 10818")
    parser.add_argument("--node", type=str, default="", help="Specific VPN node URI to start tunnel for")
    parser.add_argument("--port", type=int, default=10818, help="Local SOCKS5 port (default: 10818)")
    parser.add_argument("--target-host", type=str, default="objects.githubusercontent.com", help="Target domain for end-to-end connectivity probe")
    args = parser.parse_args()

    async def _cli_main():
        if args.node:
            print(f"[Rotator] Starting local tunnel for node on port {args.port}...", file=sys.stderr, flush=True)
            ok = await proxy_rotator.start_tunnel_for_node(args.node, port=args.port, target_host=args.target_host)
            if ok:
                print(f"PROXY_READY:socks5://127.0.0.1:{args.port}", flush=True)
                while True:
                    await asyncio.sleep(1)
            else:
                print(f"[Rotator] Failed to start tunnel for node, falling back to rotation...", file=sys.stderr, flush=True)

        if args.find_and_start or args.node:
            print(f"[Rotator] Searching for working VPN node on port {args.port} (target: {args.target_host})...", file=sys.stderr, flush=True)
            proxy = await proxy_rotator.get_working_proxy(target_host=args.target_host)
            if proxy:
                print(f"PROXY_READY:{proxy}", flush=True)
                while True:
                    await asyncio.sleep(1)
            else:
                print(f"[Rotator] No responsive VPN nodes found", file=sys.stderr, flush=True)
                sys.exit(1)

    try:
        asyncio.run(_cli_main())
    except KeyboardInterrupt:
        proxy_rotator.stop_tunnel()
