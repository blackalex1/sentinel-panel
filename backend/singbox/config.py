import json
import logging
import sys
from backend.config import SINGBOX_CONFIG_PATH, SINGBOX_LOG_PATH
import backend.database as db
from backend.singbox.inbounds import generate_singbox_inbounds
from backend.singbox.outbounds import generate_singbox_outbounds, sanitize_singbox_config
from backend.singbox.routing import generate_singbox_routing

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Переопределяемые символы для обезьяньего патча в тестах
get_all_inbounds = db.get_all_inbounds
get_clients_for_inbound = db.get_clients_for_inbound
get_all_outbounds = db.get_all_outbounds
get_all_routing_rules = db.get_all_routing_rules
get_setting = db.get_setting

def generate_singbox_config_json() -> dict:
    """Генерирует динамическую конфигурацию sing-box из базы данных"""
    mod = sys.modules[__name__]

    # Сначала проверяем monkeypatch в backend.singbox.config, затем в backend.database
    inbounds_fn = getattr(mod, "get_all_inbounds", db.get_all_inbounds)
    if inbounds_fn is db.get_all_inbounds or getattr(inbounds_fn, "__name__", "") == "get_all_inbounds":
        inbounds_fn = db.get_all_inbounds

    clients_fn = getattr(mod, "get_clients_for_inbound", db.get_clients_for_inbound)
    if clients_fn is db.get_clients_for_inbound or getattr(clients_fn, "__name__", "") == "get_clients_for_inbound":
        clients_fn = db.get_clients_for_inbound

    outbounds_fn = getattr(mod, "get_all_outbounds", db.get_all_outbounds)
    if outbounds_fn is db.get_all_outbounds or getattr(outbounds_fn, "__name__", "") == "get_all_outbounds":
        outbounds_fn = db.get_all_outbounds

    rules_fn = getattr(mod, "get_all_routing_rules", db.get_all_routing_rules)
    if rules_fn is db.get_all_routing_rules or getattr(rules_fn, "__name__", "") == "get_all_routing_rules":
        rules_fn = db.get_all_routing_rules

    setting_fn = getattr(mod, "get_setting", db.get_setting)
    if setting_fn is db.get_setting or getattr(setting_fn, "__name__", "") == "get_setting":
        setting_fn = db.get_setting

    singbox_inbounds = generate_singbox_inbounds(inbounds_fn, clients_fn)
    singbox_outbounds = generate_singbox_outbounds(outbounds_fn)
    route_config = generate_singbox_routing(rules_fn, setting_fn)

    config = {
        "log": {
            "level": "debug",
            "output": str(SINGBOX_LOG_PATH).replace("\\", "/"),
            "timestamp": True
        },
        "dns": {
            "servers": [
                {
                    "tag": "dns-remote",
                    "type": "udp",
                    "server": "8.8.8.8"
                }
            ],
            "strategy": "ipv4_only"
        },
        "experimental": {
            "clash_api": {
                "external_controller": "127.0.0.1:9090"
            }
        },
        "inbounds": singbox_inbounds,
        "outbounds": singbox_outbounds,
        "route": route_config
    }
    return sanitize_singbox_config(config)

def read_singbox_config(config_path=None) -> dict:
    """Считывает имеющийся конфигурационный файл sing-box с диска"""
    path = config_path or SINGBOX_CONFIG_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read sing-box config from {path}: {e}")
        return {}

def parse_singbox_config(raw_input) -> dict:
    """Парсит и валидирует строку или словарь конфигурации sing-box"""
    if isinstance(raw_input, dict):
        config_dict = raw_input
    elif isinstance(raw_input, str):
        try:
            config_dict = json.loads(raw_input)
        except Exception as e:
            raise ValueError(f"Невалидный JSON конфигурации sing-box: {e}")
    else:
        raise ValueError("Входные данные должны быть строкой JSON или словарем.")

    if not isinstance(config_dict, dict):
        raise ValueError("Конфигурация sing-box должна быть JSON-объектом (dict).")

    for section in ("inbounds", "outbounds"):
        if section in config_dict and not isinstance(config_dict[section], list):
            raise ValueError(f"Секция '{section}' в sing-box должна быть списком (list).")

    return sanitize_singbox_config(config_dict)

def write_singbox_config(config_dict: dict = None, force: bool = False) -> bool:
    """Записывает конфигурационный файл sing-box в формате JSON"""
    try:
        setting_fn = getattr(sys.modules[__name__], "get_setting", db.get_setting)
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
