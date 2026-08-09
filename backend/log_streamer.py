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


def get_history(core: CoreName) -> list[str]:
    """Returns a snapshot of recent lines for the initial SSE burst."""
    with _lock:
        return list(_history[core])


def subscribe(core: CoreName) -> asyncio.Queue:
    """Creates and registers an asyncio.Queue for a new SSE client."""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    with _lock:
        _subscribers[core].add(q)
    return q


def unsubscribe(core: CoreName, q: asyncio.Queue) -> None:
    """Removes the queue when the SSE client disconnects."""
    with _lock:
        _subscribers[core].discard(q)
