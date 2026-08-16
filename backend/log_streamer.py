"""
log_streamer.py — shared log streaming bus for all VPN cores.

Architecture:
  - Each VPN core (xray, hysteria, singbox) has a background thread that reads
    its log file in real-time (tail -f style).
  - That thread calls push_log_line(core, line) whenever a new line arrives.
  - Browser SSE connections call subscribe(core) to get an asyncio.Queue; they
    receive lines as they are pushed, without polling.
  - The last HISTORY_SIZE lines are buffered in a deque so a freshly-opened
    browser tab gets recent history immediately before live streaming starts.

This eliminates the 2-second poll + 150-line full JSON payload per tick.
"""

import asyncio
import threading
from collections import deque
from typing import Literal

CoreName = Literal["xray", "hysteria", "singbox"]

HISTORY_SIZE = 200  # lines to keep in memory per core

# Per-core: deque of recent lines + set of subscriber queues
_lock = threading.Lock()

_history: dict[CoreName, deque] = {
    "xray":     deque(maxlen=HISTORY_SIZE),
    "hysteria": deque(maxlen=HISTORY_SIZE),
    "singbox":  deque(maxlen=HISTORY_SIZE),
}

# Each subscriber is an asyncio.Queue living in its own event-loop thread
_subscribers: dict[CoreName, set] = {
    "xray":     set(),
    "hysteria": set(),
    "singbox":  set(),
}


def push_log_line(core: CoreName, line: str) -> None:
    """Called by tail threads (sync context) when a new log line arrives."""
    line = line.rstrip("\n\r")
    if not line:
        return

    with _lock:
        _history[core].append(line)
        dead = set()
        for q in _subscribers[core]:
            try:
                q.put_nowait(line)
            except Exception:
                dead.add(q)
        _subscribers[core] -= dead


def clear_history(core: CoreName) -> None:
    """Clears buffered in-memory lines in Python log_streamer and drains subscriber queues."""
    with _lock:
        if core in _history:
            _history[core].clear()
        if core in _subscribers:
            for q in list(_subscribers[core]):
                while not q.empty():
                    try:
                        q.get_nowait()
                    except Exception:
                        break


def get_history(core: CoreName) -> list[str]:
    """Returns a snapshot of recent lines for the initial SSE burst."""
    with _lock:
        hist = list(_history[core])
        if hist:
            return hist

    try:
        from backend.sentinel_core_bridge import get_in_memory_core_logs, get_core_logs
        # 1. Try in-memory ring buffer from sentinel-core
        mem_logs = get_in_memory_core_logs(core, HISTORY_SIZE)
        if mem_logs:
            with _lock:
                for l in mem_logs:
                    _history[core].append(l)
            return mem_logs

        # 2. Fall back to file logs
        from backend.config import XRAY_LOG_PATH, HYSTERIA_LOG_PATH, SINGBOX_LOG_PATH
        path_map = {
            "xray": XRAY_LOG_PATH,
            "hysteria": HYSTERIA_LOG_PATH,
            "singbox": SINGBOX_LOG_PATH
        }
        log_path = path_map.get(core)
        if log_path and log_path.exists():
            lines = get_core_logs(str(log_path), HISTORY_SIZE)
            if lines:
                with _lock:
                    for l in lines:
                        _history[core].append(l)
                return lines
    except Exception:
        pass

    return []


_tail_threads_started = False

def _tail_file_worker(core: CoreName, get_path_fn):
    import time
    from backend.sentinel_core_bridge import pop_core_log_line
    last_pos = 0
    while True:
        try:
            # 1. High-speed in-memory OS pipe streaming from sentinel-core
            line = pop_core_log_line(core, timeout_ms=50)
            if line:
                push_log_line(core, line)
                if core == "xray":
                    try:
                        from backend.client_alerts import process_xray_log_line
                        process_xray_log_line(line)
                    except Exception:
                        pass
                continue

            # 2. File tail fallback
            log_path = get_path_fn()
            if log_path and log_path.exists():
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(last_pos)
                    f_line = f.readline()
                    if f_line:
                        last_pos = f.tell()
                        push_log_line(core, f_line)
                        if core == "xray":
                            try:
                                from backend.client_alerts import process_xray_log_line
                                process_xray_log_line(f_line)
                            except Exception:
                                pass
                    else:
                        if log_path.exists() and log_path.stat().st_size < last_pos:
                            f.seek(0)
                            last_pos = 0
            time.sleep(0.02)
        except Exception:
            time.sleep(0.5)

def ensure_log_tailers():
    global _tail_threads_started
    with _lock:
        if _tail_threads_started:
            return
        _tail_threads_started = True

    from backend.config import XRAY_LOG_PATH, HYSTERIA_LOG_PATH, SINGBOX_LOG_PATH
    t1 = threading.Thread(target=_tail_file_worker, args=("xray", lambda: XRAY_LOG_PATH), daemon=True, name="tail-xray")
    t2 = threading.Thread(target=_tail_file_worker, args=("hysteria", lambda: HYSTERIA_LOG_PATH), daemon=True, name="tail-hysteria")
    t3 = threading.Thread(target=_tail_file_worker, args=("singbox", lambda: SINGBOX_LOG_PATH), daemon=True, name="tail-singbox")
    t1.start()
    t2.start()
    t3.start()


def subscribe(core: CoreName) -> asyncio.Queue:
    """Creates and registers an asyncio.Queue for a new SSE client."""
    ensure_log_tailers()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with _lock:
        _subscribers[core].add(q)
    return q


def unsubscribe(core: CoreName, q: asyncio.Queue) -> None:
    """Removes the queue when the SSE client disconnects."""
    with _lock:
        _subscribers[core].discard(q)
