"""Docker Compose & Database Volume Migration Manager for Sentinel Panel."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.parse
from typing import Dict, List, Optional

from ..core.common import (
    BOLD,
    CYAN,
    GREEN,
    RED,
    RESET,
    WHITE,
    YELLOW,
    free_port,
    log_error,
    log_info,
    log_success,
    log_warn,
    run_command,
)


class DockerManager:
    """Manages process cleanup, PostgreSQL volume migration, and Docker Compose rebuilding."""

    def __init__(self, project_dir: str, proxy_url: Optional[str] = None) -> None:
        self.project_dir = project_dir
        self.proxy_url = proxy_url

    def _get_compose_cmd(self) -> List[str]:
        """Detects whether 'docker compose' or 'docker-compose' is available."""
        try:
            res = subprocess.run(["docker", "compose", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                return ["docker", "compose"]
        except Exception:
            pass

        if shutil.which("docker-compose"):
            return ["docker-compose"]

        return ["docker", "compose"]

    def cleanup_conflicting_processes(self) -> None:
        """Kills any stale Python/Agent/Postgres processes holding panel ports."""
        log_info("Очистка конфликтующих локальных портов (8000, 8080, 5432)...")
        for port in (8000, 8080, 5432):
            free_port(port)

        try:
            subprocess.run(["pkill", "-f", "backend.main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "sentinel-agent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def migrate_database_volumes(self) -> None:
        """Migrates legacy spectre-panel_pgdata volume to sentinel-panel_pgdata with compose labels."""
        try:
            volumes_out = run_command(["docker", "volume", "ls", "-q"], capture=True, check=False).stdout.strip().splitlines()
            has_old = "spectre-panel_pgdata" in volumes_out
            has_new = "sentinel-panel_pgdata" in volumes_out

            if has_old and not has_new:
                log_warn("Обнаружен том базы данных старой версии (spectre-panel_pgdata). Миграция в sentinel-panel_pgdata...")
                run_command(
                    [
                        "docker", "volume", "create",
                        "--label", "com.docker.compose.project=sentinel-panel",
                        "--label", "com.docker.compose.volume=pgdata",
                        "sentinel-panel_pgdata",
                    ],
                    check=True,
                )

                run_command(
                    [
                        "docker", "run", "--rm",
                        "-v", "spectre-panel_pgdata:/from",
                        "-v", "sentinel-panel_pgdata:/to",
                        "alpine", "ash", "-c", "cp -a /from/. /to/",
                    ],
                    check=True,
                )
                log_success("Миграция данных PostgreSQL в sentinel-panel_pgdata успешно завершена!")
        except Exception as e:
            log_warn(f"Пропуск автоматической миграции томов Docker: {e}")

    def cleanup_build_artifacts(self) -> None:
        """Removes dangling images and stale BuildKit cache after building."""
        log_info("Очистка неиспользуемых слоев и кэша сборщика Docker...")
        try:
            # 1. Удаление висячих (dangling) образов (<none>:<none>) от старых сборок
            run_command(["docker", "image", "prune", "-f"], check=False)
        except Exception as e:
            log_warn(f"Не удалось выполнить docker image prune: {e}")

        try:
            # 2. Удаление висячего кэша сборщика BuildKit
            run_command(["docker", "builder", "prune", "-f"], check=False)
            # 3. Удаление всех неиспользуемых слоев кэша сборщика старше 24 часов
            run_command(["docker", "builder", "prune", "-a", "-f", "--filter", "until=24h"], check=False)
        except Exception as e:
            log_warn(f"Не удалось выполнить docker builder prune: {e}")

    def rebuild_and_restart(self) -> bool:
        """Rebuilds and restarts all Docker containers."""
        if not shutil.which("docker"):
            log_error("Docker не установлен на системе.")
            return False

        compose_cmd = self._get_compose_cmd()

        log_info("Остановка предыдущих контейнеров Docker...")
        try:
            run_command(compose_cmd + ["down", "--remove-orphans"], cwd=self.project_dir, check=False)
            run_command(compose_cmd + ["-p", "spectre-panel", "down", "--remove-orphans"], cwd=self.project_dir, check=False)
            # Remove any lingering containers with conflicting fixed names from prior installs
            for cname in ("sentinel-db", "sentinel-panel", "spectre-panel", "spectre-db"):
                run_command(["docker", "rm", "-f", cname], check=False)
        except Exception:
            pass

        self.cleanup_conflicting_processes()
        self.migrate_database_volumes()

        log_info("Сборка и запуск контейнеров панели (docker compose up -d --build)...")

        docker_env: Dict[str, str] = {}
        if self.proxy_url:
            p_url = self.proxy_url
            if ":10818" in p_url:
                p_url = p_url.replace(":10818", ":10819")
            if p_url.startswith("socks5://") or p_url.startswith("socks4://"):
                p_url = "http://" + p_url.split("://", 1)[1]

            proxy_ok = False
            try:
                parsed = urllib.parse.urlparse(p_url)
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                with socket.create_connection((host, port), timeout=0.5):
                    proxy_ok = True
            except Exception:
                proxy_ok = False

            if proxy_ok:
                docker_env["http_proxy"] = p_url
                docker_env["https_proxy"] = p_url
                docker_env["HTTP_PROXY"] = p_url
                docker_env["HTTPS_PROXY"] = p_url
            else:
                log_info(f"Прокси {p_url} не отвечает или закрыт, сборка Docker будет выполнена напрямую.")

        try:
            run_command(compose_cmd + ["up", "-d", "--build"], cwd=self.project_dir, env=docker_env if docker_env else None, check=True)
            log_success("Контейнеры Docker успешно собраны и запущены!")
            self.cleanup_build_artifacts()
            return True
        except Exception as e:
            if docker_env:
                log_warn(f"Сборка Docker через прокси завершилась с ошибкой ({e}). Повтор напрямую...")
                try:
                    run_command(compose_cmd + ["up", "-d", "--build"], cwd=self.project_dir, env=None, check=True)
                    log_success("Контейнеры Docker успешно собраны и запущены (напрямую)!")
                    self.cleanup_build_artifacts()
                    return True
                except Exception as e_direct:
                    log_error(f"Ошибка запуска Docker Compose: {e_direct}")
                    return False
            log_error(f"Ошибка запуска Docker Compose: {e}")
            return False

    def stream_live_logs(self) -> None:
        """Attaches to live container log stream until interrupted by user (Ctrl+C)."""
        compose_cmd = self._get_compose_cmd()
        try:
            subprocess.run(compose_cmd + ["logs", "-f", "--tail=30", "sentinel-panel"], cwd=self.project_dir)
        except KeyboardInterrupt:
            pass
