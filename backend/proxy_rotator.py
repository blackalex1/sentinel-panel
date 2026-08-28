import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from typing import Optional, List, Dict, Any

# Ensure panel root directory is always present in sys.path for direct CLI execution
_panel_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _panel_root not in sys.path:
    sys.path.insert(0, _panel_root)

import aiohttp
from aiohttp_socks import ProxyConnector

from backend import sentinel_core_bridge

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


class SocksProxyRotator:
    def __init__(self):
        self.cached_proxies = []
        self.last_scrape_time = 0
        self._singbox_proc: Optional[subprocess.Popen] = None
        self._current_engine: str = ""

    def _find_proxy_engine_bin(self) -> tuple[Optional[str], str]:
        """Находит установленный локально sing-box или xray бинарник."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bin_dir = os.path.join(base_dir, "bin")

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

        return None, ""

    async def start_or_reload_singbox_tunnel(self, config_json: str, port: int = 10818) -> bool:
        """Запускает или перезапускает локальный процесс Sing-box / Xray с клиентским failover-конфигом."""
        bin_path, engine_type = self._find_proxy_engine_bin()
        if not bin_path:
            logger.warning("Neither sing-box nor xray binary found in PATH or bin/ directory.")
            return False

        if self._singbox_proc:
            try:
                self._singbox_proc.terminate()
                self._singbox_proc.wait(timeout=2)
            except Exception:
                try:
                    self._singbox_proc.kill()
                except Exception:
                    pass
            self._singbox_proc = None

        cfg_dir = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(cfg_dir, f"{engine_type}_failover.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(config_json)

        cmd = [bin_path, "run", "-c", cfg_path] if engine_type == "singbox" else [bin_path, "run", "-c", cfg_path]
        try:
            self._singbox_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )
            self._current_engine = engine_type

            for _ in range(12):
                await asyncio.sleep(0.5)
                if self._singbox_proc.poll() is not None:
                    _, stderr = self._singbox_proc.communicate()
                    logger.warning("%s process terminated unexpectedly on startup: %s", engine_type, stderr)
                    self._singbox_proc = None
                    return False

                ok, lat = await self.test_proxy_alive(f"socks5://127.0.0.1:{port}", timeout=3.0)
                if ok:
                    logger.info("Started local %s failover tunnel on port %d (latency: %.1f ms)", engine_type, port, lat)
                    return True

            logger.warning("%s started on port %d but failed health probe.", engine_type, port)
            return False
        except Exception as e:
            logger.exception("Failed to launch %s client process: %s", engine_type, e)
            return False

    def stop_tunnel(self):
        """Останавливает запущенный фоновый процесс прокси."""
        if self._singbox_proc:
            try:
                self._singbox_proc.terminate()
                self._singbox_proc.wait(timeout=2)
            except Exception:
                try:
                    self._singbox_proc.kill()
                except Exception:
                    pass
            self._singbox_proc = None

    def _get_cache_file_path(self) -> str:
        """Возвращает путь к локальному файлу дискового кэша рабочих VPN-нод."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_dir = os.path.join(base_dir, "config")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "cached_vpn_nodes.json")

    def _load_cached_nodes_from_disk(self) -> List[str]:
        """Загружает список сохраненных VPN-нод из локального дискового файла."""
        cache_file = self._get_cache_file_path()
        if not os.path.isfile(cache_file):
            return []
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(u).strip() for u in data if str(u).strip()]
        except Exception as e:
            logger.debug("Failed to read cached VPN nodes from disk: %s", e)
        return []

    def _save_working_nodes_to_disk(self, uris: List[str]):
        """Сохраняет проверенные рабочие VPN-ноды в локальный дисковый файл для мгновенного старта."""
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
        except Exception as e:
            logger.debug("Failed to save working VPN nodes to disk: %s", e)

    async def _test_and_activate_nodes(self, uris: List[str], tier_name: str = "Tier") -> Optional[str]:
        """Парсит ссылки через Go sentinel-core, проверяет пинг и активирует лучший Sing-box туннель."""
        if not uris:
            return None

        combined_payload = "\n".join(uris)
        profiles = sentinel_core_bridge.parse_subscription(combined_payload)
        if not profiles:
            logger.warning("%s: failed to parse any VPN profiles from provided nodes", tier_name)
            return None

        tested = sentinel_core_bridge.test_profiles(profiles, ping_count=2, timeout_ms=3000)
        if not tested:
            logger.warning("%s: Sentinel core test-profiles returned no result, using raw profiles", tier_name)
            tested = profiles

        working = [p for p in tested if p.get("alive") or p.get("latencyMs", 0) > 0]
        if not working:
            logger.info("%s: checked %d nodes, none responsive", tier_name, len(uris))
            return None

        working.sort(key=lambda x: x.get("latencyMs") or 999999)
        best = working[0]
        logger.info("%s: %d / %d nodes alive. Best: %s (%.1f ms)", tier_name, len(working), len(uris), best.get("name") or best.get("proxyUrl"), best.get("latencyMs", 0))

        client_cfg = sentinel_core_bridge.build_failover_client_config(
            working[:10],
            socks_port=10818,
            http_port=10819,
            health_url="https://api.telegram.org"
        )
        if not client_cfg:
            logger.warning("%s: Failed to build client failover config via Go Sentinel-Core", tier_name)
            return None

        ok = await self.start_or_reload_singbox_tunnel(client_cfg, port=10818)
        if ok:
            working_uris = [p["proxyUrl"] for p in working if p.get("proxyUrl")]
            if working_uris:
                self._save_working_nodes_to_disk(working_uris)
            return "socks5://127.0.0.1:10818"

        return None

    async def _check_vpn_sources(self, sources: List[str], tier_name: str = "Tier") -> Optional[str]:
        """Скрапит подписки из GitHub, фильтрует рабочие ноды и настраивает Sing-box failover мост."""
        loop = asyncio.get_running_loop()
        uris = []
        mirror_prefixes = [
            "",
            "https://ghproxy.net/",
            "https://gh-proxy.com/",
            "https://mirror.ghproxy.com/",
        ]

        def _fetch_url(target_url: str) -> str:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                return response.read().decode("utf-8", errors="ignore")

        for base_url in sources:
            fetched = False
            for prefix in mirror_prefixes:
                full_url = f"{prefix}{base_url}" if prefix else base_url
                try:
                    content = await loop.run_in_executor(None, _fetch_url, full_url)
                    if content and len(content) > 10:
                        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
                        uris.extend(lines)
                        fetched = True
                        break
                except Exception:
                    continue

        return await self._test_and_activate_nodes(uris, tier_name=tier_name)

    async def start_tunnel_for_node(self, node_uri: str, port: int = 10818) -> bool:
        """Запускает локальный Sing-box / Xray / pproxy туннель для конкретной VPN ссылки."""
        try:
            parsed = sentinel_core_bridge.parse_subscription(node_uri)
            if parsed:
                cfg_json = sentinel_core_bridge.build_failover_client_config(parsed, socks_port=port, http_port=port+1)
                if cfg_json:
                    ok = await self.start_or_reload_singbox_tunnel(cfg_json, port=port)
                    if ok:
                        self._save_working_nodes_to_disk([node_uri])
                        return True
        except Exception as e:
            logger.debug("Sing-box tunnel start attempt failed: %s", e)

        if node_uri.startswith("ss://"):
            try:
                import pproxy
                import urllib.parse
                parsed_url = urllib.parse.urlparse(node_uri)
                netloc = parsed_url.netloc or parsed_url.path
                if '@' in netloc:
                    creds, host_port = netloc.rsplit('@', 1)
                else:
                    creds, host_port = netloc, ''

                if creds and ':' not in creds:
                    creds = creds.strip()
                    missing_padding = len(creds) % 4
                    if missing_padding:
                        creds += '=' * (4 - missing_padding)

                cleaned_ss_url = f"ss://{creds}@{host_port}"
                server = pproxy.Server(f'socks5://127.0.0.1:{port}')
                remote = pproxy.Connection(cleaned_ss_url)
                await server.start_server({'rserver': [remote]})
                ok, lat = await self.test_proxy_alive(f"socks5://127.0.0.1:{port}", timeout=4.0)
                if ok:
                    logger.info("Started pproxy Shadowsocks tunnel on port %d (latency: %.1f ms)", port, lat)
                    self._save_working_nodes_to_disk([node_uri])
                    return True
            except Exception as e:
                logger.debug("Failed to start pproxy fallback: %s", e)

        return False

    async def _check_socks5_sources(self) -> Optional[str]:
        """Крайний случай: скрапинг и проверка открытых SOCKS5 списков."""
        loop = asyncio.get_running_loop()
        raw_proxies = []

        def _fetch(url):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
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

        tasks = [self.test_proxy_alive(p, timeout=2.5) for p in unique_proxies[:60]]
        results = await asyncio.gather(*tasks)

        working = []
        for p, (ok, lat) in zip(unique_proxies[:60], results):
            if ok:
                working.append({"proxyUrl": p, "latencyMs": lat})

        if not working:
            return None

        working.sort(key=lambda x: x["latencyMs"])
        best_proxy = working[0]["proxyUrl"]
        logger.info("Tier 3 SOCKS5: found %d working proxies, best: %s (%.1f ms)", len(working), best_proxy, working[0]["latencyMs"])
        return best_proxy

    async def test_proxy_alive(self, proxy_url: str, timeout: float = 3.5) -> tuple[bool, float]:
        """Проверяет доступность прокси с замером реального пинга."""
        start = time.monotonic()
        try:
            connector = ProxyConnector.from_url(proxy_url)
            client_timeout = aiohttp.ClientTimeout(total=timeout, connect=2.0)
            async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
                async with session.get("https://api.telegram.org", ssl=False) as resp:
                    latency = (time.monotonic() - start) * 1000.0
                    return resp.status in (200, 302, 400, 401, 404), latency
        except Exception:
            return False, 999999.0

    async def refresh_disk_cache(self) -> int:
        """Фоновый метод: опрашивает GitHub источники, проверяет ноды и обновляет локальный дисковый кэш."""
        loop = asyncio.get_running_loop()
        all_sources = BLACK_LIST_SOURCES + WHITE_LIST_SOURCES
        mirror_prefixes = ["", "https://ghproxy.net/", "https://gh-proxy.com/", "https://mirror.ghproxy.com/"]

        def _fetch_url(target_url: str) -> str:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                return response.read().decode("utf-8", errors="ignore")

        all_uris = []
        for base_url in all_sources:
            for prefix in mirror_prefixes:
                full_url = f"{prefix}{base_url}" if prefix else base_url
                try:
                    content = await loop.run_in_executor(None, _fetch_url, full_url)
                    if content and len(content) > 10:
                        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
                        all_uris.extend(lines)
                        break
                except Exception:
                    continue

        unique_uris = list(set(all_uris))
        if not unique_uris:
            return 0

        combined_payload = "\n".join(unique_uris[:120])
        profiles = sentinel_core_bridge.parse_subscription(combined_payload)
        if not profiles:
            return 0

        tested = sentinel_core_bridge.test_profiles(profiles, ping_count=2, timeout_ms=3000)
        if not tested:
            return 0

        working = [p for p in tested if p.get("alive") or p.get("latencyMs", 0) > 0]
        if not working:
            return 0

        working.sort(key=lambda x: x.get("latencyMs") or 999999)
        alive_uris = [p["proxyUrl"] for p in working if p.get("proxyUrl")]
        if alive_uris:
            self._save_working_nodes_to_disk(alive_uris)
            logger.info("Proxy cache auto-refresh completed: %d / %d alive nodes saved to local disk cache (best: %.1f ms)", len(alive_uris), len(unique_uris), working[0].get("latencyMs", 0))
            return len(alive_uris)

        return 0

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
    parser.add_argument("--refresh-cache", action="store_true", help="Refresh local disk cache of VPN nodes")
    parser.add_argument("--port", type=int, default=10818, help="Local SOCKS5 port to bind (default 10818)")
    args = parser.parse_args()

    async def _cli_main():
        if args.refresh_cache:
            count = await proxy_rotator.refresh_disk_cache()
            print(f"CACHE_REFRESHED:{count}")
            return

        if args.node:
            ok = await proxy_rotator.start_tunnel_for_node(args.node, port=args.port)
            if ok:
                print(f"PROXY_READY:socks5://127.0.0.1:{args.port}", flush=True)
                while True:
                    await asyncio.sleep(1)
            else:
                sys.exit(1)

        if args.find_and_start:
            proxy = await proxy_rotator.get_working_proxy()
            if proxy:
                print(f"PROXY_READY:{proxy}", flush=True)
                while True:
                    await asyncio.sleep(1)
            else:
                sys.exit(1)

    try:
        asyncio.run(_cli_main())
    except KeyboardInterrupt:
        proxy_rotator.stop_tunnel()
