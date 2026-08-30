"""Network, Proxy & VPN Rotator Manager for Sentinel Updater."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from typing import Dict, Optional

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
    free_port,
    log_banner,
    log_error,
    log_info,
    log_success,
    log_warn,
)


class NetworkManager:
    """Manages VPN rotator tunnels and HTTP/SOCKS5 proxy settings for Sentinel components."""

    def __init__(
        self,
        project_dir: str,
        proxy_arg: Optional[str] = None,
        no_proxy: bool = False,
        auto_mode: bool = False,
        allow_env: bool = False,
    ) -> None:
        self.project_dir = project_dir
        self.custom_proxy: Optional[str] = proxy_arg
        self.configured_proxy: Optional[str] = None
        self.configured_vpn_node: Optional[str] = None
        self.no_proxy: bool = no_proxy
        self.auto_mode: bool = auto_mode
        self.allow_env: bool = allow_env
        self.use_rotator: bool = True if not (no_proxy or proxy_arg) else False
        self.use_env_proxy: bool = False
        self.rotator_proc: Optional[subprocess.Popen] = None
        self.active_proxy_url: Optional[str] = None

        if self.allow_env:
            self._init_proxy_from_env()

    def _init_proxy_from_env(self) -> None:
        """Reads PROXY_URL from bot/config/.env or bot/.env (Controller only)."""
        env_paths = [
            os.path.join(self.project_dir, "bot", "config", ".env"),
            os.path.join(self.project_dir, "config", ".env"),
            os.path.join(self.project_dir, ".env"),
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
                                    vpn_prefixes = (
                                        "ss://", "vless://", "trojan://", "hysteria2://",
                                        "hy2://", "vmess://", "tuic://", "wireguard://", "wg://"
                                    )
                                    if any(val.lower().startswith(pref) for pref in vpn_prefixes):
                                        self.configured_vpn_node = val
                                        self.use_env_proxy = True
                                    elif re.match(r"^(http|https|socks4|socks5|socks5h)://", val, re.IGNORECASE):
                                        self.configured_proxy = val
                                        self.use_env_proxy = True
                                    break
                except Exception:
                    pass
            if self.configured_vpn_node or self.configured_proxy:
                break

        if (not sys.stdin.isatty() or self.auto_mode) and not self.custom_proxy and not self.no_proxy:
            if self.configured_proxy:
                self.custom_proxy = self.configured_proxy
            elif self.configured_vpn_node:
                self.use_rotator = True

    def show_menu(self) -> None:
        """Displays interactive network selection menu if running in interactive TTY."""
        if not sys.stdin.isatty() or self.auto_mode or self.no_proxy or (self.custom_proxy and not self.use_env_proxy):
            return

        has_env = bool(self.allow_env and (self.configured_vpn_node or self.configured_proxy))

        log_banner("🌐 НАСТРОЙКА СЕТИ И ПРОКСИ", "Выбор режима подключения к GitHub для загрузки")

        if has_env:
            if self.configured_vpn_node:
                node_name = self.configured_vpn_node.split("#")[-1] if "#" in self.configured_vpn_node else self.configured_vpn_node[:30]
                proto = self.configured_vpn_node.split("://")[0]
                print(f"  {CYAN}1){RESET} {GREEN}🟢 Прокси из .env:{RESET} {BOLD}{node_name}{RESET} ({proto}) [Рекомендуется / По умолчанию]")
            else:
                print(f"  {CYAN}1){RESET} {GREEN}🟢 Прокси из .env:{RESET} {BOLD}{self.configured_proxy}{RESET} [Рекомендуется / По умолчанию]")

            print(f"  {CYAN}2){RESET} 🔄 Автоматический поиск рабочего VPN / Прокси (ротатор из списков)")
            print(f"  {CYAN}3){RESET} 🌐 Прямое соединение к GitHub (с CDN-зеркалами)")
            print(f"  {CYAN}4){RESET} 🔌 Ввести другой адрес прокси вручную\n")

            while True:
                try:
                    raw_choice = input(f"  {BOLD}Выберите вариант [1-4]{RESET} (по умолчанию 1): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("")
                    raw_choice = "1"

                choice = re.sub(r"[^1-4]", "", raw_choice) or "1"

                if choice == "1":
                    if self.configured_vpn_node:
                        self.use_rotator = True
                        self.no_proxy = False
                    else:
                        self.custom_proxy = self.configured_proxy
                        self.use_rotator = False
                        self.no_proxy = False
                    break
                elif choice == "2":
                    self.configured_vpn_node = None
                    self.configured_proxy = None
                    self.custom_proxy = None
                    self.use_env_proxy = False
                    self.use_rotator = True
                    self.no_proxy = False
                    break
                elif choice == "3":
                    self.use_rotator = False
                    self.no_proxy = True
                    break
                elif choice == "4":
                    self.use_rotator = False
                    self.no_proxy = False
                    while True:
                        try:
                            p_input = input("  Введите URL прокси (например socks5://127.0.0.1:10808): ").strip()
                        except (EOFError, KeyboardInterrupt):
                            print("")
                            p_input = ""

                        if re.match(r"^(http|https|socks4|socks5|socks5h)://", p_input, re.IGNORECASE):
                            self.custom_proxy = p_input
                            break
                        log_warn("Неверный формат URL прокси. Повторите ввод.")
                    break
        else:
            print(f"  {CYAN}1){RESET} {GREEN}🟢 Автоматический VPN / Прокси ротатор{RESET} [Рекомендуется / По умолчанию]")
            print(f"  {CYAN}2){RESET} 🌐 Прямое соединение к GitHub (с авто-фолбэком на CDN)")
            print(f"  {CYAN}3){RESET} 🔌 Ввести адрес HTTP / SOCKS5 прокси вручную\n")

            while True:
                try:
                    raw_choice = input(f"  {BOLD}Выберите вариант [1-3]{RESET} (по умолчанию 1): ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("")
                    raw_choice = "1"

                choice = re.sub(r"[^1-3]", "", raw_choice) or "1"

                if choice == "1":
                    self.use_rotator = True
                    self.no_proxy = False
                    break
                elif choice == "2":
                    self.use_rotator = False
                    self.no_proxy = True
                    break
                elif choice == "3":
                    self.use_rotator = False
                    self.no_proxy = False
                    while True:
                        try:
                            p_input = input("  Введите URL прокси (например socks5://127.0.0.1:10808): ").strip()
                        except (EOFError, KeyboardInterrupt):
                            print("")
                            p_input = ""

                        if re.match(r"^(http|https|socks4|socks5|socks5h)://", p_input, re.IGNORECASE):
                            self.custom_proxy = p_input
                            break
                        log_warn("Неверный формат URL прокси. Повторите ввод.")
                    break

    def _ensure_rotator_prerequisites(self) -> bool:
        """Verifies that libsentinel-core and sing-box/xray binaries exist.
        If missing, automatically downloads them via CDN mirrors."""
        bot_bin = os.path.join(self.project_dir, "bot", "bin")
        bin_dir = bot_bin if os.path.isdir(os.path.join(self.project_dir, "bot")) else os.path.join(self.project_dir, "bin")
        os.makedirs(bin_dir, exist_ok=True)

        is_win = sys.platform == "win32"
        is_mac = sys.platform == "darwin"
        lib_ext = ".dll" if is_win else (".dylib" if is_mac else ".so")
        exe_ext = ".exe" if is_win else ""

        lib_names = [f"libsentinel-core{lib_ext}", f"sentinel-core{lib_ext}"]
        lib_exists = any(os.path.isfile(os.path.join(bin_dir, n)) for n in lib_names)

        engine_names = [f"sing-box{exe_ext}", f"singbox{exe_ext}", f"xray{exe_ext}"]
        engine_exists = any(os.path.isfile(os.path.join(bin_dir, n)) for n in engine_names)

        if lib_exists and engine_exists:
            return True

        log_info("Для работы VPN-ротатора выполняется быстрая подготовка компонентов...")

        # 1. Download libsentinel-core if missing
        if not lib_exists:
            try:
                from .sentinel_core import SentinelCoreManager
                core_mgr = SentinelCoreManager(bin_dir=bin_dir, proxy_url=None, auto_mode=True)
                _, _, latest_tag = core_mgr.fetch_releases()
                tag_to_use = latest_tag or "latest"
                log_info(f"Загрузка ядра Sentinel-Core ({tag_to_use}) для VPN-ротатора...")
                core_mgr.download_core(tag_to_use)
            except Exception as e:
                log_warn(f"Не удалось автоматически загрузить ядро Sentinel-Core: {e}")

        # 2. Download sing-box if missing
        if not engine_exists:
            try:
                from ..controller.engines import ProxyEngineManager
                engine_mgr = ProxyEngineManager(bin_dir=bin_dir, proxy_url=None, auto_mode=True)
                log_info("Загрузка движка Sing-box для VPN-ротатора...")
                engine_mgr.download_singbox()
            except Exception as e:
                log_warn(f"Не удалось автоматически загрузить Sing-box: {e}")

        # Re-check presence
        lib_ok = any(os.path.isfile(os.path.join(bin_dir, n)) for n in lib_names)
        engine_ok = any(os.path.isfile(os.path.join(bin_dir, n)) for n in engine_names)

        if not (lib_ok and engine_ok):
            log_warn("Ядра Sing-box / Sentinel-Core отсутствуют. Переключение на прямое подключение (CDN-зеркала)...")
            return False

        return True

    def setup_network(self) -> Optional[str]:
        """Activates chosen proxy mode or starts automated rotator."""
        if self.no_proxy:
            log_info("Используется прямое сетевое подключение к GitHub (с CDN-зеркалами при блокировке).")
            return None

        if self.custom_proxy:
            self.active_proxy_url = self.custom_proxy
            log_info(f"Используется указанный прокси: {BOLD}{self.active_proxy_url}{RESET}")
            return self.active_proxy_url

        if not self.use_rotator:
            return None

        # Check and ensure prerequisites (Sentinel-Core and Sing-box)
        if not self._ensure_rotator_prerequisites():
            self.use_rotator = False
            self.no_proxy = True
            log_info("Используется прямое сетевое подключение к GitHub (с CDN-зеркалами при блокировке).")
            return None

        rotator_candidates = [
            os.path.join(os.path.dirname(__file__), "proxy_rotator.py"),
            os.path.join(self.project_dir, "updater", "core", "proxy_rotator.py"),
            os.path.join(self.project_dir, "bot", "core", "proxy_rotator.py"),
            os.path.join(self.project_dir, "backend", "proxy_rotator.py"),
        ]
        rotator_py = next((p for p in rotator_candidates if os.path.isfile(p)), None)

        if not rotator_py:
            log_info("Скрипт proxy_rotator.py не найден. Используются CDN-зеркала GitHub.")
            return None

        if self.allow_env and self.configured_vpn_node:
            node_label = self.configured_vpn_node.split("#")[-1] if "#" in self.configured_vpn_node else self.configured_vpn_node[:30]
            log_info(f"Запуск локального Sing-box туннеля для ноды {BOLD}{node_label}{RESET}...")
        else:
            log_info("Запуск Sentinel Proxy Rotator для поиска рабочего VPN из списков...")

        self.cleanup()

        # Find python binary
        py_bin = sys.executable
        for venv_cand in [
            os.path.join(self.project_dir, "backend", "venv", "bin", "python"),
            os.path.join(self.project_dir, "bot", "venv", "bin", "python"),
            os.path.join(self.project_dir, ".venv", "bin", "python"),
        ]:
            if os.path.isfile(venv_cand):
                py_bin = venv_cand
                break

        cmd = [py_bin, "-u", rotator_py]
        if self.allow_env and self.configured_vpn_node:
            cmd.extend(["--node", self.configured_vpn_node, "--port", "10818", "--target-host", "objects.githubusercontent.com"])
        else:
            cmd.extend(["--find-and-start", "--port", "10818", "--target-host", "objects.githubusercontent.com"])

        try:
            extra_kwargs = {}
            if sys.platform != "win32":
                extra_kwargs["preexec_fn"] = os.setsid

            self.rotator_proc = subprocess.Popen(
                cmd,
                cwd=self.project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
                **extra_kwargs
            )
        except Exception as e:
            log_warn(f"Не удалось запустить процесс ротатора: {e}")
            return None

        start_time = time.time()
        timeout = 75.0

        while time.time() - start_time < timeout:
            line = self.rotator_proc.stdout.readline() if self.rotator_proc.stdout else ""
            if line:
                line_str = line.strip()
                if "PROXY_READY:" in line_str:
                    self.active_proxy_url = line_str.split("PROXY_READY:", 1)[1].strip()
                    log_success(f"VPN-туннель успешно поднят на {BOLD}{self.active_proxy_url}{RESET}!")

                    def _drain_rotator():
                        try:
                            if self.rotator_proc and self.rotator_proc.stdout:
                                for _ in iter(self.rotator_proc.stdout.readline, ''):
                                    pass
                        except Exception:
                            pass

                    drain_thread = threading.Thread(target=_drain_rotator, daemon=True)
                    drain_thread.start()
                    return self.active_proxy_url
                elif line_str:
                    print(f"    {DARK_GRAY}{line_str}{RESET}", flush=True)
            elif self.rotator_proc.poll() is not None:
                log_warn("Процесс ротатора завершился до установления соединения. Продолжение через зеркала...")
                break

            time.sleep(0.05)

        log_warn("Превышено время ожидания ответа от VPN-нод. Продолжение через зеркала...")
        self.cleanup()
        return None

    def get_env_dict(self) -> Dict[str, str]:
        """Returns environment dictionary configured with the active proxy."""
        env: Dict[str, str] = {}
        if self.active_proxy_url:
            env["http_proxy"] = self.active_proxy_url
            env["https_proxy"] = self.active_proxy_url
            env["all_proxy"] = self.active_proxy_url
            env["HTTP_PROXY"] = self.active_proxy_url
            env["HTTPS_PROXY"] = self.active_proxy_url
            env["ALL_PROXY"] = self.active_proxy_url
        return env

    def cleanup(self) -> None:
        """Terminates background rotator processes and frees proxy ports."""
        if self.rotator_proc:
            try:
                if sys.platform != "win32":
                    try:
                        os.killpg(os.getpgid(self.rotator_proc.pid), signal.SIGTERM)
                    except Exception:
                        self.rotator_proc.terminate()
                else:
                    self.rotator_proc.terminate()
                self.rotator_proc.wait(timeout=1.5)
            except Exception:
                try:
                    if sys.platform != "win32":
                        try:
                            os.killpg(os.getpgid(self.rotator_proc.pid), signal.SIGKILL)
                        except Exception:
                            self.rotator_proc.kill()
                    else:
                        self.rotator_proc.kill()
                except Exception:
                    pass
            self.rotator_proc = None

        try:
            if sys.platform != "win32":
                subprocess.run(["pkill", "-9", "-f", "singbox_failover.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["pkill", "-9", "-f", "xray_failover.json"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["pkill", "-9", "-f", "proxy_rotator.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        free_port(10818)
        free_port(10819)
