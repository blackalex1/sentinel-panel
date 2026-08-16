"""Xray configuration builder - powered by sentinel-core native compiler."""
import json
import logging
from backend.sentinel_core_bridge import compile_node_server_config

def generate_xray_config_json() -> dict:
    """Generates Xray server configuration JSON via sentinel-core compiler."""
    try:
        res = compile_node_server_config("xray")
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
