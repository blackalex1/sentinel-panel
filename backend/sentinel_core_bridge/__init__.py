"""
Sentinel-Core Bridge Package for Sentinel-Panel.
Provides high-performance C-FFI and CLI interfaces to the Go sentinel-core engine.

Submodules:
- ffi: Dynamic library loading, C-FFI invocations, memory management, and CLI runner.
- config_builder: Multi-protocol server config compilation and client failover generation.
- lifecycle: Core process supervision (start, stop, restart, validate, status, version).
- crypto: Keypairs generation (X25519, VLESS-ENC) and authenticated payload AEAD encryption.
- traffic_sessions: Unified traffic telemetry, active online sessions, disconnections.
- logs: File log retrieval and memory ring-buffer log streaming/clearing.
- routing: Presets, schema capabilities, proxy URI links, subscriptions, and latency testing.
"""

from backend.sentinel_core_bridge.ffi import (
    _get_sentinel_core_bin,
    _find_sentinel_core_lib_path,
    _init_sentinel_lib,
    get_sentinel_lib,
    set_sentinel_lib,
    _ffi_call_str,
    _ffi_call_json,
    run_core_command,
)

from backend.sentinel_core_bridge.crypto import (
    generate_x25519_keypair,
    generate_vlessenc_keypair,
    encrypt_payload,
    decrypt_payload,
)

from backend.sentinel_core_bridge.lifecycle import (
    start_core,
    stop_core,
    restart_core,
    validate_core_config,
    get_cores_status,
    get_core_version,
)

from backend.sentinel_core_bridge.traffic_sessions import (
    get_unified_traffic,
    get_active_sessions,
    get_online_emails_core,
    get_recent_session_events,
    register_external_connect,
    register_hysteria_port,
    kick_client,
)

from backend.sentinel_core_bridge.logs import (
    get_core_logs,
    pop_core_log_line,
    push_core_log_line,
    get_in_memory_core_logs,
    clear_in_memory_core_logs,
)

from backend.sentinel_core_bridge.routing import (
    get_capabilities_schema,
    get_routing_presets,
    get_preset_details,
    parse_proxy_uri,
    generate_proxy_uri,
    parse_subscription,
    check_proxies,
    test_profiles,
    ping_host,
    set_core_language,
)

from backend.sentinel_core_bridge.config_builder import (
    build_server_config,
    compile_node_server_config,
    build_failover_client_config,
)

__all__ = [
    # FFI
    "_get_sentinel_core_bin",
    "_find_sentinel_core_lib_path",
    "_init_sentinel_lib",
    "get_sentinel_lib",
    "set_sentinel_lib",
    "_ffi_call_str",
    "_ffi_call_json",
    "run_core_command",
    # Crypto
    "generate_x25519_keypair",
    "generate_vlessenc_keypair",
    "encrypt_payload",
    "decrypt_payload",
    # Lifecycle
    "start_core",
    "stop_core",
    "restart_core",
    "validate_core_config",
    "get_cores_status",
    "get_core_version",
    # Traffic & Sessions
    "get_unified_traffic",
    "get_active_sessions",
    "get_online_emails_core",
    "get_recent_session_events",
    "register_external_connect",
    "register_hysteria_port",
    "kick_client",
    # Logs
    "get_core_logs",
    "pop_core_log_line",
    "push_core_log_line",
    "get_in_memory_core_logs",
    "clear_in_memory_core_logs",
    # Routing
    "get_capabilities_schema",
    "get_routing_presets",
    "get_preset_details",
    "parse_proxy_uri",
    "generate_proxy_uri",
    "parse_subscription",
    "check_proxies",
    "test_profiles",
    "ping_host",
    "set_core_language",
    # Config Builder
    "build_server_config",
    "compile_node_server_config",
    "build_failover_client_config",
]
