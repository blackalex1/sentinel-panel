import json
import logging
import backend.config
from backend.xray.config_builder.builder import generate_xray_config_json

def read_xray_config(config_path=None) -> dict:
    """Считывает имеющийся конфигурационный файл Xray с диска"""
    path = config_path or backend.config.XRAY_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read Xray config from {path}: {e}")
        return {}

def parse_xray_config(raw_input) -> dict:
    """Парсит и валидирует строку или словарь конфигурации Xray"""
    if isinstance(raw_input, dict):
        config_dict = raw_input
    elif isinstance(raw_input, str):
        try:
            config_dict = json.loads(raw_input)
        except Exception as e:
            raise ValueError(f"Невалидный JSON конфигурации Xray: {e}")
    else:
        raise ValueError("Входные данные должны быть строкой JSON или словарем.")

    if not isinstance(config_dict, dict):
        raise ValueError("Конфигурация Xray должна быть JSON-объектом (dict).")

    for section in ("inbounds", "outbounds"):
        if section in config_dict and not isinstance(config_dict[section], list):
            raise ValueError(f"Секция '{section}' в Xray должна быть списком (list).")

    return config_dict

def write_xray_config(config_dict: dict = None) -> bool:
    """Записывает сгенерированный JSON конфиг в файл через sentinel-core"""
    try:
        from backend.database import get_setting
        cfg_path = backend.config.XRAY_CONFIG_PATH
        if config_dict is None:
            if get_setting("use_custom_xray_config") == "true" and cfg_path.exists():
                logging.info("Xray is using custom configuration. Skipping auto-generation.")
                return True
            try:
                from backend.sentinel_core_bridge import compile_node_server_config
                core_cfg = compile_node_server_config("xray")
                if isinstance(core_cfg, dict) and core_cfg.get("config"):
                    raw_cfg = core_cfg["config"]
                    if isinstance(raw_cfg, str):
                        config_dict = json.loads(raw_cfg)
                    elif isinstance(raw_cfg, dict):
                        config_dict = raw_cfg
            except Exception as e:
                logging.debug(f"Falling back to python xray generator: {e}")
            if config_dict is None:
                config_dict = generate_xray_config_json()

        config_dict = parse_xray_config(config_dict)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)
        logging.info(f"Xray config rewritten to {cfg_path}")
        return True
    except Exception as e:
        logging.error(f"Failed to write Xray config: {e}")
        return False
