"""Xray configuration builder - powered by sentinel-core native compiler."""
import json
import logging
from backend.sentinel_core_bridge import compile_node_server_config

_db_readers_provider = None


def register_db_readers_provider(provider_fn) -> None:
    """Registers a callable returning DB reader functions (preserves mockable xray.config hooks)."""
    global _db_readers_provider
    _db_readers_provider = provider_fn


def get_xray_db_readers() -> dict | None:
    return _db_readers_provider() if _db_readers_provider else None


def generate_xray_config_json() -> dict:
    """Generates Xray server configuration JSON via sentinel-core compiler."""
    try:
        res = compile_node_server_config("xray", db_readers=get_xray_db_readers())
        if isinstance(res, dict):
            if "config" in res:
                cfg = res["config"]
                if isinstance(cfg, str):
                    return json.loads(cfg)
                elif isinstance(cfg, dict):
                    return cfg
            return res
    except Exception as e:
        logging.error(f"Error compiling xray config via sentinel-core: {e}")
    return {}
