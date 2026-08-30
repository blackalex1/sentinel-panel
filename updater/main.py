"""Master CLI Entrypoint and Dispatcher for Sentinel Universal Updater."""

from __future__ import annotations

import argparse
import os
import sys

# Support running directly via `python3 path/to/main.py` or as a module `python3 -m updater.main`
if __package__ is None or __package__ == "":
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    from updater.config import TARGET, TargetType
    from updater.controller.runner import ControllerRunner
    from updater.core.common import (
        BOLD,
        CYAN,
        GREEN,
        RED,
        RESET,
        WHITE,
        YELLOW,
        log_banner,
        log_error,
        log_info,
        log_success,
        log_warn,
    )
    from updater.detector import detect_target, prompt_target_selection
    from updater.panel.runner import PanelRunner
else:
    from .config import TARGET, TargetType
    from .controller.runner import ControllerRunner
    from .core.common import (
        BOLD,
        CYAN,
        GREEN,
        RED,
        RESET,
        WHITE,
        YELLOW,
        log_banner,
        log_error,
        log_info,
        log_success,
        log_warn,
    )
    from .detector import detect_target, prompt_target_selection
    from .panel.runner import PanelRunner


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Sentinel Universal Modular Updater for Controller and Panel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--target", "-t",
        choices=["auto", "controller", "panel", "all"],
        default=None,
        help="Target project to update (controller | panel | all | auto). Default: from config.TARGET",
    )
    parser.add_argument(
        "--proxy", "-p",
        type=str,
        help="Specify an HTTP or SOCKS5 proxy URL (e.g. socks5://127.0.0.1:10808)",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Force direct connection without VPN rotator or proxy",
    )
    parser.add_argument(
        "--auto", "-y",
        action="store_true",
        help="Non-interactive automated update mode",
    )
    parser.add_argument(
        "--core-version",
        type=str,
        help="Specific sentinel-core version/tag to install (e.g. v0.0.8)",
    )
    parser.add_argument(
        "--force-core", "-f",
        action="store_true",
        help="Force core reinstallation even if already up to date",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip Git codebase pull/sync",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip Python dependency updates (Controller)",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip Docker container rebuild (Panel)",
    )
    parser.add_argument(
        "--skip-engines",
        action="store_true",
        help="Skip Sing-box / Xray proxy engine updates (Controller)",
    )
    parser.add_argument(
        "--skip-service",
        action="store_true",
        help="Skip Systemd service registration and restart",
    )
    parser.add_argument(
        "--dir", "-d",
        type=str,
        default=None,
        help="Custom project directory path (default: current working directory)",
    )
    parser.add_argument(
        "--bootstrapped",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    return parser.parse_args()


def determine_target(cli_target: str | None, project_dir: str) -> TargetType:
    """Resolves the target using CLI flag -> hardcoded TARGET -> auto-detection."""
    # 1. CLI argument takes highest priority
    if cli_target:
        return TargetType(cli_target)

    # 2. Hardcoded TARGET variable in config.py
    if TARGET != TargetType.AUTO:
        return TARGET

    # 3. Automatic directory signature detection
    detected = detect_target(project_dir)
    if detected != TargetType.AUTO:
        return detected

    # 4. Interactive selection
    return prompt_target_selection()


def main() -> int:
    """Master entrypoint function."""
    args = parse_args()

    project_dir = os.path.abspath(args.dir) if args.dir else os.getcwd()

    # Determine what to update
    target = determine_target(args.target, project_dir)

    target_label = "PROXMOX SENTINEL BOT" if target in (TargetType.BOT, TargetType.CONTROLLER) else ("SENTINEL PANEL" if target == TargetType.PANEL else "ВСЕ ПРОЕКТЫ (ALL)")
    log_info(f"Выбранная цель обновления: {BOLD}{target_label}{RESET} (Директория: {project_dir})")

    # 1. Update Proxmox Sentinel Bot
    if target in (TargetType.BOT, TargetType.CONTROLLER):
        controller_dir = project_dir
        if not os.path.isdir(os.path.join(controller_dir, "bot")):
            cand = os.path.join(project_dir, "controller")
            if os.path.isdir(cand):
                controller_dir = cand

        runner = ControllerRunner(
            project_dir=controller_dir,
            proxy_arg=args.proxy,
            no_proxy=args.no_proxy,
            auto_mode=args.auto,
            core_version=args.core_version,
            force_core=args.force_core,
            skip_git=args.skip_git,
            skip_deps=args.skip_deps,
            skip_engines=args.skip_engines,
            skip_service=args.skip_service,
            bootstrapped=args.bootstrapped,
        )
        return runner.run()

    # 2. Update Panel
    elif target == TargetType.PANEL:
        panel_dir = project_dir
        if not os.path.isfile(os.path.join(panel_dir, "docker-compose.yml")):
            cand = os.path.join(project_dir, "panel")
            if os.path.isdir(cand):
                panel_dir = cand

        runner = PanelRunner(
            project_dir=panel_dir,
            proxy_arg=args.proxy,
            no_proxy=args.no_proxy,
            auto_mode=args.auto,
            core_version=args.core_version,
            force_core=args.force_core,
            skip_git=args.skip_git,
            skip_docker=args.skip_docker,
            bootstrapped=args.bootstrapped,
        )
        return runner.run()

    # 3. Update Both (All)
    elif target == TargetType.ALL:
        log_banner("🔄 МАССОВОЕ ОБНОВЛЕНИЕ (CONTROLLER + PANEL)", "Последовательное обновление всех сервисов")

        controller_dir = project_dir
        if not os.path.isdir(os.path.join(controller_dir, "bot")):
            for c_name in ("controller", "proxmox_Sentinel", "proxmox-lxc-bot"):
                c_path = os.path.join(project_dir, c_name)
                if os.path.isdir(c_path):
                    controller_dir = c_path
                    break

        panel_dir = project_dir
        if not os.path.isfile(os.path.join(panel_dir, "docker-compose.yml")):
            for p_name in ("panel", "sentinel-panel"):
                p_path = os.path.join(project_dir, p_name)
                if os.path.isdir(p_path):
                    panel_dir = p_path
                    break

        # Run Controller
        c_runner = ControllerRunner(
            project_dir=controller_dir,
            proxy_arg=args.proxy,
            no_proxy=args.no_proxy,
            auto_mode=args.auto,
            core_version=args.core_version,
            force_core=args.force_core,
            skip_git=args.skip_git,
            skip_deps=args.skip_deps,
            skip_engines=args.skip_engines,
            skip_service=args.skip_service,
            bootstrapped=args.bootstrapped,
        )
        c_code = c_runner.run()

        # Run Panel
        p_runner = PanelRunner(
            project_dir=panel_dir,
            proxy_arg=args.proxy,
            no_proxy=args.no_proxy,
            auto_mode=args.auto,
            core_version=args.core_version,
            force_core=args.force_core,
            skip_git=args.skip_git,
            skip_docker=args.skip_docker,
            bootstrapped=args.bootstrapped,
        )
        p_code = p_runner.run()

        if c_code == 0 and p_code == 0:
            log_banner("🎉 ВСЕ СЕРВИСЫ SENTINEL УСПЕШНО ОБНОВЛЕНЫ!", "Контроллер и Панель готовы к работе")
            return 0
        return max(c_code, p_code)

    return 0


if __name__ == "__main__":
    sys.exit(main())
