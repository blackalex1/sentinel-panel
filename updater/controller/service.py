"""Systemd Service Manager for Sentinel Controller (proxmox-lxc-bot.service)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

from ..core.common import (
    BOLD,
    CYAN,
    GREEN,
    RED,
    RESET,
    YELLOW,
    log_error,
    log_info,
    log_success,
    log_warn,
    run_command,
)


class ServiceManager:
    """Manages systemd unit registration, restarting, and live log streaming for controller."""

    SERVICE_NAME = "proxmox-lxc-bot"

    def __init__(self, project_dir: str) -> None:
        self.project_dir = project_dir
        self.service_src = os.path.join(project_dir, "bot", f"{self.SERVICE_NAME}.service")
        self.systemd_target = f"/etc/systemd/system/{self.SERVICE_NAME}.service"

    def register_and_restart_service(self) -> bool:
        """Registers or updates systemd service and restarts it."""
        if sys.platform == "win32" or not shutil.which("systemctl"):
            log_warn("systemd не обнаружен на данной платформе. Пропуск управления службой.")
            return True

        log_info(f"Обновление службы systemd ({BOLD}{self.SERVICE_NAME}.service{RESET})...")

        if os.path.isfile(self.service_src):
            try:
                with open(self.service_src, "r", encoding="utf-8") as f:
                    content = f.read()

                bot_dir = os.path.join(self.project_dir, "bot")
                venv_py = os.path.join(bot_dir, "venv", "bin", "python")

                if "/opt/proxmox-lxc-bot" in content and self.project_dir != "/opt/proxmox-lxc-bot":
                    content = content.replace("/opt/proxmox-lxc-bot/bot/venv/bin/python", venv_py)
                    content = content.replace("/opt/proxmox-lxc-bot/bot", bot_dir)

                with open(self.systemd_target, "w", encoding="utf-8") as f:
                    f.write(content)

                os.chmod(self.systemd_target, 0o644)
            except Exception as e:
                log_warn(f"Не удалось обновить unit-файл {self.systemd_target}: {e}")

        try:
            run_command(["systemctl", "daemon-reload"], check=False, timeout=10.0)
            run_command(["systemctl", "enable", self.SERVICE_NAME], check=False, timeout=10.0)
            res = run_command(["systemctl", "restart", self.SERVICE_NAME], check=False, timeout=25.0)
            if res.returncode == 0:
                log_success(f"Служба {BOLD}{self.SERVICE_NAME}.service{RESET} успешно перезапущена!")
                return True
            else:
                log_error(f"Не удалось перезапустить службу {self.SERVICE_NAME}.service")
                return False
        except Exception as e:
            log_error(f"Ошибка управления службой systemd: {e}")
            return False

    def stream_live_logs(self) -> None:
        """Attaches to live journalctl log stream until interrupted by user (Ctrl+C)."""
        if sys.platform == "win32" or not shutil.which("journalctl"):
            return

        try:
            subprocess.run(["journalctl", "-u", self.SERVICE_NAME, "-f", "-n", "25"])
        except KeyboardInterrupt:
            pass
