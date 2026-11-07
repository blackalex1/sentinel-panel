"""Docker Compose Manager for Sentinel Panel."""

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
    """Manages container lifecycle, BuildKit caching, and zero/minimal-downtime updates."""

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
            # 3. Удаление всех неиспользуемых слоев кэша сборщика старше 7 дней (168 часов)
            run_command(["docker", "builder", "prune", "-a", "-f", "--filter", "until=168h"], check=False)
        except Exception as e:
            log_warn(f"Не удалось выполнить docker builder prune: {e}")

    def rebuild_and_restart(self) -> bool:
        """Rebuilds Docker image in background and performs zero/minimal-downtime swap."""
        if not shutil.which("docker"):
            log_error("Docker не установлен на системе.")
            return False

        compose_cmd = self._get_compose_cmd()

        # 1. Setup build environment and proxy if available
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

        # 2. Phase 1: Background Build while existing container continues serving traffic
        log_info("Сборка обновленного Docker-образа (панель продолжает работу без даунтайма)...")
        build_cmd = compose_cmd + ["build", "sentinel-panel"]
        build_success = False

        try:
            run_command(build_cmd, cwd=self.project_dir, env=docker_env if docker_env else None, check=True)
            build_success = True
        except Exception as e:
            if docker_env:
                log_warn(f"Сборка Docker через прокси завершилась с ошибкой ({e}). Повтор напрямую...")
                try:
                    run_command(build_cmd, cwd=self.project_dir, env=None, check=True)
                    build_success = True
                except Exception as e_direct:
                    log_error(f"Ошибка сборки Docker Compose напрямую: {e_direct}")
                    log_warn("Предыдущая версия панели не останавливалась и продолжает работать.")
                    return False
            else:
                log_error(f"Ошибка сборки Docker Compose: {e}")
                log_warn("Предыдущая версия панели не останавливалась и продолжает работать.")
                return False

        if not build_success:
            return False

        log_success("Новый Docker-образ успешно собран!")

        # 4. Phase 2: Instant swap to newly built image (downtime: ~1-2 seconds)
        log_info("Переключение на новую версию контейнера (docker compose up -d)...")
        try:
            run_command(compose_cmd + ["up", "-d", "--remove-orphans"], cwd=self.project_dir, check=True)
            log_success("Контейнеры Docker успешно запущены с минимальным даунтаймом!")
            self.cleanup_build_artifacts()
            return True
        except Exception as e_up:
            log_warn(f"Быстрое переключение завершилось с предупреждением: {e_up}. Попытка восстановления...")
            try:
                self.cleanup_conflicting_processes()
                run_command(compose_cmd + ["up", "-d", "--force-recreate", "--remove-orphans"], cwd=self.project_dir, check=True)
                log_success("Контейнеры Docker успешно запущены (восстановлено)!")
                self.cleanup_build_artifacts()
                return True
            except Exception as e_retry:
                log_error(f"Критическая ошибка запуска Docker Compose: {e_retry}")
                return False

    def stream_live_logs(self) -> None:
        """Attaches to live container log stream until interrupted by user (Ctrl+C)."""
        compose_cmd = self._get_compose_cmd()
        try:
            subprocess.run(compose_cmd + ["logs", "-f", "--tail=30", "sentinel-panel"], cwd=self.project_dir)
        except KeyboardInterrupt:
            pass
