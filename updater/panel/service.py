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
    """Manages systemd unit registration and restarting for panel and host agent."""

    PANEL_SERVICE_NAME = "sentinel-panel"
    AGENT_SERVICE_NAME = "sentinel-agent"

    def __init__(self, project_dir: str) -> None:
        self.project_dir = project_dir
        self.panel_src = os.path.join(project_dir, "installation", f"{self.PANEL_SERVICE_NAME}.service")
        self.panel_target = f"/etc/systemd/system/{self.PANEL_SERVICE_NAME}.service"

        self.agent_src = os.path.join(project_dir, "host", f"{self.AGENT_SERVICE_NAME}.service")
        self.agent_target = f"/etc/systemd/system/{self.AGENT_SERVICE_NAME}.service"

    def register_and_restart_service(self) -> bool:
        """Registers or updates systemd services (panel & agent) and restarts them."""
        if sys.platform == "win32" or not shutil.which("systemctl"):
            return True

        success = True

        # 1. Always update & restart Sentinel Agent on the host (creates /var/run/sentinel/agent.sock)
        host_agent_py = os.path.join(self.project_dir, "host", "host_agent.py")
        if os.path.isfile(self.agent_src) or os.path.isfile(host_agent_py):
            log_info(f"Обновление службы хост-агента ({BOLD}{self.AGENT_SERVICE_NAME}.service{RESET})...")
            try:
                if os.path.isfile(self.agent_src):
                    with open(self.agent_src, "r", encoding="utf-8") as f:
                        content = f.read()
                    content = content.replace("/opt/sentinel-panel", self.project_dir)
                else:
                    host_dir = os.path.join(self.project_dir, "host")
                    content = (
                        "[Unit]\n"
                        "Description=Sentinel Host Agent\n"
                        "After=network.target\n\n"
                        "[Service]\n"
                        "Type=simple\n"
                        "User=root\n"
                        f"WorkingDirectory={host_dir}\n"
                        f"ExecStart=/usr/bin/python3 {host_dir}/host_agent.py\n"
                        "Restart=always\n"
                        "RestartSec=5\n\n"
                        "[Install]\n"
                        "WantedBy=multi-user.target\n"
                    )

                with open(self.agent_target, "w", encoding="utf-8") as f:
                    f.write(content)
                os.chmod(self.agent_target, 0o644)
                log_success(f"Unit-файл {BOLD}{self.AGENT_SERVICE_NAME}.service{RESET} обновлен (путь: {self.project_dir})")
            except Exception as e:
                log_warn(f"Не удалось обновить unit-файл {self.AGENT_SERVICE_NAME}: {e}")

            try:
                run_command(["systemctl", "daemon-reload"], check=False, timeout=10.0)
                run_command(["systemctl", "enable", self.AGENT_SERVICE_NAME], check=False, timeout=10.0)
                res = run_command(["systemctl", "restart", self.AGENT_SERVICE_NAME], check=False, timeout=25.0)
                if res.returncode == 0:
                    log_success(f"Служба {BOLD}{self.AGENT_SERVICE_NAME}.service{RESET} успешно перезапущена!")
                else:
                    log_warn(f"Не удалось перезапустить {self.AGENT_SERVICE_NAME}.service (код {res.returncode})")
                    success = False
            except Exception as e:
                log_warn(f"Ошибка при перезапуске {self.AGENT_SERVICE_NAME}: {e}")
                success = False

        # 2. Update & restart Sentinel Panel if service unit exists
        if os.path.isfile(self.panel_src) or os.path.isfile(self.panel_target):
            log_info(f"Обновление службы systemd панели ({BOLD}{self.PANEL_SERVICE_NAME}.service{RESET})...")

            if os.path.isfile(self.panel_src):
                try:
                    shutil.copyfile(self.panel_src, self.panel_target)
                    os.chmod(self.panel_target, 0o644)
                except Exception as e:
                    log_warn(f"Не удалось скопировать unit-файл панели: {e}")

            try:
                run_command(["systemctl", "daemon-reload"], check=False, timeout=10.0)
                run_command(["systemctl", "enable", self.PANEL_SERVICE_NAME], check=False, timeout=10.0)
                res = run_command(["systemctl", "restart", self.PANEL_SERVICE_NAME], check=False, timeout=25.0)
                if res.returncode == 0:
                    log_success(f"Служба {BOLD}{self.PANEL_SERVICE_NAME}.service{RESET} успешно перезапущена!")
                else:
                    success = False
            except Exception as e:
                log_warn(f"Предупреждение при перезапуске службы панели: {e}")
                success = False

        return success
