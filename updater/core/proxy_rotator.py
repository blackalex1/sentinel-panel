"""Universal VPN Tunnel Rotator for Sentinel Updater.

Delegates 100% of proxy parsing, batch checking, and Sing-box configuration
generation to the native Go Sentinel-Core engine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    from .sentinel_core_bridge import (
        batch_check_proxies,
        build_failover_client_config,
        parse_proxy_uri,
        parse_subscription,
    )
except ImportError:
    from sentinel_core_bridge import (
        batch_check_proxies,
        build_failover_client_config,
        parse_proxy_uri,
        parse_subscription,
    )

_core_dir = os.path.dirname(os.path.abspath(__file__))
_updater_root = os.path.dirname(_core_dir)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ProxyRotator")

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

HEALTH_CHECK_URL = "http://cp.cloudflare.com/generate_204"


def _free_port(port: int) -> None:
    """Освобождает указанный локальный порт."""
    if sys.platform == "win32":
        return
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class SocksProxyRotator:
    """Orchestrates Sing-box/Xray processes using configurations compiled by Sentinel-Core."""

    def __init__(self) -> None:
        self._singbox_proc: Optional[subprocess.Popen] = None
        self._current_engine: str = "singbox"

    def _find_proxy_engine_bin(self) -> Tuple[Optional[str], str]:
        """Ищет бинарник sing-box или xray на сервере."""
        candidates = [
            os.path.join(os.getcwd(), "bot", "bin", "sing-box"),
            os.path.join(os.getcwd(), "bin", "sing-box"),
            os.path.join(_updater_root, "bot", "bin", "sing-box"),
            os.path.join(_updater_root, "bin", "sing-box"),
        ]
        for c in candidates:
            if c and os.path.isfile(c) and os.access(c, os.X_OK):
                return c, "singbox"

        xray_candidates = [
            os.path.join(os.getcwd(), "bot", "bin", "xray"),
            os.path.join(os.getcwd(), "bin", "xray"),
            os.path.join(_updater_root, "bot", "bin", "xray"),
            os.path.join(_updater_root, "bin", "xray"),
        ]
        for c in xray_candidates:
            if c and os.path.isfile(c) and os.access(c, os.X_OK):
                return c, "xray"

        return None, ""

    def stop_tunnel(self) -> None:
        """Останавливает фоновый процесс прокси."""
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
                subprocess.run(["pkill", "-9", "-f", "_failover_"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["pkill", "-9", "-f", "singbox_failover"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["pkill", "-9", "-f", "xray_failover"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        _free_port(10818)
        _free_port(10819)

    async def start_or_reload_singbox_tunnel(
        self,
        config_obj: Dict[str, Any] | str,
        port: int = 10818,
        health_check_url: str = HEALTH_CHECK_URL,
    ) -> bool:
        """Запускает клиентский процесс Sing-box с конфигом от Sentinel-Core."""
        self.stop_tunnel()
        _free_port(port)
        _free_port(port + 1)

        engine_bin, engine_type = self._find_proxy_engine_bin()
        if not engine_bin:
            logger.error("Binary sing-box/xray not found in PATH or project bin/")
            return False

        tmp_cfg = f"/tmp/{engine_type}_failover_{os.getpid()}.json"
        try:
            if isinstance(config_obj, dict) and "configJson" in config_obj:
                cfg_text = config_obj["configJson"]
            elif isinstance(config_obj, str):
                cfg_text = config_obj
            else:
                cfg_text = json.dumps(config_obj, indent=2)

            with open(tmp_cfg, "w", encoding="utf-8") as f:
                f.write(cfg_text)

            cmd = [engine_bin, "run", "-c", tmp_cfg] if engine_type == "singbox" else [engine_bin, "run", "-config", tmp_cfg]

            extra_kwargs = {}
            if sys.platform != "win32":
                extra_kwargs["preexec_fn"] = os.setsid

            self._singbox_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **extra_kwargs
            )
            self._current_engine = engine_type

            await asyncio.sleep(1.0)
            health_url = health_check_url or HEALTH_CHECK_URL

            for attempt in range(1, 5):
                if self._singbox_proc.poll() is not None:
                    return False

                ok, lat = await self.test_proxy_alive(f"socks5://127.0.0.1:{port}", health_check_url=health_url, timeout=3.5)
                if ok:
                    return True

                await asyncio.sleep(0.4)

            self.stop_tunnel()
            return False
        except Exception as e:
            logger.exception("Failed to launch %s: %s", engine_type, e)
            self.stop_tunnel()
            return False

    async def test_proxy_alive(
        self,
        proxy_url: str,
        health_check_url: str = HEALTH_CHECK_URL,
        timeout: float = 3.0,
        verbose: bool = False,
        **kwargs
    ) -> Tuple[bool, float]:
        """Проверяет доступность прокси через curl к health-check эндпоинту."""
        loop = asyncio.get_running_loop()

        def _probe():
            start = time.monotonic()
            if shutil.which("curl"):
                try:
                    p = proxy_url
                    if p.startswith("socks5://"):
                        p = "socks5h://" + p[len("socks5://"):]
                    cmd = [
                        "curl", "-sI", "-k",
                        "--connect-timeout", "2",
                        "--max-time", str(int(timeout)),
                        "-x", p,
                        health_check_url,
                    ]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 1.0)
                    if res.returncode == 0 and ("HTTP/" in res.stdout or "204" in res.stdout or "200" in res.stdout or "30" in res.stdout):
                        lat = (time.monotonic() - start) * 1000.0
                        return True, lat
                except Exception:
                    pass
            return False, 999999.0

        return await loop.run_in_executor(None, _probe)

    async def start_tunnel_for_node(
        self,
        node_uri: str,
        port: int = 10818,
        target_host: str = "objects.githubusercontent.com"
    ) -> bool:
        """Парсит URI и генерирует конфиг через ядро Sentinel-Core."""
        profile = parse_proxy_uri(node_uri)
        if not profile:
            logger.error("Sentinel-Core failed to parse proxy URI: %s", node_uri[:30])
            return False

        # Build client configuration directly via Sentinel-Core builder
        config_obj = build_failover_client_config(
            profiles=[profile],
            target_core="singbox",
            socks_port=port,
            http_port=port + 1,
            health_url=HEALTH_CHECK_URL,
        )
        if not config_obj:
            logger.error("Sentinel-Core failed to build client configuration for node.")
            return False

        return await self.start_or_reload_singbox_tunnel(config_obj, port=port, health_check_url=HEALTH_CHECK_URL)

    async def _fetch_single_source(self, base_url: str) -> str:
        """Скачивает файл подписки, параллельно опрашивая все CDN-зеркала и возвращая самый быстрый ответ."""
        loop = asyncio.get_running_loop()
        prefixes = ["https://gh-proxy.com/", "https://ghfast.top/", "https://gh.ddlc.top/"]

        def _fetch_from_mirror(mirror_url: str) -> str:
            if shutil.which("curl"):
                cmd = ["curl", "-fsSL", "-k", "--connect-timeout", "2", "--max-time", "3", mirror_url]
                try:
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3.5)
                    if res.returncode == 0 and res.stdout and len(res.stdout) > 20:
                        return res.stdout.decode("utf-8", errors="ignore")
                except Exception:
                    pass

            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(mirror_url, headers={"User-Agent": "Mozilla/5.0 Sentinel/1.0"})
                with urllib.request.urlopen(req, timeout=2.0, context=ctx) as resp:
                    data = resp.read().decode("utf-8", errors="ignore")
                    if data and len(data) > 20:
                        return data
            except Exception:
                pass
            return ""

        async def _async_probe(pref: str) -> str:
            return await loop.run_in_executor(None, _fetch_from_mirror, f"{pref}{base_url}")

        tasks = [_async_probe(p) for p in prefixes]
        for coro in asyncio.as_completed(tasks):
            try:
                content = await coro
                if content and len(content) > 20:
                    return content
            except Exception:
                pass

        return ""

    async def _test_and_activate_sources(
        self,
        raw_subscriptions: List[str],
        tier_name: str = "Tier",
        target_host: str = "cp.cloudflare.com"
    ) -> Optional[str]:
        """Парсит подписки, проверяет ссылки и строит failover-конфиг полностью через Go Sentinel-Core."""
        candidate_uris: List[str] = []
        for raw_content in raw_subscriptions:
            if raw_content:
                for line in raw_content.splitlines():
                    l = line.strip()
                    if l and not l.startswith("#") and not l.startswith("//"):
                        if l.startswith(("vless://", "ss://", "trojan://", "hy2://", "hysteria2://", "vmess://", "tuic://")):
                            candidate_uris.append(l)

        if not candidate_uris:
            return None

        # Take up to 50 candidate URIs for batch verification
        test_uris = candidate_uris[:50]
        logger.info("[%s] Sentinel-Core проверяет %d нод через нативный движок (concurrency=32)...", tier_name, len(test_uris))

        # Check proxies via Go Core with aggressive 1.8s timeout
        checked_results = batch_check_proxies(
            proxies=test_uris,
            target_host=target_host,
            target_port=443,
            use_tls=True,
            timeout_ms=1800,
            concurrency=32,
        )

        alive_results = [r for r in checked_results if r.get("success")]
        if not alive_results:
            logger.info("[%s] 0 / %d нод ответили на рукопожатие ядра", tier_name, len(test_uris))
            return None

        alive_results.sort(key=lambda x: x.get("latencyMs", 999999))
        best = alive_results[0]
        logger.info(
            "[%s] Найдено %d живых нод. Лучшая: %s (%s, %.1f ms)",
            tier_name, len(alive_results), best.get("name") or "Node", best.get("protocol"), best.get("latencyMs", 0)
        )

        alive_profiles = []
        for r in alive_results[:8]:
            p = parse_proxy_uri(r.get("proxyUrl", ""))
            if p:
                alive_profiles.append(p)

        if not alive_profiles:
            return None

        logger.info("[%s] Sentinel-Core генерирует Failover конфигурацию (активно нод: %d)...", tier_name, len(alive_profiles))

        config_obj = build_failover_client_config(
            profiles=alive_profiles,
            target_core="singbox",
            socks_port=10818,
            http_port=10819,
            health_url=HEALTH_CHECK_URL,
        )
        if not config_obj:
            return None

        ok = await self.start_or_reload_singbox_tunnel(config_obj, port=10818, health_check_url=HEALTH_CHECK_URL)
        if ok:
            logger.info("[%s] VPN-туннель успешно поднят и верифицирован через Sentinel-Core", tier_name)
            return "socks5://127.0.0.1:10818"

        return None

    async def get_working_proxy(self, target_host: str = "cp.cloudflare.com") -> Optional[str]:
        """Многопоточный поиск рабочего VPN-соединения через Sentinel-Core."""
        logger.info("[Failover] Проверка Tier 1: Черные списки (Hysteria 2 / Trojan / VLESS Reality)...")
        tasks = [self._fetch_single_source(url) for url in BLACK_LIST_SOURCES]
        t1_contents = await asyncio.gather(*tasks, return_exceptions=True)
        valid_t1 = [c for c in t1_contents if isinstance(c, str) and len(c) > 20]

        proxy = await self._test_and_activate_sources(valid_t1, tier_name="Tier 1", target_host=target_host)
        if proxy:
            return proxy

        logger.info("[Failover] Проверка Tier 2: Белые списки (VLESS Reality)...")
        tasks = [self._fetch_single_source(url) for url in WHITE_LIST_SOURCES]
        t2_contents = await asyncio.gather(*tasks, return_exceptions=True)
        valid_t2 = [c for c in t2_contents if isinstance(c, str) and len(c) > 20]

        proxy = await self._test_and_activate_sources(valid_t2, tier_name="Tier 2", target_host=target_host)
        if proxy:
            return proxy

        return None


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sentinel-Core VPN Rotator")
    parser.add_argument("--node", type=str, help="Specific VPN URI to connect")
    parser.add_argument("--find-and-start", action="store_true", help="Scrape and start best node")
    parser.add_argument("--port", type=int, default=10818, help="Local SOCKS5 port")
    parser.add_argument("--target-host", type=str, default="cp.cloudflare.com", help="Target host for health checks")
    args = parser.parse_args()

    rotator = SocksProxyRotator()

    def _sig_handler(sig, frame):
        rotator.stop_tunnel()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    if args.node:
        ok = await rotator.start_tunnel_for_node(args.node, port=args.port, target_host=args.target_host)
        if ok:
            print(f"PROXY_READY: socks5://127.0.0.1:{args.port}", flush=True)
            while True:
                await asyncio.sleep(1.0)
        else:
            print("Failed to start tunnel for provided node.", file=sys.stderr, flush=True)
            sys.exit(1)
    elif args.find_and_start:
        proxy = await rotator.get_working_proxy(target_host=args.target_host)
        if proxy:
            print(f"PROXY_READY: {proxy}", flush=True)
            while True:
                await asyncio.sleep(1.0)
        else:
            print("No responsive VPN nodes found", file=sys.stderr, flush=True)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
