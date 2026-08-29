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
    """Manages VPN rotator tunnel and external HTTP/SOCKS5 proxy settings."""

    def __init__(self, project_dir: str, proxy_arg: Optional[str] = None, no_proxy: bool = False, auto_mode: bool = False) -> None:
        self.project_dir = project_dir
        self.custom_proxy: Optional[str] = proxy_arg
        self.no_proxy: bool = no_proxy
        self.auto_mode: bool = auto_mode
        self.use_rotator: bool = True if not (no_proxy or proxy_arg) else False
        self.rotator_proc: Optional[subprocess.Popen] = None
        self.active_proxy_url: Optional[str] = None

        self._init_proxy_from_env()

    def _init_proxy_from_env(self) -> None:
        """Reads PROXY_URL from .env file if not explicitly set."""
        if not self.custom_proxy and not self.no_proxy:
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
                                            self.use_rotator = True
                                        elif re.match(r"^(http|https|socks4|socks5|socks5h)://", val, re.IGNORECASE):
                                            self.custom_proxy = val
                                        break
                    except Exception:
                        pass
                if self.custom_proxy:
                    break

    def show_menu(self) -> None:
        """Displays interactive network selection menu if interactive TTY."""
        if not sys.stdin.isatty() or self.auto_mode or self.no_proxy or self.custom_proxy:
            return

        log_banner("🌐 НАСТРОЙКА СЕТИ И ПРОКСИ ДЛЯ ОБНОВЛЕНИЯ ПАНЕЛИ")
        print("Выберите режим подключения к GitHub для загрузки релизов:")
        print(f"  1) {GREEN}🟢 Автоматический VPN / Прокси ротатор{RESET} [Рекомендуется / По умолчанию]")
        print(f"  2) 🌐 Прямое соединение к GitHub (с авто-фолбэком на CDN-зеркала при блокировке)")
        print(f"  3) 🔌 Использовать существующий HTTP / SOCKS5 прокси\n")

        while True:
            try:
                raw_choice = input(f"Выберите вариант [1-3] (по умолчанию 1): ")
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
                    p_input = input("Введите адрес прокси (например socks5://127.0.0.1:10808): ").strip()
                    if re.match(r"^(http|https|socks4|socks5|socks5h)://", p_input, re.IGNORECASE):
                        self.custom_proxy = p_input
                        break
                    print(f"{RED}❌ Неверный формат! URL должен начинаться с http://, https://, socks5:// или socks5h://{RESET}")
                break
            else:
                print(f"{RED}❌ Неверный ввод '{raw_choice.strip()}'. Пожалуйста, введите 1, 2 или 3.{RESET}")

        print("")

    def start_vpn_rotator(self) -> Optional[str]:
        """Starts backend proxy rotator and waits for active local failover tunnel."""
        if not self.use_rotator or self.no_proxy:
            if self.custom_proxy:
                self.active_proxy_url = self.custom_proxy
                log_success(f"Используется указанный прокси: {self.active_proxy_url}")
            else:
                log_info("Прокси не активен. Будут задействованы быстрые CDN-зеркала и прямые соединения.")
            return self.active_proxy_url

        free_port(10818)
        free_port(10819)

        log_info("Запуск Sentinel Proxy Rotator для поиска рабочего VPN...")

        cmd = [sys.executable, "-m", "backend.proxy_rotator", "--port", "10818"]
        if self.custom_proxy and re.match(r"^(ss|vless|vmess|trojan|hysteria2)://", self.custom_proxy):
            cmd.extend(["--node", self.custom_proxy])
        else:
            cmd.append("--find-and-start")

        try:
            self.rotator_proc = subprocess.Popen(
                cmd,
                cwd=self.project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            log_warn(f"Не удалось запустить процесс ротатора: {e}")
            return None

        start_time = time.time()
        timeout = 90.0

        while time.time() - start_time < timeout:
            if self.rotator_proc.poll() is not None:
                log_error("Процесс ротатора завершился до установления соединения.")
                break

            line = self.rotator_proc.stdout.readline() if self.rotator_proc.stdout else ""
            if line:
                line_str = line.strip()
                if "PROXY_READY:" in line_str:
                    self.active_proxy_url = line_str.split("PROXY_READY:", 1)[1].strip()
                    log_success(f"VPN-туннель успешно поднят на {self.active_proxy_url}!")
                    return self.active_proxy_url
                elif any(k in line_str for k in ("[INFO]", "[Failover]", "Tier", "nodes alive", "Best:", "singbox")):
                    print(f"    {line_str}", flush=True)

            time.sleep(0.1)

        log_warn("Превышено время ожидания ответа от VPN-нод. Продолжаем обновление без ротатора...")
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
        """Terminates any background rotator process and frees proxy ports."""
        if self.rotator_proc:
            try:
                self.rotator_proc.terminate()
                self.rotator_proc.wait(timeout=2.0)
            except Exception:
                try:
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
