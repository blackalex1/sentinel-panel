"""Systemd Service Manager for Sentinel Panel."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from ..core.common import (
    BOLD,
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
    """Manages systemd unit registration and restarting for panel."""

    SERVICE_NAME = "sentinel-panel"

    def __init__(self, project_dir: str) -> None:
        self.project_dir = project_dir
        self.service_src = os.path.join(project_dir, "installation", f"{self.SERVICE_NAME}.service")
        self.systemd_target = f"/etc/systemd/system/{self.SERVICE_NAME}.service"

    def register_and_restart_service(self) -> bool:
        """Registers or updates systemd service and restarts it if service file exists."""
        if sys.platform == "win32" or not shutil.which("systemctl"):
            return True

        if not os.path.isfile(self.service_src) and not os.path.isfile(self.systemd_target):
            return True

        log_info(f"Обновление службы systemd ({BOLD}{self.SERVICE_NAME}.service{RESET})...")

        if os.path.isfile(self.service_src):
            try:
                shutil.copyfile(self.service_src, self.systemd_target)
                os.chmod(self.systemd_target, 0o644)
            except Exception as e:
                log_warn(f"Не удалось скопировать unit-файл: {e}")

        try:
            run_command(["systemctl", "daemon-reload"], check=False, timeout=10.0)
            run_command(["systemctl", "enable", self.SERVICE_NAME], check=False, timeout=10.0)
            res = run_command(["systemctl", "restart", self.SERVICE_NAME], check=False, timeout=25.0)
            if res.returncode == 0:
                log_success(f"Служба {BOLD}{self.SERVICE_NAME}.service{RESET} успешно перезапущена!")
                return True
        except Exception as e:
            log_warn(f"Предупреждение при перезапуске службы: {e}")

        return False
