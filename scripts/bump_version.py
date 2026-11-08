#!/usr/bin/env python3
"""Sentinel Panel Version Bumper Utility.

Synchronizes version across VERSION, backend/version.py, and Dockerfile,
with optional git commit and tagging.

Usage:
    python scripts/bump_version.py 0.0.9
    python scripts/bump_version.py 1.0.0 --tag
    python scripts/bump_version.py 1.0.0 --tag --push
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize and bump Sentinel Panel version.")
    parser.add_argument("version", help="Target version string (e.g. 0.0.9 or v1.0.0)")
    parser.add_argument("--tag", action="store_true", help="Create a git tag (e.g. v0.0.9)")
    parser.add_argument("--push", action="store_true", help="Push commit and tag to git remote")
    args = parser.parse_args()

    clean_ver = args.version.strip().lstrip("v")
    if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$", clean_ver):
        print(f"[-] Invalid version format: '{args.version}'. Expected format like 0.0.9 or 1.0.0", file=sys.stderr)
        return 1

    repo_dir = Path(__file__).resolve().parent.parent

    # 1. Update VERSION file
    version_file = repo_dir / "VERSION"
    version_file.write_text(f"{clean_ver}\n", encoding="utf-8")
    print(f"[+] Updated VERSION -> {clean_ver}")

    # 2. Update backend/version.py
    py_version_file = repo_dir / "backend" / "version.py"
    if py_version_file.is_file():
        content = py_version_file.read_text(encoding="utf-8")
        updated = re.sub(
            r'PANEL_VERSION_FALLBACK\s*=\s*["\'].*?["\']',
            f'PANEL_VERSION_FALLBACK = "{clean_ver}"',
            content,
        )
        py_version_file.write_text(updated, encoding="utf-8")
        print(f"[+] Updated backend/version.py (PANEL_VERSION_FALLBACK -> {clean_ver})")

    # 3. Update Dockerfile ARG PANEL_VERSION
    dockerfile = repo_dir / "Dockerfile"
    if dockerfile.is_file():
        content = dockerfile.read_text(encoding="utf-8")
        updated = re.sub(
            r'ARG PANEL_VERSION\s*=\s*["\'].*?["\']',
            f'ARG PANEL_VERSION="{clean_ver}"',
            content,
        )
        dockerfile.write_text(updated, encoding="utf-8")
        print(f"[+] Updated Dockerfile (ARG PANEL_VERSION -> {clean_ver})")

    # 4. Optional Git Commit and Tag
    if args.tag or args.push:
        tag_name = f"v{clean_ver}"
        commit_msg = f"chore(release): bump panel version to {clean_ver}"
        print(f"[+] Committing changes: {commit_msg}...")
        subprocess.run(["git", "add", "VERSION", "backend/version.py", "Dockerfile"], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_dir, check=True)

        print(f"[+] Creating git tag: {tag_name}...")
        subprocess.run(["git", "tag", "-a", tag_name, "-m", f"Release Sentinel Control Panel {tag_name}"], cwd=repo_dir, check=True)

        if args.push:
            print("[+] Pushing commit and tag to git remote origin...")
            subprocess.run(["git", "push", "origin", "HEAD"], cwd=repo_dir, check=True)
            subprocess.run(["git", "push", "origin", tag_name], cwd=repo_dir, check=True)
            print(f"[✔] Successfully pushed {tag_name} to remote. GitHub Actions release workflow will trigger.")

    print(f"\n[✔] Version successfully synchronized to {clean_ver}!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
