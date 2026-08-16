from backend.config import BIN_DIR, IS_WINDOWS, DB_PATH, HYSTERIA_LOG_PATH
from backend.hysteria.core import _get_bin_suffix

HYSTERIA_BIN_NAME = f"hysteria-windows-{_get_bin_suffix()}.exe" if IS_WINDOWS else f"hysteria-linux-{_get_bin_suffix()}"
HYSTERIA_BIN_PATH = BIN_DIR / HYSTERIA_BIN_NAME
HYSTERIA_CERT_PATH = BIN_DIR / "hysteria.crt"
HYSTERIA_KEY_PATH = BIN_DIR / "hysteria.key"

from backend.hysteria.core import (
    get_latest_hysteria_version_info,
    get_hysteria_releases,
    download_hysteria_core,
    ensure_hysteria_installed,
    get_installed_hysteria_version,
    generate_self_signed_cert,
)
from backend.hysteria.config import (
    generate_hysteria_config,
    ensure_hysteria_quic_and_log,
)
from backend.hysteria.service import (
    hysteria_processes,
    _last_hysteria_stats,
    get_hysteria_logs,
    is_hysteria_running,
    start_hysteria,
    stop_hysteria,
    restart_hysteria,
    query_hysteria_traffic,
    kick_client_hysteria_api,
)

__all__ = [
    "BIN_DIR",
    "IS_WINDOWS",
    "DB_PATH",
    "HYSTERIA_LOG_PATH",
    "HYSTERIA_BIN_NAME",
    "HYSTERIA_BIN_PATH",
    "HYSTERIA_CERT_PATH",
    "HYSTERIA_KEY_PATH",
    "_get_bin_suffix",
    "get_latest_hysteria_version_info",
    "download_hysteria_core",
    "ensure_hysteria_installed",
    "get_installed_hysteria_version",
    "generate_self_signed_cert",
    "generate_hysteria_config",
    "ensure_hysteria_quic_and_log",
    "hysteria_processes",
    "_last_hysteria_stats",
    "get_hysteria_logs",
    "is_hysteria_running",
    "start_hysteria",
    "stop_hysteria",
    "restart_hysteria",
    "query_hysteria_traffic",
    "kick_client_hysteria_api",
]
