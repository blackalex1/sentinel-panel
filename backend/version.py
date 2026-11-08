"""Sentinel Control Panel Version Definition."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PANEL_VERSION_FALLBACK = "0.0.8"


def _resolve_panel_version() -> str:
    # 1. Environment variable override (e.g., passed via Docker ARG/ENV)
    env_ver = os.getenv("PANEL_VERSION", "").strip().lstrip("v")
    if env_ver:
        return env_ver

    # 2. Check candidate locations for VERSION file
    candidates = [
        Path(__file__).resolve().parent.parent / "VERSION",  # project_root/VERSION
        Path(__file__).resolve().parent / "VERSION",         # backend/VERSION
        Path("/app/VERSION"),
        Path.cwd() / "VERSION",
    ]
    for v_path in candidates:
        if v_path.is_file():
            try:
                content = v_path.read_text(encoding="utf-8").strip().lstrip("v")
                if content:
                    return content
            except Exception:
                pass

    # 3. Detect from Git repository metadata if available (.git)
    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / ".git").exists():
        try:
            res = subprocess.run(
                ["git", "-c", "safe.directory=*", "describe", "--tags", "--abbrev=0"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                tag = res.stdout.strip().lstrip("v")
                if tag:
                    return tag
        except Exception:
            pass

    return PANEL_VERSION_FALLBACK


PANEL_VERSION: str = _resolve_panel_version()
