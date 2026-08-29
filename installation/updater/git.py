"""Git Codebase Updater Module for Sentinel Panel."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Dict, List, Optional

from .common import (
    BOLD,
    GREEN,
    RESET,
    YELLOW,
    log_error,
    log_info,
    log_success,
    log_warn,
    run_command,
)


class GitManager:
    """Manages Git updates with automatic multi-mirror fallback."""

    REPO_URL = "https://github.com/blackalex1/sentinel-panel.git"

    def __init__(self, project_dir: str, proxy_url: Optional[str] = None) -> None:
        self.project_dir = project_dir
        self.proxy_url = proxy_url

    def update_codebase(self) -> bool:
        """Pulls latest updates from Git origin or fallback CDN mirrors."""
        if not shutil.which("git") or not os.path.isdir(os.path.join(self.project_dir, ".git")):
            log_warn("Директория .git не найдена. Пропуск этапа обновления через Git.")
            return True

        log_info("Получение последних обновлений из Git...")

        # Stash any local uncommitted changes to prevent conflicts
        stashed = False
        try:
            status = run_command(["git", "status", "--porcelain"], cwd=self.project_dir, capture=True, check=False).stdout.strip()
            if status:
                log_warn("Обнаружены локальные изменения. Сохранение во временный stash...")
                run_command(["git", "stash", "push", "-m", "sentinel-updater-autostash"], cwd=self.project_dir, check=False)
                stashed = True
        except Exception:
            pass

        git_env: Dict[str, str] = {}
        git_config_args: List[str] = []
        if self.proxy_url:
            proxy_val = self.proxy_url
            if proxy_val.startswith("socks5://"):
                proxy_val = "socks5h://" + proxy_val[len("socks5://") :]
            git_env["http_proxy"] = proxy_val
            git_env["https_proxy"] = proxy_val
            git_env["ALL_PROXY"] = proxy_val
            git_config_args = ["-c", f"http.proxy={proxy_val}", "-c", "http.sslVerify=false"]

        candidate_remotes = [
            "origin",
            self.REPO_URL,
            "https://gh-proxy.com/https://github.com/blackalex1/sentinel-panel.git",
            "https://ghfast.top/https://github.com/blackalex1/sentinel-panel.git",
            "https://gh.ddlc.top/https://github.com/blackalex1/sentinel-panel.git",
        ]

        # Determine current branch
        branch = "main"
        try:
            b_out = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.project_dir, capture=True, check=False).stdout.strip()
            if b_out and b_out != "HEAD":
                branch = b_out
        except Exception:
            pass

        old_commit = ""
        try:
            old_commit = run_command(["git", "rev-parse", "HEAD"], cwd=self.project_dir, capture=True, check=False).stdout.strip()
        except Exception:
            pass

        pull_success = False
        for remote in candidate_remotes:
            try:
                fetch_cmd = ["git"] + git_config_args + ["fetch", remote, branch]
                res = run_command(fetch_cmd, cwd=self.project_dir, env=git_env, capture=True, check=False, timeout=12)
                if res.returncode == 0:
                    run_command(["git", "reset", "--hard", "FETCH_HEAD"], cwd=self.project_dir, capture=True, check=True)
                    pull_success = True
                    break
            except Exception:
                continue

        if not pull_success:
            log_error("Не удалось получить обновления из Git ни с одного источника.")
            if stashed:
                try:
                    run_command(["git", "stash", "pop"], cwd=self.project_dir, check=False)
                except Exception:
                    pass
            return False

        # Pop stash if it was created
        if stashed:
            try:
                run_command(["git", "stash", "pop"], cwd=self.project_dir, check=False)
            except Exception:
                pass

        new_commit = ""
        try:
            new_commit = run_command(["git", "rev-parse", "HEAD"], cwd=self.project_dir, capture=True, check=False).stdout.strip()
        except Exception:
            pass

        if old_commit and new_commit and old_commit != new_commit:
            log_success(f"Кодовая база успешно обновлена: {BOLD}{old_commit[:7]} -> {new_commit[:7]}{RESET}")
            try:
                log_diff = run_command(["git", "diff", "--stat", f"{old_commit}..{new_commit}"], cwd=self.project_dir, capture=True, check=False).stdout.strip()
                if log_diff:
                    print(f"\n{log_diff}\n")
            except Exception:
                pass
        else:
            log_success("Кодовая база уже актуальна (Already up to date).")

        return True
