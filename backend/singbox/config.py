"""Sing-box configuration builder - powered by sentinel-core native compiler."""
import json
import logging
from backend.config import SINGBOX_CONFIG_PATH
import backend.database as db
from backend.sentinel_core_bridge import compile_node_server_config

def get_all_inbounds(*args, **kwargs):
    return db.get_all_inbounds(*args, **kwargs)

def get_clients_for_inbound(*args, **kwargs):
    return db.get_clients_for_inbound(*args, **kwargs)

def get_all_outbounds(*args, **kwargs):
    return db.get_all_outbounds(*args, **kwargs)

def get_all_routing_rules(*args, **kwargs):
    return db.get_all_routing_rules(*args, **kwargs)

def get_setting(*args, **kwargs):
    return db.get_setting(*args, **kwargs)

def generate_singbox_config_json() -> dict:
    """Generates Sing-box server configuration JSON via sentinel-core compiler."""
    try:
        res = compile_node_server_config("sing-box")
        if isinstance(res, dict):
            if "config" in res:
                cfg = res["config"]
                if isinstance(cfg, str):
                    return json.loads(cfg)
                elif isinstance(cfg, dict):
                    return cfg
            return res
    except Exception as e:
        logging.error(f"Error compiling sing-box config via sentinel-core: {e}")
    return {}

def parse_singbox_config(config_dict: dict) -> dict:
    """Sanitizes sing-box config before writing."""
    if not isinstance(config_dict, dict):
        raise ValueError("Sing-box config must be a dictionary.")
    for section in ["inbounds", "outbounds"]:
        if section in config_dict and not isinstance(config_dict[section], list):
            raise ValueError(f"Section '{section}' in Sing-box config must be a list.")
    return config_dict

def read_singbox_config() -> dict:
    """Reads sing-box config from file or generates default."""
    if SINGBOX_CONFIG_PATH.exists():
        try:
            with open(SINGBOX_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return generate_singbox_config_json()

def write_singbox_config(config_dict: dict = None, force: bool = False) -> bool:
    """Writes sing-box server configuration file."""
    try:
        setting_fn = getattr(db, "get_setting", lambda k, d="": d)
        if config_dict is None:
            if not force and setting_fn("use_custom_singbox_config") == "true" and SINGBOX_CONFIG_PATH.exists():
                logging.info("Using existing custom Sing-box config from file.")
                return True
            config_dict = generate_singbox_config_json()

        config_dict = parse_singbox_config(config_dict)
        with open(SINGBOX_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        logging.info(f"Sing-box config successfully written to {SINGBOX_CONFIG_PATH}")
        return True
    except Exception as e:
        logging.error(f"Failed to write sing-box config: {e}")
        return False
