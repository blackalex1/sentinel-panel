"""Host agent command dispatch facade over system monitoring, optimizations, and WARP controls."""

from typing import Any, Callable

from agent.monitor import get_system_stats
from agent.optimizations import (
    apply_network_optimizations,
    enable_bbr,
    get_bbr_status,
    get_ipv6_status,
    get_optimization_status,
    set_ipv6_disabled,
)
from agent.warp import (
    connect_warp,
    disconnect_warp,
    get_warp_status,
    install_warp,
    register_warp,
    uninstall_warp,
)


def _tuple_action(fn: Callable[..., tuple[bool, str]], *args: Any) -> dict[str, Any]:
    success, msg = fn(*args)
    return {"success": success, "msg": msg}


_ACTION_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "get_bbr_status": lambda req: {"success": True, "bbr_enabled": get_bbr_status()},
    "enable_bbr": lambda req: _tuple_action(enable_bbr),
    "get_system_stats": lambda req: get_system_stats(),
    "get_optimization_status": lambda req: {"success": True, "optimized": get_optimization_status()},
    "apply_optimizations": lambda req: _tuple_action(apply_network_optimizations),
    "get_ipv6_status": lambda req: {
        "success": True,
        "ipv6_disabled": (s := get_ipv6_status()).get("ipv6_disabled", False),
        "supported": s.get("supported", True),
    },
    "set_ipv6_disabled": lambda req: _tuple_action(set_ipv6_disabled, req.get("disable", True)),
    "get_warp_status": lambda req: get_warp_status(),
    "install_warp": lambda req: _tuple_action(install_warp),
    "register_warp": lambda req: _tuple_action(register_warp, req.get("license_key")),
    "connect_warp": lambda req: _tuple_action(connect_warp),
    "disconnect_warp": lambda req: _tuple_action(disconnect_warp),
    "uninstall_warp": lambda req: _tuple_action(uninstall_warp),
}


def dispatch_agent_action(action: str | None, request: dict[str, Any]) -> dict[str, Any] | None:
    """Executes a host-level agent action and returns the JSON-serializable response, or None if unhandled."""
    handler = _ACTION_HANDLERS.get(action or "")
    return handler(request) if handler is not None else None


__all__ = [
    "dispatch_agent_action",
    "get_system_stats",
    "get_bbr_status",
    "enable_bbr",
    "get_optimization_status",
    "apply_network_optimizations",
    "get_ipv6_status",
    "set_ipv6_disabled",
    "get_warp_status",
    "install_warp",
    "register_warp",
    "connect_warp",
    "disconnect_warp",
    "uninstall_warp",
]
