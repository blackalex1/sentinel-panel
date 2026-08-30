"""Proxmox Sentinel Controller Update Runner Orchestrator."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from typing import Optional

from ..core.common import (
    BOLD,
    CYAN,
    GREEN,
    RESET,
    WHITE,
    YELLOW,
    check_root,
    log_banner,
    log_error,
    log_info,
    log_step,
    log_success,
    log_warn,
)
from ..core.git import GitManager
from ..core.network import NetworkManager
from ..core.sentinel_core import SentinelCoreManager
from .dependencies import DependencyManager
from .engines import ProxyEngineManager
from .service import ServiceManager


class ControllerRunner:
    """Orchestrates the entire update lifecycle for Proxmox Sentinel Controller."""

    def __init__(
        self,
        project_dir: str,
        proxy_arg: Optional[str] = None,
        no_proxy: bool = False,
        auto_mode: bool = False,
        core_version: Optional[str] = None,
        force_core: bool = False,
        skip_git: bool = False,
        skip_deps: bool = False,
        skip_engines: bool = False,
        skip_service: bool = False,
        bootstrapped: bool = False,
    ) -> None:
        self.project_dir = project_dir
        self.proxy_arg = proxy_arg
        self.no_proxy = no_proxy
        self.auto_mode = auto_mode
        self.core_version = core_version
        self.force_core = force_core
        self.skip_git = skip_git
        self.skip_deps = skip_deps
        self.skip_engines = skip_engines
        self.skip_service = skip_service
        self.bootstrapped = bootstrapped

    def run(self) -> int:
        """Executes controller update pipeline."""
        check_root()
        os.chdir(self.project_dir)

        log_banner("🔄 ОБНОВЛЕНИЕ PROXMOX SENTINEL BOT", "Автоматизированный модульный установщик")

        # Display current git revision info
        try:
            head_proc = subprocess.run(
                ["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
            )
            if head_proc.returncode == 0 and head_proc.stdout.strip():
                print(f"  📌 Текущая ревизия бота: {BOLD}{head_proc.stdout.strip()}{RESET}\n")
        except Exception:
            pass

        total_steps = 6

        # Step 1: Git Codebase Sync
        log_step(1, total_steps, "Синхронизация кодовой базы Git")
        git_mgr = GitManager(
            project_dir=self.project_dir,
            repo_url="https://github.com/blackalex1/proxmox_Sentinel.git",
            proxy_url=self.proxy_arg,
        )

        old_head_env = os.getenv("SENTINEL_OLD_HEAD")
        new_head_env = os.getenv("SENTINEL_NEW_HEAD")

        if old_head_env and new_head_env and old_head_env != new_head_env:
            log_success(f"Кодовая база обновлена: {BOLD}{old_head_env[:7]} → {new_head_env[:7]}{RESET}")
            git_mgr.display_changelog(from_commit=old_head_env, to_commit=new_head_env)
        elif not self.skip_git and not self.bootstrapped:
            updated = git_mgr.update_codebase(silent_if_uptodate=False)
            if updated:
                log_info("Кодовая база обновлена. Перезапуск обновленного скрипта...")
                new_argv = [sys.executable, "-m", "updater.main", "--bootstrapped"]
                for a in sys.argv[1:]:
                    if a not in ("--bootstrapped",):
                        new_argv.append(a)
                os.execv(sys.executable, new_argv)
        else:
            log_success("Кодовая база актуальна (Up to date).")
            git_mgr.display_changelog(max_commits=3)

        # Step 2: Network & Proxy Setup
        log_step(2, total_steps, "Настройка сетевого подключения и прокси")
        network_mgr = NetworkManager(
            project_dir=self.project_dir,
            proxy_arg=self.proxy_arg,
            no_proxy=self.no_proxy,
            auto_mode=self.auto_mode,
            allow_env=True,
        )

        def _cleanup_signal(signum, frame):
            print(f"\n  {YELLOW}Прерывание процесса. Очистка ресурсов...{RESET}")
            network_mgr.cleanup()
            sys.exit(130)

        signal.signal(signal.SIGINT, _cleanup_signal)
        signal.signal(signal.SIGTERM, _cleanup_signal)

        try:
            network_mgr.show_menu()
            active_proxy = network_mgr.setup_network()

            # Step 3: Sentinel-Core Binaries & Libraries
            log_step(3, total_steps, "Компоненты ядра Sentinel-Core")
            bin_dir = os.path.join(self.project_dir, "bot", "bin")
            core_mgr = SentinelCoreManager(
                bin_dir=bin_dir,
                proxy_url=active_proxy,
                auto_mode=self.auto_mode,
                force=self.force_core,
            )
            target_ver = self.core_version or core_mgr.select_version()
            if target_ver:
                core_mgr.download_core(target_ver)

            # Step 4: Sing-box & Xray-core Proxy Engines
            if not self.skip_engines:
                log_step(4, total_steps, "Прокси-движки Sing-box и Xray-core")
                engine_mgr = ProxyEngineManager(
                    bin_dir=bin_dir,
                    proxy_url=active_proxy,
                    auto_mode=self.auto_mode,
                )
                engine_mgr.manage_engines()
            else:
                log_step(4, total_steps, "Прокси-движки (пропущено)")

            # Step 5: Python Dependencies
            if not self.skip_deps:
                log_step(5, total_steps, "Зависимости Python (bot/requirements.txt)")
                dep_mgr = DependencyManager(project_dir=self.project_dir, proxy_url=active_proxy)
                dep_mgr.update_dependencies()
            else:
                log_step(5, total_steps, "Зависимости Python (пропущено)")

            # Step 6: Systemd Service Registration & Restart
            if not self.skip_service:
                log_step(6, total_steps, "Служба systemd (proxmox-lxc-bot.service)")
                service_mgr = ServiceManager(project_dir=self.project_dir)
                service_mgr.register_and_restart_service()
            else:
                log_step(6, total_steps, "Служба systemd (пропущено)")

            # Success Banner
            log_banner(
                "✅ ОБНОВЛЕНИЕ PROXMOX SENTINEL BOT УСПЕШНО ЗАВЕРШЕНО!",
                "Все компоненты, ядро и служба бота обновлены",
            )

            # Explicitly shut down VPN/Sing-box rotator tunnel and free ports before long-running log stream
            network_mgr.cleanup()

            if sys.stdin.isatty() and not self.auto_mode and not self.skip_service:
                print(f"  {CYAN}📡 Подключение к живому потоку логов ({BOLD}journalctl -u proxmox-lxc-bot -f -n 25{RESET}{CYAN})...{RESET}")
                print(f"  {YELLOW}(Нажмите Ctrl+C для выхода из режима логов){RESET}\n")
                service_mgr = ServiceManager(project_dir=self.project_dir)
                service_mgr.stream_live_logs()
                print(f"\n  {GREEN}✔{RESET} Просмотр логов завершен. Служба контроллера работает в фоне.\n")

            return 0

        except Exception as e:
            log_error(f"Критическая ошибка при обновлении контроллера: {e}")
            return 1
        finally:
            network_mgr.cleanup()
