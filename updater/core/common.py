"""Common utilities: ANSI formatting, modern box styling, process runner, and system checks."""

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import unicodedata
from typing import Dict, List, Optional, Union

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


class ProgressBar:
    """Modern inline download progress bar with live speed, percentage, ETA, and spinner."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, filename: str, total_bytes: int = 0) -> None:
        self.filename = filename
        self.total_bytes = total_bytes
        self.downloaded_bytes = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_bytes = 0
        self.current_speed = 0.0
        self.frame_idx = 0
        self.bar_width = 24
        self.is_tty = sys.stdout.isatty()

    def update(self, chunk_size: int) -> None:
        """Updates downloaded bytes and renders progress."""
        self.downloaded_bytes += chunk_size
        now = time.time()
        dt = now - self.last_update_time

        if dt >= 0.08 or (self.total_bytes > 0 and self.downloaded_bytes >= self.total_bytes):
            db = self.downloaded_bytes - self.last_bytes
            if dt > 0:
                self.current_speed = 0.7 * self.current_speed + 0.3 * (db / dt)
            self.last_update_time = now
            self.last_bytes = self.downloaded_bytes
            self.render()

    def render(self) -> None:
        """Renders live single-line progress bar."""
        if not self.is_tty:
            return

        spinner = self.SPINNER_FRAMES[self.frame_idx % len(self.SPINNER_FRAMES)]
        self.frame_idx += 1

        elapsed = max(0.001, time.time() - self.start_time)
        avg_speed = self.downloaded_bytes / elapsed
        speed = self.current_speed if self.current_speed > 0 else avg_speed

        if speed >= 1024 * 1024:
            speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
        else:
            speed_str = f"{speed / 1024:.1f} KB/s"

        cur_mb = self.downloaded_bytes / (1024 * 1024)

        if self.total_bytes > 0:
            pct = min(100.0, (self.downloaded_bytes / self.total_bytes) * 100.0)
            filled = int(self.bar_width * (pct / 100.0))
            bar = "█" * filled + "░" * (self.bar_width - filled)
            tot_mb = self.total_bytes / (1024 * 1024)

            remaining_bytes = max(0, self.total_bytes - self.downloaded_bytes)
            eta_sec = int(remaining_bytes / speed) if speed > 0 else 0
            eta_str = f"{eta_sec}s" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s"

            line = (
                f"\r  {CYAN}{spinner}{RESET} "
                f"[{GREEN}{bar}{RESET}] "
                f"{BOLD}{pct:5.1f}%{RESET} "
                f"({cur_mb:4.1f}/{tot_mb:4.1f} MB) • "
                f"{YELLOW}{speed_str:>9}{RESET} • "
                f"ETA {DARK_GRAY}{eta_str:<4}{RESET}"
            )
        else:
            line = (
                f"\r  {CYAN}{spinner}{RESET} "
                f"Загрузка: {BOLD}{cur_mb:4.1f} MB{RESET} • "
                f"{YELLOW}{speed_str:>9}{RESET}"
            )

        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self, success: bool = True) -> None:
        """Clears progress line and outputs final completion message."""
        if self.is_tty:
            sys.stdout.write("\r" + " " * 95 + "\r")
            sys.stdout.flush()

        if success:
            elapsed = max(0.001, time.time() - self.start_time)
            avg_speed = self.downloaded_bytes / elapsed
            speed_str = f"{avg_speed / (1024 * 1024):.1f} MB/s" if avg_speed >= 1024 * 1024 else f"{avg_speed / 1024:.1f} KB/s"
            size_mb = self.downloaded_bytes / (1024 * 1024)
            log_success(f"Загружено: {BOLD}{self.filename}{RESET} ({size_mb:.2f} MB) [{YELLOW}{speed_str}{RESET}]")


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
