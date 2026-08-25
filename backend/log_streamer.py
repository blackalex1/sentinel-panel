"""
log_streamer.py — Pure high-speed in-memory log streaming bus for all VPN cores.

Architecture:
  - Each VPN core (xray, hysteria, singbox) has an in-memory worker thread that
    pops real-time stdout/stderr lines from the sentinel-core Go supervisor pipes.
  - That thread calls push_log_line(core, line) with zero disk I/O and zero delay.
  - Browser SSE / WebSocket connections subscribe(core) to get an asyncio.Queue;
    they receive lines instantly as they are emitted by the core engine.
  - The last HISTORY_SIZE lines are stored in memory in a deque so newly-opened
    browser tabs get recent history immediately before live streaming starts.
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
    """Called by streamer threads when a new log line arrives from sentinel-core."""
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
    """Returns a snapshot of recent lines from in-memory ring buffer."""
    with _lock:
        hist = list(_history[core])
        if hist:
            return hist

    try:
        from backend.sentinel_core_bridge import get_in_memory_core_logs
        mem_logs = get_in_memory_core_logs(core, HISTORY_SIZE)
        if mem_logs:
            with _lock:
                for l in mem_logs:
                    _history[core].append(l)
            return mem_logs
    except Exception:
        pass

    return []


_tail_threads_started = False

def _core_log_worker(core: CoreName):
    """High-speed worker that drains in-memory pipes from sentinel-core."""
    import time
    from backend.sentinel_core_bridge import pop_core_log_line

    while True:
        try:
            had_activity = False
            # Batch drain all available lines in the in-memory queue
            while True:
                line = pop_core_log_line(core, timeout_ms=0)
                if not line:
                    break
                had_activity = True
                push_log_line(core, line)

            if had_activity:
                time.sleep(0.005)
            else:
                time.sleep(0.03)
        except Exception:
            time.sleep(0.2)


def ensure_log_tailers():
    """Ensures background in-memory log streamer threads are active."""
    global _tail_threads_started
    with _lock:
        if _tail_threads_started:
            return
        _tail_threads_started = True

    t1 = threading.Thread(target=_core_log_worker, args=("xray",), daemon=True, name="stream-xray")
    t2 = threading.Thread(target=_core_log_worker, args=("hysteria",), daemon=True, name="stream-hysteria")
    t3 = threading.Thread(target=_core_log_worker, args=("singbox",), daemon=True, name="stream-singbox")
    t1.start()
    t2.start()
    t3.start()


def subscribe(core: CoreName) -> asyncio.Queue:
    """Creates and registers an asyncio.Queue for a new SSE / WebSocket client."""
    ensure_log_tailers()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with _lock:
        _subscribers[core].add(q)
    return q


def unsubscribe(core: CoreName, q: asyncio.Queue) -> None:
    """Removes the queue when the SSE / WebSocket client disconnects."""
    with _lock:
        _subscribers[core].discard(q)
