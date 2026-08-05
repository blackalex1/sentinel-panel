from backend.config import SINGBOX_BIN_PATH, SINGBOX_CONFIG_PATH

from backend.singbox.core import (
    get_latest_singbox_version_info,
    get_singbox_releases,
    download_singbox_core,
    ensure_singbox_installed,
    get_installed_singbox_version,
)

from backend.singbox.service import (
    start_singbox,
    stop_singbox,
    restart_singbox,
    is_singbox_running,
    get_singbox_logs,
    query_singbox_traffic,
)

from backend.singbox.config import (
    generate_singbox_config_json,
    write_singbox_config,
    read_singbox_config,
    parse_singbox_config,
)

__all__ = [
    "SINGBOX_BIN_PATH",
    "SINGBOX_CONFIG_PATH",
    "get_latest_singbox_version_info",
    "download_singbox_core",
    "ensure_singbox_installed",
    "get_installed_singbox_version",
    "start_singbox",
    "stop_singbox",
    "restart_singbox",
    "is_singbox_running",
    "get_singbox_logs",
    "query_singbox_traffic",
    "generate_singbox_config_json",
    "write_singbox_config",
    "read_singbox_config",
    "parse_singbox_config",
]
