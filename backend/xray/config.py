# Facade for Xray Configuration Generation & I/O
from backend.database import (
    get_all_inbounds,
    get_clients_for_inbound,
    get_all_outbounds,
    get_all_routing_rules,
    get_setting
)
from backend.xray.config_builder.sanitizer import clean_stream_settings
from backend.xray.config_builder.builder import generate_xray_config_json
from backend.xray.config_builder.io import (
    read_xray_config,
    parse_xray_config,
    write_xray_config
)

__all__ = [
    "clean_stream_settings",
    "generate_xray_config_json",
    "read_xray_config",
    "parse_xray_config",
    "write_xray_config",
    "get_all_inbounds",
    "get_clients_for_inbound",
    "get_all_outbounds",
    "get_all_routing_rules",
    "get_setting"
]
