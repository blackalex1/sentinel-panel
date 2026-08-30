"""Git Codebase Updater Module with multi-mirror fallback and changelog formatter."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Dict, List, Optional

from .common import (
    BOLD,
    CYAN,
    DARK_GRAY,
    DIM,
    GREEN,
    RED,
    RESET,
    WHITE,
    YELLOW,
    log_error,
    log_info,
    log_success,
    log_warn,
    run_command,
)


class GitManager:
    """Manages Git updates with automatic multi-mirror fallback and changelog visualization."""

    def __init__(self, project_dir: str, repo_url: Optional[str] = None, proxy_url: Optional[str] = None) -> None:
        self.project_dir = project_dir
        self.repo_url = repo_url
        self.proxy_url = proxy_url

    def _get_candidate_remotes(self) -> List[str]:
        """Builds a list of fetch sources including official URL and CDN mirrors."""
        remotes = ["origin"]
        if self.repo_url:
            remotes.append(self.repo_url)
            remotes.append(f"https://gh-proxy.com/{self.repo_url}")
            remotes.append(f"https://ghfast.top/{self.repo_url}")
            remotes.append(f"https://gh.ddlc.top/{self.repo_url}")
        return remotes

    def update_codebase(self, silent_if_uptodate: bool = False) -> bool:
        """Pulls latest updates from Git origin or fallback mirrors. Returns True if new commits were pulled."""
        if not shutil.which("git") or not os.path.isdir(os.path.join(self.project_dir, ".git")):
            if not silent_if_uptodate:
                log_warn("Директория .git не найдена. Пропуск обновления через Git.")
            return False

        if not silent_if_uptodate:
            log_info("Проверка и получение обновлений Git...")

        # Stash local changes if any
        stashed = False
        try:
            status = run_command(["git", "status", "--porcelain"], cwd=self.project_dir, capture=True, check=False).stdout.strip()
            if status:
                if not silent_if_uptodate:
                    log_warn("Обнаружены локальные изменения. Сохранение во временный stash...")
                run_command(["git", "stash", "push", "-m", "sentinel-updater-autostash"], cwd=self.project_dir, check=False)
                stashed = True
        except Exception:
            pass

        git_env: Dict[str, str] = {}
        git_config_args: List[str] = ["-c", "safe.directory=*"]
        if self.proxy_url:
            proxy_val = self.proxy_url
            if proxy_val.startswith("socks5://"):
                proxy_val = "socks5h://" + proxy_val[len("socks5://"):]
            git_env["http_proxy"] = proxy_val
            git_env["https_proxy"] = proxy_val
            git_env["ALL_PROXY"] = proxy_val
            git_config_args.extend(["-c", f"http.proxy={proxy_val}", "-c", "http.sslVerify=false"])

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
        for remote in self._get_candidate_remotes():
            try:
                fetch_cmd = ["git"] + git_config_args + ["fetch", remote, branch]
                res = run_command(fetch_cmd, cwd=self.project_dir, env=git_env, capture=True, check=False, timeout=12.0)
                if res.returncode == 0:
                    run_command(["git", "reset", "--hard", "FETCH_HEAD"], cwd=self.project_dir, check=True)
                    pull_success = True
                    break
            except Exception:
                continue

        if not pull_success:
            if not silent_if_uptodate:
                log_warn("Не удалось загрузить новые коммиты из Git (используется текущая локальная версия).")
            if stashed:
                try:
                    run_command(["git", "stash", "pop"], cwd=self.project_dir, check=False)
                except Exception:
                    pass
            return False

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
            log_success(f"Кодовая база обновлена: {BOLD}{old_commit[:7]} → {new_commit[:7]}{RESET}")
            self.display_changelog(from_commit=old_commit, to_commit=new_commit)
            return True
        else:
            if not silent_if_uptodate:
                log_success("Кодовая база уже актуальна (Up to date).")
                self.display_changelog(max_commits=3)
            return False

    def display_changelog(
        self,
        from_commit: Optional[str] = None,
        to_commit: Optional[str] = None,
        max_commits: int = 5,
    ) -> None:
        """Visualizes commit log and colorized git diff statistics with added/deleted line counts."""
        if not shutil.which("git") or not os.path.isdir(os.path.join(self.project_dir, ".git")):
            return

        try:
            current_head = run_command(
                ["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"],
                cwd=self.project_dir,
                capture=True,
                check=False,
            ).stdout.strip()

            if from_commit and to_commit and from_commit != to_commit:
                print(f"\n  {CYAN}📝 Список изменений ({BOLD}{from_commit[:7]} → {to_commit[:7]}{RESET}{CYAN}):{RESET}")
                log_cmd = [
                    "git", "-c", "safe.directory=*", "log",
                    "--pretty=format:%h %s (%cr)",
                    f"{from_commit}..{to_commit}"
                ]
                diff_cmd = [
                    "git", "-c", "safe.directory=*", "diff",
                    "--stat", "--color=always",
                    f"{from_commit}..{to_commit}"
                ]
            else:
                print(f"\n  {CYAN}📝 Недавние изменения в кодовой базе (текущая: {BOLD}{current_head}{RESET}{CYAN}):{RESET}")
                log_cmd = [
                    "git", "-c", "safe.directory=*", "log",
                    f"-n", str(max_commits),
                    "--pretty=format:%h %s (%cr)"
                ]
                diff_cmd = [
                    "git", "-c", "safe.directory=*", "show",
                    "--stat", "--color=always", "--format=",
                    "HEAD"
                ]

            commits_out = run_command(log_cmd, cwd=self.project_dir, capture=True, check=False).stdout.strip()
            if commits_out:
                for line in commits_out.splitlines():
                    if line.strip():
                        parts = line.strip().split(" ", 1)
                        h = parts[0]
                        rest = parts[1] if len(parts) > 1 else ""
                        print(f"    • {YELLOW}{BOLD}{h}{RESET} {rest}")

            diff_out = run_command(diff_cmd, cwd=self.project_dir, capture=True, check=False).stdout.strip()
            if diff_out:
                print(f"\n  {WHITE}{BOLD}📊 Статистика изменений файлов ({GREEN}+{RESET}/{RED}-{RESET}):{RESET}")
                for line in diff_out.splitlines():
                    print(f"    {line}")
            print("")
        except Exception:
            pass
