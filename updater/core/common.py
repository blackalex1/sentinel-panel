"""ProgressBar and re-exported common updater utilities."""

from __future__ import annotations

import sys
import time

from ..ui import (
    ANSI_REGEX,
    BLUE,
    BOLD,
    CYAN,
    DARK_GRAY,
    DIM,
    GRAY,
    GREEN,
    ITALIC,
    MAGENTA,
    RED,
    RESET,
    UNDERLINE,
    WHITE,
    YELLOW,
    check_root,
    ensure_unencrypted_dns,
    free_port,
    get_display_width,
    log_banner,
    log_error,
    log_info,
    log_step,
    log_success,
    log_warn,
    pad_center,
    run_command,
)


class ProgressBar:
    """Modern inline download progress bar with live speed, percentage, ETA, and spinner."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, filename: str, total_bytes: int = 0) -> None:
        self.filename = filename
        self.total_bytes = total_bytes
        self._downloaded_bytes = 0
        self._start_time = time.time()
        self.last_update_time = self._start_time
        self.last_bytes = 0
        self._current_speed = 0.0
        self.frame_idx = 0
        self.bar_width = 24
        self.is_tty = sys.stdout.isatty()

    def elapsed_seconds(self) -> float:
        """Returns elapsed download duration in seconds."""
        return max(0.001, time.time() - self._start_time)

    def get_downloaded_bytes(self) -> int:
        """Returns total bytes downloaded so far."""
        return self._downloaded_bytes

    def get_current_speed(self) -> float:
        """Returns smoothed current download speed in bytes/sec."""
        return self._current_speed

    def stats_inputs(self) -> tuple[int, float, float]:
        """Returns (downloaded_bytes, start_time, current_speed) for stats calculation."""
        return self._downloaded_bytes, self._start_time, self._current_speed

    def update(self, chunk_size: int) -> None:
        """Updates downloaded bytes and renders progress."""
        self._downloaded_bytes += chunk_size
        now = time.time()
        dt = now - self.last_update_time

        if dt >= 0.08 or (self.total_bytes > 0 and self._downloaded_bytes >= self.total_bytes):
            db = self._downloaded_bytes - self.last_bytes
            if dt > 0:
                self._current_speed = 0.7 * self._current_speed + 0.3 * (db / dt)
            self.last_update_time = now
            self.last_bytes = self._downloaded_bytes
            self.render()

    def render(self) -> None:
        """Renders live single-line progress bar."""
        if not self.is_tty:
            return

        spinner = self.SPINNER_FRAMES[self.frame_idx % len(self.SPINNER_FRAMES)]
        self.frame_idx += 1

        elapsed = self.elapsed_seconds()
        avg_speed = self._downloaded_bytes / elapsed
        speed = self._current_speed if self._current_speed > 0 else avg_speed

        if speed >= 1024 * 1024:
            speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
        else:
            speed_str = f"{speed / 1024:.1f} KB/s"

        cur_mb = self._downloaded_bytes / (1024 * 1024)

        if self.total_bytes > 0:
            pct = min(100.0, (self._downloaded_bytes / self.total_bytes) * 100.0)
            filled = int(self.bar_width * (pct / 100.0))
            bar = "█" * filled + "░" * (self.bar_width - filled)
            tot_mb = self.total_bytes / (1024 * 1024)

            remaining_bytes = max(0, self.total_bytes - self._downloaded_bytes)
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
            elapsed = self.elapsed_seconds()
            avg_speed = self._downloaded_bytes / elapsed
            speed_str = f"{avg_speed / (1024 * 1024):.1f} MB/s" if avg_speed >= 1024 * 1024 else f"{avg_speed / 1024:.1f} KB/s"
            size_mb = self._downloaded_bytes / (1024 * 1024)
            log_success(f"Загружено: {BOLD}{self.filename}{RESET} ({size_mb:.2f} MB) [{YELLOW}{speed_str}{RESET}]")
