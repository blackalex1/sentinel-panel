import asyncio
import base64
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional, List, Dict, Any, Tuple

# Ensure panel root directory is in sys.path
_panel_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _panel_root not in sys.path:
    sys.path.insert(0, _panel_root)

logger = logging.getLogger(__name__)

# ТИР 1: Черные списки (Hysteria2, Trojan, VLESS, Shadowsocks)
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


def parse_vpn_uri(uri: str) -> Optional[Dict[str, Any]]:
    """Парсит VPN-ссылку (VLESS, Trojan, Hysteria2, SS) через единое ядро sentinel-core."""
    try:
        from backend import sentinel_core_bridge
        profile = sentinel_core_bridge.parse_proxy_uri(uri)
        if profile and isinstance(profile, dict) and profile.get("protocol"):
            profile["proxyUrl"] = uri
            return profile
    except Exception:
        pass

    # Basic fallback with camelCase field mapping for Go ast.ServerProfile
    try:
        uri = uri.strip()
        if uri.startswith("ss://"):
            raw = uri[5:]
            name = ""
            if "#" in raw:
                raw, name = raw.split("#", 1)
                name = urllib.parse.unquote(name)

            if "@" in raw:
                user_info, host_port = raw.split("@", 1)
            else:
                user_info, host_port = raw, ""

            if not host_port and user_info:
                padded = user_info + "=" * ((4 - len(user_info) % 4) % 4)
                try:
                    decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
                    if "@" in decoded:
                        user_info, host_port = decoded.split("@", 1)
                except Exception:
                    pass

            method, pwd = user_info.split(":", 1) if ":" in user_info else ("chacha20-ietf-poly1305", user_info)
            if "?" in host_port:
                host_port, _ = host_port.split("?", 1)
            host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "443")
            return {
                "protocol": "shadowsocks",
                "address": host.strip("[]"),
                "port": int(port),
                "password": pwd,
                "cipher": method,
                "name": name or f"ss-{host}:{port}",
                "proxyUrl": uri
            }

        for proto in ("vless", "trojan", "hysteria2", "hy2"):
            if uri.startswith(f"{proto}://"):
                parsed = urllib.parse.urlparse(uri)
                name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"{proto}-{parsed.hostname}:{parsed.port}"
                params = dict(urllib.parse.parse_qsl(parsed.query))
                
                res = {
                    "protocol": "hysteria2" if proto == "hy2" else proto,
                    "address": parsed.hostname or "",
                    "port": int(parsed.port or (443 if proto != "shadowsocks" else 8388)),
                    "name": name,
                    "proxyUrl": uri
                }

                if proto == "vless":
                    res["uuid"] = parsed.username or ""
                    res["security"] = params.get("security", "none")
                    res["sni"] = params.get("sni", params.get("serverName", ""))
                    res["flow"] = params.get("flow", "")
                    res["fingerprint"] = params.get("fp", "chrome")
                    res["publicKey"] = params.get("pbk", "")
                    res["shortId"] = params.get("sid", "")
                elif proto in ("hysteria2", "hy2"):
                    res["password"] = parsed.username or parsed.password or ""
                    res["sni"] = params.get("sni", "")
                elif proto == "trojan":
                    res["password"] = parsed.username or parsed.password or ""
                    res["sni"] = params.get("sni", "")

                return res
    except Exception:
        pass

    return None




def _free_port(port: int):
    """Принудительно освобождает порт, завершая зависшие процессы."""
    if sys.platform != "win32":
        try:
            subprocess.run(["fuser", "-k", "-9", f"{port}/tcp"], capture_output=True, timeout=1.5)
        except Exception:
            pass
        try:
            cmd = f"lsof -t -i :{port} 2>/dev/null | xargs -r kill -9 2>/dev/null || true"
            subprocess.run(["sh", "-c", cmd], capture_output=True, timeout=1.5)
        except Exception:
            pass


class SocksProxyRotator:
    def __init__(self):
        self._singbox_proc: Optional[subprocess.Popen] = None
        self._current_engine: str = ""

    def _ensure_proxy_engine(self) -> tuple[Optional[str], str]:
        """Находит установленный локально sing-box или xray бинарник, либо загружает его при отсутствии."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bin_dir = os.path.join(base_dir, "bin")
        os.makedirs(bin_dir, exist_ok=True)

        is_win = sys.platform == "win32" or os.name == "nt"
        sb_name = "sing-box.exe" if is_win else "sing-box"
        xray_name = "xray.exe" if is_win else "xray"

        sb_path = os.path.join(bin_dir, sb_name)
        if os.path.isfile(sb_path) and os.access(sb_path, os.X_OK):
            return sb_path, "singbox"

        which_sb = shutil.which(sb_name) or shutil.which("sing-box")
        if which_sb:
            return which_sb, "singbox"

        xray_path = os.path.join(bin_dir, xray_name)
        if os.path.isfile(xray_path) and os.access(xray_path, os.X_OK):
            return xray_path, "xray"

        which_xray = shutil.which(xray_name) or shutil.which("xray")
        if which_xray:
            return which_xray, "xray"

        # Try auto-fetching sing-box via fetch_proxy_core.sh
        fetch_script = os.path.join(base_dir, "installation", "fetch_proxy_core.sh")
        if os.path.isfile(fetch_script):
            try:
                subprocess.run(["bash", fetch_script, bin_dir, "--auto"], timeout=20, capture_output=True)
                if os.path.isfile(sb_path) and os.access(sb_path, os.X_OK):
                    return sb_path, "singbox"
            except Exception:
                pass

        return None, ""

    async def start_or_reload_singbox_tunnel(self, config_json: str, port: int = 10818) -> bool:
        """Запускает или перезапускает локальный процесс Sing-box / Xray с клиентским failover-конфигом."""
        self.stop_tunnel()
        _free_port(port)
        _free_port(port + 1)

        bin_path, engine_type = self._ensure_proxy_engine()
        if not bin_path:
            logger.warning("Neither sing-box nor xray binary found in PATH or bin/ directory.")
            return False

        cfg_dir = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(cfg_dir, f"{engine_type}_failover.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(config_json)

        env = os.environ.copy()
        env["ENABLE_DEPRECATED_LEGACY_DNS_SERVERS"] = "true"

        cmd = [bin_path, "run", "-c", cfg_path]
        try:
            extra_kwargs = {}
            if sys.platform != "win32":
                extra_kwargs["preexec_fn"] = os.setsid

            self._singbox_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
                **extra_kwargs
            )
            self._current_engine = engine_type

            for _ in range(6):
                await asyncio.sleep(0.5)
                if self._singbox_proc.poll() is not None:
                    _, stderr = self._singbox_proc.communicate()
                    logger.warning("%s process terminated unexpectedly on startup: %s", engine_type, stderr)
                    self._singbox_proc = None
                    return False

                ok, lat = await self.test_proxy_alive(f"socks5://127.0.0.1:{port}", timeout=2.5)
                if ok:
                    logger.info("Started local %s failover tunnel on port %d (latency: %.1f ms)", engine_type, port, lat)
                    return True

            logger.warning("%s started on port %d but failed health probe.", engine_type, port)
            self.stop_tunnel()
            return False
        except Exception as e:
            logger.exception("Failed to launch %s client process: %s", engine_type, e)
            self.stop_tunnel()
            return False

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

        _free_port(10818)
        _free_port(10819)

    def _get_cache_file_path(self) -> str:
        """Путь к локальному дисковому кэшу рабочих VPN-нод."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_dir = os.path.join(base_dir, "config")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "cached_vpn_nodes.json")

    def _load_cached_nodes_from_disk(self) -> List[str]:
        """Загружает список сохраненных VPN-нод из файла."""
        cache_file = self._get_cache_file_path()
        if not os.path.isfile(cache_file):
            return []
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(u).strip() for u in data if str(u).strip()]
        except Exception:
            pass
        return []

    def _save_working_nodes_to_disk(self, uris: List[str]):
        """Сохраняет рабочие VPN-ноды на диск для мгновенного запуска при следующем обновлении."""
        if not uris:
            return
        cache_file = self._get_cache_file_path()
        try:
            existing = self._load_cached_nodes_from_disk()
            combined = []
            seen = set()
            for u in uris + existing:
                u_clean = u.strip()
                if u_clean and u_clean not in seen:
                    seen.add(u_clean)
                    combined.append(u_clean)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(combined[:50], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    async def _test_and_activate_nodes(self, uris: List[str], tier_name: str = "Tier") -> Optional[str]:
        """Парсит ссылки через Go sentinel-core, проверяет пинг и запускает локальный Sing-box failover мост."""
        if not uris:
            return None

        combined_payload = "\n".join(uris[:40])
        profiles = None
        try:
            from backend import sentinel_core_bridge
            profiles = sentinel_core_bridge.parse_subscription(combined_payload)
        except Exception as e:
            logger.debug("Core parse_subscription exception: %s", e)

        if not profiles:
            profiles = []
            for u in uris[:40]:
                p = parse_vpn_uri(u)
                if p:
                    profiles.append(p)

        if not profiles:
            return None

        # Parallel non-blocking TCP ping
        async def _ping_node(prof: dict) -> dict:
            host = prof.get("address") or ""
            port = prof.get("port") or 443
            if not host:
                return prof
            start = time.monotonic()
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=1.5)
                w.close()
                await w.wait_closed()
                prof["alive"] = True
                prof["latencyMs"] = (time.monotonic() - start) * 1000.0
            except Exception:
                prof["alive"] = False
                prof["latencyMs"] = 999999.0
            return prof

        tasks = [_ping_node(p) for p in profiles[:25]]
        tested = await asyncio.gather(*tasks)
        working = [p for p in tested if p.get("alive") and p.get("latencyMs", 999999) < 2000]

        if not working:
            logger.info("%s: checked %d nodes, none responsive", tier_name, len(profiles[:25]))
            return None

        working.sort(key=lambda x: x.get("latencyMs") or 999999)
        best = working[0]
        logger.info("%s: %d / %d nodes alive. Best: %s (%.1f ms)", tier_name, len(working), len(profiles[:25]), best.get("name") or best.get("address"), best.get("latencyMs", 0))

        client_cfg = None
        try:
            from backend import sentinel_core_bridge
            client_cfg = sentinel_core_bridge.build_failover_client_config(
                working[:10],
                socks_port=10818,
                http_port=10819,
                health_url="https://api.telegram.org"
            )
        except Exception as e:
            logger.error("Core build_failover_client_config exception: %s", e)

        if not client_cfg:
            logger.error("Не удалось скомпилировать Sing-box конфиг через sentinel-core.")
            return None

        ok = await self.start_or_reload_singbox_tunnel(client_cfg, port=10818)
        if ok:
            working_uris = [p["proxyUrl"] for p in working if p.get("proxyUrl")]
            if working_uris:
                self._save_working_nodes_to_disk(working_uris)
            return "socks5://127.0.0.1:10818"

        return None

    async def _fetch_single_source(self, base_url: str) -> List[str]:
        """Скачивает файл подписки через быстрые CDN-зеркала с таймаутом 3.5с."""
        loop = asyncio.get_running_loop()
        mirror_prefixes = [
            "https://ghfast.top/",
            "https://gh-proxy.com/",
            "https://gh.ddlc.top/",
            "",
        ]

        def _fetch_url(target_url: str) -> str:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sentinel/1.0"}
            )
            with urllib.request.urlopen(req, timeout=2.0, context=ctx) as response:
                return response.read().decode("utf-8", errors="ignore")

        for prefix in mirror_prefixes:
            full_url = f"{prefix}{base_url}" if prefix else base_url
            try:
                content = await loop.run_in_executor(None, _fetch_url, full_url)
                if content and len(content) > 10:
                    return [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
            except Exception:
                continue
        return []

    async def _check_vpn_sources(self, sources: List[str], tier_name: str = "Tier") -> Optional[str]:
        """Параллельно скачивает подписки и активирует лучший Sing-box туннель."""
        tasks = [self._fetch_single_source(url) for url in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        uris = []
        for r in results:
            if isinstance(r, list):
                uris.extend(r)

        return await self._test_and_activate_nodes(uris, tier_name=tier_name)

    async def start_tunnel_for_node(self, node_uri: str, port: int = 10818) -> bool:
        """Запускает туннель для конкретной VPN ссылки через ядро sentinel-core."""
        parsed = parse_vpn_uri(node_uri)
        if parsed:
            try:
                from backend import sentinel_core_bridge
                cfg_json = sentinel_core_bridge.build_failover_client_config([parsed], socks_port=port, http_port=port+1)
                if cfg_json:
                    ok = await self.start_or_reload_singbox_tunnel(cfg_json, port=port)
                    if ok:
                        self._save_working_nodes_to_disk([node_uri])
                        return True
            except Exception as e:
                logger.error("start_tunnel_for_node error: %s", e)
        return False

    async def _check_socks5_sources(self) -> Optional[str]:
        """Крайний случай: скрапинг и проверка открытых SOCKS5 списков."""
        loop = asyncio.get_running_loop()
        raw_proxies = []

        def _fetch(url):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    return resp.read().decode('utf-8', errors='ignore')
            except Exception:
                return ""

        for src in SOCKS5_FALLBACK_SOURCES:
            text = await loop.run_in_executor(None, _fetch, src)
            matches = re.findall(r'(\d{1,3}(?:\.\d{1,3}){3}:\d+)', text)
            for m in matches:
                raw_proxies.append(f"socks5://{m}")

        unique_proxies = list(set(raw_proxies))
        if not unique_proxies:
            return None

        tasks = [self.test_proxy_alive(p, timeout=2.0) for p in unique_proxies[:50]]
        results = await asyncio.gather(*tasks)

        working = []
        for p, (ok, lat) in zip(unique_proxies[:50], results):
            if ok:
                working.append({"proxyUrl": p, "latencyMs": lat})

        if not working:
            return None

        working.sort(key=lambda x: x["latencyMs"])
        best_proxy = working[0]["proxyUrl"]
        logger.info("Tier 3 SOCKS5: found %d working proxies, best: %s (%.1f ms)", len(working), best_proxy, working[0]["latencyMs"])
        return best_proxy

    async def test_proxy_alive(self, proxy_url: str, timeout: float = 3.0) -> Tuple[bool, float]:
        """Проверяет доступность SOCKS5/HTTP прокси сокетным рукопожатием и сквозным соединением (E2E)."""
        loop = asyncio.get_running_loop()

        def _socket_probe():
            start = time.monotonic()
            try:
                parsed = urllib.parse.urlparse(proxy_url)
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port or 1080
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((host, port))
                if proxy_url.startswith("socks5://") or proxy_url.startswith("socks5h://"):
                    # 1. SOCKS5 greeting: VER=5, NMETHODS=1, NO_AUTH=0
                    s.sendall(b"\x05\x01\x00")
                    resp = s.recv(2)
                    if resp != b"\x05\x00":
                        s.close()
                        return False, 999999.0

                    # 2. SOCKS5 CONNECT to 1.1.1.1:443 (HTTPS) to verify real internet connectivity through VPN!
                    ip_bytes = socket.inet_aton("1.1.1.1")
                    port_bytes = (443).to_bytes(2, byteorder="big")
                    req = b"\x05\x01\x00\x01" + ip_bytes + port_bytes
                    s.sendall(req)
                    connect_resp = s.recv(10)
                    s.close()
                    if len(connect_resp) >= 2 and connect_resp[1] == 0:
                        lat = (time.monotonic() - start) * 1000.0
                        return True, lat
                    return False, 999999.0
                elif proxy_url.startswith("socks4://"):
                    s.close()
                    lat = (time.monotonic() - start) * 1000.0
                    return True, lat
                else:
                    # HTTP proxy probe
                    s.sendall(b"CONNECT 1.1.1.1:443 HTTP/1.1\r\nHost: 1.1.1.1:443\r\n\r\n")
                    resp = s.recv(12)
                    s.close()
                    lat = (time.monotonic() - start) * 1000.0
                    return b"200" in resp or b"HTTP" in resp, lat
            except Exception:
                return False, 999999.0

        return await loop.run_in_executor(None, _socket_probe)

    async def get_working_proxy(self) -> Optional[str]:
        """4-Уровневый каскадный поиск рабочего соединения."""
        # ТИР 0: Дисковый кэш
        cached = self._load_cached_nodes_from_disk()
        if cached:
            logger.info("[Failover] Checking %d local cached VPN nodes...", len(cached))
            cached_res = await self._test_and_activate_nodes(cached, tier_name="Disk Cache")
            if cached_res:
                logger.info("[Failover] Successfully activated cached VPN node: %s", cached_res)
                return cached_res

        # ТИР 1: Черные списки
        logger.info("[Failover] Checking Tier 1: Black lists (Hysteria 2 / Trojan / VLESS Reality)...")
        t1_proxy = await self._check_vpn_sources(BLACK_LIST_SOURCES, tier_name="Tier 1")
        if t1_proxy:
            return t1_proxy

        # ТИР 2: Белые списки
        logger.info("[Failover] Checking Tier 2: White lists (VLESS Reality)...")
        t2_proxy = await self._check_vpn_sources(WHITE_LIST_SOURCES, tier_name="Tier 2")
        if t2_proxy:
            return t2_proxy

        # ТИР 3: SOCKS5 списки
        logger.info("[Failover] Checking Tier 3: Public SOCKS5 proxy lists...")
        t3_proxy = await self._check_socks5_sources()
        if t3_proxy:
            return t3_proxy

        return None


proxy_rotator = SocksProxyRotator()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sentinel Panel Proxy Rotator CLI Bridge")
    parser.add_argument("--find-and-start", action="store_true", help="Find best working VPN node and start local Sing-box tunnel")
    parser.add_argument("--node", type=str, default="", help="Specific VPN node URI (ss://, vless://, etc.) to start tunnel for")
    parser.add_argument("--port", type=int, default=10818, help="Local SOCKS5 port to bind (default 10818)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    async def _cli_main():
        if args.node:
            print(f"[Rotator] Starting local tunnel for node on port {args.port}...", file=sys.stderr, flush=True)
            ok = await proxy_rotator.start_tunnel_for_node(args.node, port=args.port)
            if ok:
                print(f"PROXY_READY:socks5://127.0.0.1:{args.port}", flush=True)
                while True:
                    await asyncio.sleep(1)
            else:
                print(f"[Rotator] Failed to start tunnel for node", file=sys.stderr, flush=True)
                sys.exit(1)

        if args.find_and_start:
            print(f"[Rotator] Searching for working VPN node on port {args.port}...", file=sys.stderr, flush=True)
            proxy = await proxy_rotator.get_working_proxy()
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
