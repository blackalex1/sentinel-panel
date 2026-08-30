"""Network, Proxy & VPN Rotator Manager for Sentinel Panel Updater."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from typing import Dict, Optional

from .common import (
    BOLD,
    CYAN,
    GREEN,
    RED,
    RESET,
    YELLOW,
    free_port,
    log_banner,
    log_error,
    log_info,
    log_success,
    log_warn,
)


class NetworkManager:
    """Manages VPN rotator tunnel and external HTTP/SOCKS5 proxy settings for Panel."""

    def __init__(self, project_dir: str, proxy_arg: Optional[str] = None, no_proxy: bool = False, auto_mode: bool = False) -> None:
        self.project_dir = project_dir
        self.custom_proxy: Optional[str] = proxy_arg
        self.configured_proxy: Optional[str] = None
        self.configured_vpn_node: Optional[str] = None
        self.no_proxy: bool = no_proxy
        self.auto_mode: bool = auto_mode
        self.use_rotator: bool = True if not (no_proxy or proxy_arg) else False
        self.use_env_proxy: bool = False
        self.rotator_proc: Optional[subprocess.Popen] = None
        self.active_proxy_url: Optional[str] = None

        self._init_proxy_from_env()

    def _init_proxy_from_env(self) -> None:
        """Reads PROXY_URL from .env file if not explicitly set."""
        env_paths = [
            os.path.join(self.project_dir, ".env"),
            os.path.join(self.project_dir, "config", ".env"),
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
                                    vpn_prefixes = ("ss://", "vless://", "trojan://", "hysteria2://", "hy2://", "vmess://", "tuic://", "wireguard://", "wg://")
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

        # In non-interactive or auto mode, fallback to configured proxy if custom_proxy wasn't passed via CLI
        if (not sys.stdin.isatty() or self.auto_mode) and not self.custom_proxy and not self.no_proxy:
            if self.configured_proxy:
                self.custom_proxy = self.configured_proxy
            elif self.configured_vpn_node:
                self.use_rotator = True

    def show_menu(self) -> None:
        """Displays interactive network selection menu if interactive TTY."""
        if not sys.stdin.isatty() or self.auto_mode or self.no_proxy or (self.custom_proxy and not self.use_env_proxy):
            return

        has_env = bool(self.configured_vpn_node or self.configured_proxy)

        log_banner("🌐 НАСТРОЙКА СЕТИ И ПРОКСИ ДЛЯ ОБНОВЛЕНИЯ ПАНЕЛИ")
        print("Выберите режим подключения к GitHub для загрузки релизов:")

        if has_env:
            if self.configured_vpn_node:
                node_name = self.configured_vpn_node.split("#")[-1] if "#" in self.configured_vpn_node else self.configured_vpn_node[:28]
                proto = self.configured_vpn_node.split("://")[0]
                print(f"  1) {GREEN}🟢 Прокси из .env: {BOLD}{node_name}{RESET} ({proto}){RESET} [Рекомендуется / По умолчанию]")
            else:
                print(f"  1) {GREEN}🟢 Прокси из .env: {BOLD}{self.configured_proxy}{RESET} [Рекомендуется / По умолчанию]")

            print(f"  2) 🔄 Автоматический поиск рабочего VPN / Прокси (ротатор)")
            print(f"  3) 🌐 Прямое соединение к GitHub (с авто-фолбэком на CDN-зеркала)")
            print(f"  4) 🔌 Ввести другой адрес прокси вручную\n")

            while True:
                try:
                    raw_choice = input("Выберите вариант [1-4] (по умолчанию 1): ")
                except (EOFError, KeyboardInterrupt):
                    print("")
                    raw_choice = "1"

                choice = re.sub(r"[^1-4]", "", raw_choice.strip()) or "1" if raw_choice.strip() == "" else re.sub(r"[^1-4]", "", raw_choice.strip())

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
                            p_input = input("Введите адрес прокси (например socks5://127.0.0.1:10808): ").strip()
                        except (EOFError, KeyboardInterrupt):
                            print("")
                            p_input = ""

                        if re.match(r"^(http|https|socks4|socks5|socks5h)://", p_input, re.IGNORECASE):
                            self.custom_proxy = p_input
                            break
                        print(f"{RED}Неверный формат URL прокси. Повторите ввод.{RESET}")
                    break
        else:
            print(f"  1) {GREEN}🟢 Автоматический VPN / Прокси ротатор{RESET} [Рекомендуется / По умолчанию]")
            print(f"  2) 🌐 Прямое соединение к GitHub (с авто-фолбэком на CDN-зеркала)")
            print(f"  3) 🔌 Ввести адрес HTTP / SOCKS5 прокси вручную\n")

            while True:
                try:
                    raw_choice = input("Выберите вариант [1-3] (по умолчанию 1): ")
                except (EOFError, KeyboardInterrupt):
                    print("")
                    raw_choice = "1"

                choice = re.sub(r"[^1-3]", "", raw_choice.strip()) or "1" if raw_choice.strip() == "" else re.sub(r"[^1-3]", "", raw_choice.strip())

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
                            p_input = input("Введите адрес прокси (например socks5://127.0.0.1:10808): ").strip()
                        except (EOFError, KeyboardInterrupt):
                            print("")
                            p_input = ""

                        if re.match(r"^(http|https|socks4|socks5|socks5h)://", p_input, re.IGNORECASE):
                            self.custom_proxy = p_input
                            break
                        print(f"{RED}Неверный формат URL прокси. Повторите ввод.{RESET}")
                    break

    def setup_network(self) -> Optional[str]:
        """Activates chosen proxy mode or starts automated failover rotator."""
        if self.no_proxy:
            log_info("Используется прямое сетевое подключение к GitHub (с CDN-зеркалами при блокировке).")
            return None

        if self.custom_proxy:
            self.active_proxy_url = self.custom_proxy
            log_info(f"Используется указанный прокси: {self.active_proxy_url}")
            return self.active_proxy_url

        if not self.use_rotator:
            return None

        # Start automated VPN Rotator / Node tunnel
        if self.configured_vpn_node:
            node_label = self.configured_vpn_node.split("#")[-1] if "#" in self.configured_vpn_node else self.configured_vpn_node[:30]
            log_info(f"Запуск локального Sing-box туннеля для ноды {BOLD}{node_label}{RESET}...")
        else:
            log_info("Запуск Sentinel Proxy Rotator для поиска рабочего VPN...")

        self.cleanup()

        # Find python executable inside backend venv or host
        py_bin = sys.executable
        venv_py = os.path.join(self.project_dir, "backend", "venv", "bin", "python")
        if os.path.isfile(venv_py):
            py_bin = venv_py

        rotator_py = os.path.join(self.project_dir, "backend", "proxy_rotator.py")
        cmd = [py_bin, "-u", rotator_py]
        if self.configured_vpn_node:
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
        timeout = 90.0

        while time.time() - start_time < timeout:
            line = self.rotator_proc.stdout.readline() if self.rotator_proc.stdout else ""
            if line:
                line_str = line.strip()
                if "PROXY_READY:" in line_str:
                    self.active_proxy_url = line_str.split("PROXY_READY:", 1)[1].strip()
                    log_success(f"VPN-туннель успешно поднят на {self.active_proxy_url}!")

                    import threading
                    def _drain_rotator_output():
                        try:
                            if self.rotator_proc and self.rotator_proc.stdout:
                                for _ in iter(self.rotator_proc.stdout.readline, ''):
                                    pass
                        except Exception:
                            pass

                    drain_thread = threading.Thread(target=_drain_rotator_output, daemon=True)
                    drain_thread.start()
                    return self.active_proxy_url
                elif line_str:
                    print(f"    {line_str}", flush=True)
            elif self.rotator_proc.poll() is not None:
                # Read all remaining output
                if self.rotator_proc.stdout:
                    for remaining in self.rotator_proc.stdout:
                        r_str = remaining.strip()
                        if r_str:
                            print(f"    {r_str}", flush=True)
                log_error("Процесс ротатора завершился до установления соединения.")
                break

            time.sleep(0.05)

        log_warn("Превышено время ожидания ответа от VPN-нод. Продолжаем обновление без ротатора...")
        self.cleanup()
        return None

    def start_vpn_rotator(self) -> Optional[str]:
        """Alias for setup_network for backward compatibility."""
        return self.setup_network()

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
        """Terminates any background rotator process and frees proxy ports."""
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
        except Exception:
            pass

        free_port(10818)
        free_port(10819)
