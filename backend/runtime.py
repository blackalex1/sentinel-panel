"""Panel process lifecycle and safe self-restart coordination."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from typing import List

logger = logging.getLogger(__name__)

_RESTART_LOCK = threading.Lock()
_RESTART_REQUESTED = False
_RESTART_SCHEDULED = False
_STARTED_FROM_MAIN = False


def mark_started_from_main() -> None:
    """Marks that the panel was started via backend.main entrypoint (enabling execv on bare metal)."""
    global _STARTED_FROM_MAIN
    _STARTED_FROM_MAIN = True


def is_restart_requested() -> bool:
    """Returns whether an in-process or container restart has been requested."""
    return _RESTART_REQUESTED


def is_running_in_docker() -> bool:
    """Detects whether the panel is running inside a Docker/OCI container."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
        if any(tok in data for tok in ("docker", "containerd", "kubepods", "lxc")):
            return True
    except Exception:
        pass
    return False


def stop_all_managed_cores() -> None:
    """Best-effort shutdown of managed proxy cores prior to process exit or execv."""
    for mod_name, fn_name in (
        ("backend.xray", "stop_xray"),
        ("backend.hysteria", "stop_hysteria"),
        ("backend.singbox", "stop_singbox"),
    ):
        try:
            mod = __import__(mod_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                fn()
        except Exception as e:
            logger.debug("Error stopping core via %s.%s: %s", mod_name, fn_name, e)


def build_exec_argv() -> List[str]:
    """Builds clean argv to re-exec the current Python process."""
    orig = getattr(sys, "orig_argv", None)
    if isinstance(orig, list) and len(orig) >= 2:
        exe_base = os.path.basename(orig[0]).lower()
        if "python" in exe_base:
            return [sys.executable] + list(orig[1:])
    if sys.argv and sys.argv[0].endswith(".py"):
        return [sys.executable] + list(sys.argv)
    return [sys.executable, "-m", "backend.main"]


def perform_execv_restart() -> None:
    """Replaces current OS process image cleanly so updated C-FFI libraries load from scratch."""
    argv = build_exec_argv()
    logger.info("Executing process replacement: %s", " ".join(argv))
    os.execv(argv[0], argv)


def _execute_restart(delay_seconds: float, reason: str) -> None:
    time.sleep(max(0.2, float(delay_seconds)))
    in_docker = is_running_in_docker()
    logger.info(
        "Initiating panel restart (%s, in_docker=%s, started_from_main=%s)...",
        reason,
        in_docker,
        _STARTED_FROM_MAIN,
    )

    try:
        if hasattr(signal, "SIGTERM") and os.name != "nt":
            os.kill(os.getpid(), signal.SIGTERM)
        else:
            stop_all_managed_cores()
            os._exit(0)
    except Exception as e:
        logger.warning("Graceful SIGTERM restart failed (%s), forcing clean core stop + exit...", e)
        stop_all_managed_cores()
        os._exit(0)

    # Watchdog: force clean exit/re-exec if uvicorn does not exit shortly after SIGTERM
    time.sleep(6.0)
    logger.warning("Panel process still alive 6s after SIGTERM (%s); forcing fallback restart...", reason)
    stop_all_managed_cores()
    if in_docker or not _STARTED_FROM_MAIN:
        os._exit(0)
    else:
        perform_execv_restart()


def schedule_panel_restart(delay_seconds: float = 1.2, reason: str = "core update") -> bool:
    """Schedules an asynchronous panel restart after returning the HTTP response."""
    global _RESTART_REQUESTED, _RESTART_SCHEDULED

    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return False

    with _RESTART_LOCK:
        _RESTART_REQUESTED = True
        if _RESTART_SCHEDULED:
            return True
        _RESTART_SCHEDULED = True

    t = threading.Thread(
        target=_execute_restart,
        args=(delay_seconds, reason),
        name="panel-restart-worker",
        daemon=True,
    )
    t.start()
    return True
