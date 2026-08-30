"""Project Type Detector for Sentinel Updater."""

from __future__ import annotations

import os
import sys
from typing import Optional

from .config import TargetType
from .core.common import (
    BOLD,
    CYAN,
    GREEN,
    RESET,
    WHITE,
    YELLOW,
    log_banner,
    log_info,
    log_warn,
)


def detect_target(project_dir: str) -> TargetType:
    """Detects whether the target directory corresponds to Panel, Controller, or Both."""
    # Check for Panel indicators (Docker Compose, backend/frontend directories)
    is_panel = any([
        os.path.isfile(os.path.join(project_dir, "docker-compose.yml")),
        os.path.isfile(os.path.join(project_dir, "docker-compose.yaml")),
        os.path.isdir(os.path.join(project_dir, "backend")) and os.path.isdir(os.path.join(project_dir, "frontend")),
        os.path.isfile(os.path.join(project_dir, "installation", "sentinel-panel.service")),
    ])

    # Check for Proxmox Controller indicators (proxmox-lxc-bot.service, proxmox monitor modules)
    is_controller = any([
        os.path.isfile(os.path.join(project_dir, "bot", "proxmox-lxc-bot.service")),
        os.path.isfile(os.path.join(project_dir, "proxmox-lxc-bot.service")),
        os.path.isdir(os.path.join(project_dir, "bot", "modules", "proxmox")),
        os.path.isfile(os.path.join(project_dir, "bot", "config", "bot.ini")),
    ])

    # Check if this is a parent directory containing both distinct subproject folders
    has_sub_controller = os.path.isdir(os.path.join(project_dir, "controller")) or os.path.isdir(os.path.join(project_dir, "proxmox_Sentinel"))
    has_sub_panel = os.path.isdir(os.path.join(project_dir, "panel")) or os.path.isdir(os.path.join(project_dir, "sentinel-panel"))

    if is_panel and not is_controller:
        return TargetType.PANEL
    elif is_controller and not is_panel:
        return TargetType.CONTROLLER
    elif has_sub_controller and has_sub_panel:
        return TargetType.ALL

    if is_panel:
        return TargetType.PANEL
    if is_controller:
        return TargetType.CONTROLLER

    return TargetType.AUTO


def prompt_target_selection() -> TargetType:
    """Interactive target selector when auto-detection cannot determine project type."""
    if not sys.stdin.isatty():
        return TargetType.CONTROLLER

    log_banner("🎯 ВЫБОР ЦЕЛЕВОГО ПРОЕКТА ДЛЯ ОБНОВЛЕНИЯ", "Sentinel Universal Updater")
    print(f"  {CYAN}1){RESET} 🤖 {GREEN}Proxmox Sentinel Bot{RESET} (Python / Sing-box / Xray / Systemd)")
    print(f"  {CYAN}2){RESET} 🖥️  {GREEN}Sentinel Panel{RESET} (Docker Compose / Postgres / Web UI)")
    print(f"  {CYAN}3){RESET} 🌐 {GREEN}Обновить оба проекта (All){RESET}\n")

    while True:
        try:
            raw = input(f"  {BOLD}Выберите вариант [1-3]{RESET} (по умолчанию 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return TargetType.CONTROLLER

        if raw in ("1", ""):
            return TargetType.CONTROLLER
        elif raw == "2":
            return TargetType.PANEL
        elif raw == "3":
            return TargetType.ALL
        log_warn("Неверный выбор. Введите 1, 2 или 3.")
