"""Global configuration and project target definitions for Sentinel Updater.

The active target can be configured directly via the TARGET variable below,
or auto-detected from the current directory structure.
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from typing import Optional


class TargetType(str, enum.Enum):
    """Supported update target types."""
    AUTO = "auto"              # Auto-detect based on directory contents
    BOT = "bot"                # Proxmox Sentinel Bot (Python / Systemd / Sing-box / Xray)
    CONTROLLER = "controller"  # Alias for Proxmox Sentinel Bot
    PANEL = "panel"            # Sentinel Panel (Docker Compose / Postgres / Web UI)
    ALL = "all"                # Update both if located side by side


# ==============================================================================
# 🎯 ЗАХАРДКОЖЕННАЯ ПЕРЕМЕННАЯ ВЫБОРА ЦЕЛИ ОБНОВЛЕНИЯ:
# Варианты: TargetType.AUTO | TargetType.BOT | TargetType.PANEL | TargetType.ALL
# ==============================================================================
TARGET: TargetType = TargetType.AUTO


@dataclass
class ProjectPaths:
    """Project directory paths and file locations."""
    root_dir: str

    @property
    def env_file(self) -> str:
        candidates = [
            os.path.join(self.root_dir, "bot", "config", ".env"),
            os.path.join(self.root_dir, "bot", ".env"),
            os.path.join(self.root_dir, "config", ".env"),
            os.path.join(self.root_dir, ".env"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return os.path.join(self.root_dir, ".env")

    @property
    def bin_dir(self) -> str:
        bot_bin = os.path.join(self.root_dir, "bot", "bin")
        if os.path.isdir(bot_bin):
            return bot_bin
        return os.path.join(self.root_dir, "bin")

    @property
    def bot_service_path(self) -> str:
        return os.path.join(self.root_dir, "bot", "proxmox-lxc-bot.service")

    @property
    def controller_service_path(self) -> str:
        return self.bot_service_path

    @property
    def docker_compose_file(self) -> str:
        for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            p = os.path.join(self.root_dir, name)
            if os.path.isfile(p):
                return p
        return os.path.join(self.root_dir, "docker-compose.yml")
