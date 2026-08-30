"""Python Dependencies & Virtual Environment Manager for Sentinel Controller."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Dict, Optional

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


class DependencyManager:
    """Manages Python virtual environments and package installations (uv / pip)."""

    def __init__(self, project_dir: str, proxy_url: Optional[str] = None) -> None:
        self.project_dir = project_dir
        self.venv_dir = os.path.join(project_dir, "bot", "venv")
        self.requirements_path = os.path.join(project_dir, "bot", "requirements.txt")
        self.proxy_url = proxy_url

    def _ensure_venv(self) -> str:
        """Ensures virtual environment exists, creating one if needed."""
        py_bin = os.path.join(self.venv_dir, "bin", "python")
        if sys.platform == "win32":
            py_bin = os.path.join(self.venv_dir, "Scripts", "python.exe")

        if not os.path.isfile(py_bin):
            log_info(f"Создание виртуального окружения Python: {BOLD}{self.venv_dir}{RESET}...")
            os.makedirs(os.path.dirname(self.venv_dir), exist_ok=True)
            run_command([sys.executable, "-m", "venv", self.venv_dir], cwd=self.project_dir, check=True, timeout=60.0)

        return py_bin

    def _verify_installed_packages(self, py_bin: str) -> bool:
        """Checks if critical bot dependencies are already available in the virtualenv."""
        test_script = "import aiogram, requests, proxmoxer, pydantic, aiohttp"
        try:
            res = subprocess.run([py_bin, "-c", test_script], capture_output=True, timeout=5.0)
            return res.returncode == 0
        except Exception:
            return False

    def update_dependencies(self) -> bool:
        """Updates Python dependencies using uv (fast) or pip with timeout and failover."""
        if not os.path.isfile(self.requirements_path):
            log_warn(f"Файл {self.requirements_path} не найден. Пропуск обновления зависимостей.")
            return True

        py_bin = self._ensure_venv()

        log_info("Обновление зависимостей Python (bot/requirements.txt)...")

        env_dict: Dict[str, str] = {
            "UV_HTTP_TIMEOUT": "20",
            "UV_NO_KEYRING": "1",
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
            "PIP_DEFAULT_TIMEOUT": "20",
        }
        if self.proxy_url:
            env_dict["http_proxy"] = self.proxy_url
            env_dict["https_proxy"] = self.proxy_url
            env_dict["all_proxy"] = self.proxy_url
            env_dict["HTTP_PROXY"] = self.proxy_url
            env_dict["HTTPS_PROXY"] = self.proxy_url
            env_dict["ALL_PROXY"] = self.proxy_url

        # Check for uv binary
        uv_bin = shutil.which("uv")
        if not uv_bin:
            for cand in [
                os.path.expanduser("~/.local/bin/uv"),
                os.path.expanduser("~/.cargo/bin/uv"),
                "/root/.local/bin/uv",
                "/usr/local/bin/uv",
            ]:
                if os.path.isfile(cand):
                    uv_bin = cand
                    break

        if uv_bin:
            try:
                log_info(f"Использование uv для ускоренной установки ({uv_bin})...")
                uv_cmd = [
                    uv_bin, "pip", "install",
                    "--python", self.venv_dir,
                    "-r", self.requirements_path,
                ]
                if not self.proxy_url:
                    uv_cmd.extend([
                        "--index-url", "https://mirror.yandex.ru/pypi/simple",
                        "--extra-index-url", "https://pypi.org/simple",
                    ])

                res = run_command(uv_cmd, cwd=self.project_dir, env=env_dict, check=False, timeout=90.0)
                if res.returncode == 0:
                    log_success("Зависимости Python успешно обновлены через uv!")
                    return True
            except Exception:
                log_warn("Переключение на стандартный pip...")

        # Fallback to pip
        pip_bin = os.path.join(self.venv_dir, "bin", "pip")
        if sys.platform == "win32":
            pip_bin = os.path.join(self.venv_dir, "Scripts", "pip.exe")

        pip_cmd = [pip_bin] if os.path.isfile(pip_bin) else [py_bin, "-m", "pip"]

        try:
            pip_args = pip_cmd + ["install", "--default-timeout=20", "--retries=2", "-r", self.requirements_path]
            if not self.proxy_url:
                pip_args.extend([
                    "--index-url", "https://mirror.yandex.ru/pypi/simple",
                    "--extra-index-url", "https://pypi.org/simple",
                ])

            res = run_command(pip_args, cwd=self.project_dir, env=env_dict, check=False, timeout=120.0)
            if res.returncode == 0:
                log_success("Зависимости Python успешно обновлены через pip!")
                return True
        except Exception as e:
            log_warn(f"Ошибка при установке через pip: {e}")

        if self._verify_installed_packages(py_bin):
            log_success("Используются текущие установленные зависимости (проверка импортов пройдена).")
            return True

        log_error("Необходимые Python-пакеты не установлены и сеть недоступна.")
        return False
