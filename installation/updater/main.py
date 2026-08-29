"""Main Orchestrator for Sentinel Panel Updater."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from .common import (
    BOLD,
    CYAN,
    GREEN,
    MAGENTA,
    RED,
    RESET,
    YELLOW,
    check_root,
    ensure_unencrypted_dns,
    log_banner,
    log_error,
    log_info,
    log_success,
    log_warn,
)
from .core import CoreManager
from .docker import DockerManager
from .git import GitManager
from .network import NetworkManager
from .service import ServiceManager


def get_project_root() -> str:
    """Calculates the absolute path to the panel project root."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, "..", ".."))


def main() -> int:
    """Main CLI entrypoint for panel update orchestrator."""
    parser = argparse.ArgumentParser(description="Sentinel Panel Modular Update Orchestrator")
    parser.add_argument("--proxy", "-p", help="HTTP / SOCKS5 proxy URL (e.g. socks5://127.0.0.1:10808)")
    parser.add_argument("--no-proxy", action="store_true", help="Direct connection without proxy or rotator")
    parser.add_argument("--auto", "-y", action="store_true", help="Non-interactive automated mode")
    parser.add_argument("--force", "-f", action="store_true", help="Force re-download even if already up to date")

    args = parser.parse_args()

    project_root = get_project_root()
    os.chdir(project_root)

    # 0. Initial System Checks
    check_root()

    network_mgr = NetworkManager(
        project_dir=project_root,
        proxy_arg=args.proxy,
        no_proxy=args.no_proxy,
        auto_mode=args.auto,
    )

    # Setup signal traps for graceful cleanup
    def handle_signal(sig, frame):
        print(f"\n{YELLOW}[!] Прерывание процесса обновления. Очистка ресурсов...{RESET}")
        network_mgr.cleanup()
        sys.exit(130)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        # 1. Interactive Network & Proxy Configuration
        network_mgr.show_menu()

        # 2. DNS Verification (Unencrypted UDP:53)
        ensure_unencrypted_dns()

        # 3. Start VPN Rotator if selected
        active_proxy = network_mgr.start_vpn_rotator()

        log_banner("🔄 UPDATING SENTINEL PANEL")

        # 4. Update Git Codebase
        git_mgr = GitManager(project_dir=project_root, proxy_url=active_proxy)
        git_mgr.update_codebase()

        # 5. Update Sentinel-Core Engine (v0.0.8+)
        core_mgr = CoreManager(
            project_dir=project_root,
            proxy_url=active_proxy,
            auto_mode=args.auto,
            force=args.force,
        )
        core_ok = core_mgr.update_core()
        if not core_ok:
            log_warn("Не удалось обновить некоторые компоненты ядра. Продолжаем развертывание...")

        # 6. Rebuild & Restart Docker Containers
        docker_mgr = DockerManager(project_dir=project_root, proxy_url=active_proxy)
        docker_ok = docker_mgr.rebuild_and_restart()
        if not docker_ok:
            log_error("Ошибка при сборке контейнеров Docker.")

        # 7. Register / Restart Systemd Service
        service_mgr = ServiceManager(project_dir=project_root)
        service_mgr.register_and_restart_service()

        # 8. Success Banner
        log_banner("✅ ОБНОВЛЕНИЕ ПАНЕЛИ SENTINEL УСПЕШНО ЗАВЕРШЕНО!")
        print(f"{GREEN}Панель доступна по адресу:{RESET} {BOLD}http://<IP_СЕРВЕРА>:8000{RESET}")
        print(f"{CYAN}База данных PostgreSQL:{RESET}  {BOLD}порт 5432 (том: sentinel-panel_pgdata){RESET}")
        print(f"{MAGENTA}Логи панели:{RESET}             {BOLD}docker compose logs -f{RESET}\n")

        return 0

    except Exception as e:
        log_error(f"Критическая ошибка в процессе обновления: {e}")
        return 1
    finally:
        network_mgr.cleanup()


if __name__ == "__main__":
    sys.exit(main())
