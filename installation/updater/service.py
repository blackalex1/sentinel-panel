"""Systemd Service Registration & Lifecycle Manager for Sentinel Panel."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Optional

from .common import (
    log_error,
    log_info,
    log_success,
    log_warn,
    run_command,
)


class ServiceManager:
    """Manages systemd unit creation and daemon reloading."""

    SERVICE_NAME = "sentinel-agent.service"

    def __init__(self, project_dir: str) -> None:
        self.project_dir = project_dir

    def register_and_restart_service(self) -> bool:
        """Registers sentinel-agent.service if systemd is present."""
        if platform.system() == "Windows" or not shutil.which("systemctl"):
            return True

        agent_bin = os.path.join(self.project_dir, "bin", "sentinel-core")
        service_file = f"/etc/systemd/system/{self.SERVICE_NAME}"

        # If agent binary is present and service directory exists
        if os.path.isfile(agent_bin) and os.path.isdir("/etc/systemd/system"):
            log_info(f"Обновление службы systemd ({self.SERVICE_NAME})...")
            unit_content = f"""[Unit]
Description=Sentinel Core Agent Daemon
After=network.target docker.service
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory={self.project_dir}
ExecStart={agent_bin}
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""
            try:
                with open(service_file, "w", encoding="utf-8") as f:
                    f.write(unit_content)

                run_command(["systemctl", "daemon-reload"], check=True)
                run_command(["systemctl", "enable", self.SERVICE_NAME], check=False)
                run_command(["systemctl", "restart", self.SERVICE_NAME], check=False)
                log_success(f"Служба {self.SERVICE_NAME} успешно зарегистрирована и перезапущена!")
            except Exception as e:
                log_warn(f"Не удалось обновить службу {self.SERVICE_NAME}: {e}")

        return True
