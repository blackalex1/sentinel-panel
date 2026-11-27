"""UI helpers, ANSI colors, boxed banners, and system command runners for Sentinel Updater."""

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import unicodedata
from typing import Dict, List, Optional, Union

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ANSI Colors & Styles
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# Standard Colors
RED = "\033[38;5;196m"
GREEN = "\033[38;5;46m"
YELLOW = "\033[38;5;226m"
BLUE = "\033[38;5;39m"
MAGENTA = "\033[38;5;201m"
CYAN = "\033[38;5;51m"
WHITE = "\033[38;5;231m"
GRAY = "\033[38;5;245m"
DARK_GRAY = "\033[38;5;238m"

ANSI_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def get_display_width(text: str) -> int:
    """Calculates visible terminal column display width accurately, handling emojis and East Asian characters."""
    clean = ANSI_REGEX.sub("", text)
    width = 0
    for char in clean:
        if char == "\ufe0f":
            continue
        eaw = unicodedata.east_asian_width(char)
        if eaw in ("W", "F"):
            width += 2
        elif 0x1F300 <= ord(char) <= 0x1FAFF:
            width += 2
        elif unicodedata.category(char) in ("Mn", "Me", "Cf"):
            continue
        else:
            width += 1
    return width


def pad_center(text: str, total_width: int) -> str:
    """Centers text accurately based on visible terminal column width."""
    d_width = get_display_width(text)
    if d_width >= total_width:
        return text
    total_padding = total_width - d_width
    left_padding = total_padding // 2
    right_padding = total_padding - left_padding
    return f"{' ' * left_padding}{text}{' ' * right_padding}"


def log_info(msg: str) -> None:
    """Informative status message."""
    print(f"  {BLUE}ℹ{RESET} {msg}", flush=True)


def log_success(msg: str) -> None:
    """Success status message."""
    print(f"  {GREEN}✔{RESET} {msg}", flush=True)


def log_warn(msg: str) -> None:
    """Warning status message."""
    print(f"  {YELLOW}⚠{RESET} {msg}", flush=True)


def log_error(msg: str) -> None:
    """Error status message."""
    print(f"  {RED}✖{RESET} {msg}", flush=True)


def log_step(step_num: int, total_steps: int, title: str) -> None:
    """Renders a visually appealing step header."""
    badge = f"{CYAN}[{step_num}/{total_steps}]{RESET}"
    print(f"\n{badge} {BOLD}{WHITE}{title}{RESET}")
    print(f"  {DARK_GRAY}{'─' * 50}{RESET}")


def log_banner(title: str, subtitle: Optional[str] = None) -> None:
    """Renders a modern boxed banner with pixel-perfect right border alignment."""
    t_clean = title.replace("\ufe0f", "")
    s_clean = (subtitle or "").replace("\ufe0f", "") if subtitle else None

    t_width = get_display_width(t_clean)
    s_width = get_display_width(s_clean or "") if s_clean else 0
    content_width = max(t_width, s_width) + 6
    total_width = max(content_width, 58)
    inner_width = total_width - 4

    border_top = f"╭{'─' * (total_width - 2)}╮"
    border_bot = f"╰{'─' * (total_width - 2)}╯"

    print(f"\n{CYAN}{border_top}{RESET}")
    print(f"{CYAN}│{RESET} {BOLD}{WHITE}{pad_center(t_clean, inner_width)}{RESET} {CYAN}│{RESET}")
    if s_clean:
        print(f"{CYAN}│{RESET} {DIM}{pad_center(s_clean, inner_width)}{RESET} {CYAN}│{RESET}")
    print(f"{CYAN}{border_bot}{RESET}\n", flush=True)


def check_root() -> None:
    """Verifies that the script is executed with root/sudo privileges on Linux/Unix systems."""
    if platform.system() != "Windows":
        if os.geteuid() != 0:
            log_error("Для обновления требуются права root (sudo).")
            print(f"\n  {YELLOW}Пожалуйста, запустите:{RESET} {BOLD}sudo ./update.sh{RESET}\n")
            sys.exit(1)


def ensure_unencrypted_dns() -> None:
    """Configures fallback DNS resolution on Linux/Unix systems if needed."""
    if platform.system() == "Windows":
        return
    try:
        socket.gethostbyname("github.com")
    except Exception:
        try:
            with open("/etc/resolv.conf", "a") as f:
                f.write("\nnameserver 1.1.1.1\nnameserver 8.8.8.8\n")
        except Exception:
            pass


def free_port(port: int) -> None:
    """Kills any stale process binding to the specified TCP port."""
    if platform.system() == "Windows":
        return

    try:
        if shutil.which("fuser"):
            subprocess.run(["fuser", "-k", "-9", f"{port}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    try:
        if shutil.which("lsof"):
            out = subprocess.check_output(["lsof", "-t", f"-i:{port}"], stderr=subprocess.DEVNULL).decode().strip()
            for pid_str in out.split():
                if pid_str.isdigit():
                    try:
                        os.kill(int(pid_str), signal.SIGKILL)
                    except Exception:
                        pass
    except Exception:
        pass

    if port in (10818, 10819):
        try:
            subprocess.run(["pkill", "-9", "-f", "_failover_"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "singbox_failover"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "xray_failover"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def run_command(
    cmd: Union[List[str], str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture: bool = False,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """Runs shell/system command with robust timeout and output capturing."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    shell = isinstance(cmd, str)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        shell=shell,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )
