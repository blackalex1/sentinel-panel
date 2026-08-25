import os
import sys
import json
import logging
import subprocess
import shutil
import time
import requests
import backend.hysteria
from backend.database import get_all_inbounds, get_clients_for_inbound, update_client_traffic, update_inbound_traffic

# Словарь запущенных процессов: inbound_id -> Popen
hysteria_processes = {}
# Предыдущие счетчики трафика для дельт: "inbound_id:email:dir" -> value
_last_hysteria_stats = {}


def get_hysteria_logs(lines_count: int = 150) -> list:
    """Возвращает последние строки лог-файла Hysteria 2 через sentinel-core supervisor"""
    if not backend.hysteria.HYSTERIA_LOG_PATH.exists():
        return ["Лог-файл пуст или еще не создан."]
        
    try:
        from backend.sentinel_core_bridge import get_core_logs
        lines = get_core_logs(str(backend.hysteria.HYSTERIA_LOG_PATH), lines_count)
        if lines:
            return [line.strip() for line in lines]

        from backend.utils import read_last_lines
        lines = read_last_lines(backend.hysteria.HYSTERIA_LOG_PATH, lines_count)
        return [line.strip() for line in lines]
    except Exception as e:
        return [f"Ошибка чтения логов: {e}"]

def is_hysteria_running() -> bool:
    """Проверяет, запущен ли хотя бы один процесс Hysteria 2"""
    global hysteria_processes
    if hysteria_processes:
        if any(proc.poll() is None for proc in hysteria_processes.values()):
            return True

    try:
        from backend.sentinel_core_bridge import get_cores_status
        status = get_cores_status()
        if isinstance(status, dict):
            if "cores" in status and isinstance(status["cores"], list):
                for c in status["cores"]:
                    if c.get("name") in ("hysteria", "hysteria2") and c.get("running"):
                        return True
            elif status.get("hysteria2", {}).get("running") or status.get("hysteria", {}).get("running"):
                return True
    except Exception:
        pass

    import psutil
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("AppData\\Local\\Temp\\tmp" in str(arg) or "/tmp/tmp" in str(arg) for arg in cmdline):
                continue
            name = proc.info.get("name") or ""
            if name == backend.hysteria.HYSTERIA_BIN_NAME or (name and name.startswith("hysteria-linux-")):
                return True
            if any(backend.hysteria.HYSTERIA_BIN_NAME in str(arg) for arg in cmdline):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return False

def start_hysteria():
    """Запускает процессы Hysteria 2 для всех hysteria2 подключений из БД"""
    global hysteria_processes
    
    inbounds = get_all_inbounds()
    hysteria_inbounds = [ib for ib in inbounds if ib["protocol"] == "hysteria2" and ib["enable"]]
    
    # Автоматическая очистка файлов конфигураций и сертификатов для удаленных инбаундов Hysteria 2
    import os
    from backend.config import CONFIG_DIR
    all_hysteria_ids = {ib["id"] for ib in inbounds if ib["protocol"] == "hysteria2"}
    
    # Очищаем файлы в CONFIG_DIR (.crt, .key, .sni)
    if CONFIG_DIR.exists():
        for filename in os.listdir(CONFIG_DIR):
            if filename.startswith("hysteria_"):
                try:
                    parts = filename.split("_", 1)[1].split(".", 1)
                    ib_id = int(parts[0])
                    if ib_id not in all_hysteria_ids:
                        file_path = CONFIG_DIR / filename
                        os.remove(file_path)
                        logging.info(f"Cleaned up deleted Hysteria inbound file: {file_path}")
                except (ValueError, IndexError, Exception):
                    pass
                    
    # Очищаем файлы в BIN_DIR (.json конфигурация)
    if backend.hysteria.BIN_DIR.exists():
        for filename in os.listdir(backend.hysteria.BIN_DIR):
            if filename.startswith("hysteria_") and filename.endswith(".json"):
                try:
                    ib_id = int(filename.split("_", 1)[1].split(".", 1)[0])
                    if ib_id not in all_hysteria_ids:
                        file_path = backend.hysteria.BIN_DIR / filename
                        os.remove(file_path)
                        logging.info(f"Cleaned up deleted Hysteria config file: {file_path}")
                except (ValueError, IndexError, Exception):
                    pass
    
    if not hysteria_inbounds:
        logging.info("No active Hysteria 2 inbounds found. Hysteria core will not be started.")
        return True
        
    # Гарантируем установку ядра Hysteria 2 на старте
    backend.hysteria.ensure_hysteria_installed()
    
    backend.hysteria.generate_self_signed_cert()
    
    success = True
    for ib in hysteria_inbounds:
        ib_id = ib["id"]
        if ib_id in hysteria_processes and hysteria_processes[ib_id].poll() is None:
            continue
            
        clients = get_clients_for_inbound(ib_id)
        active_clients = [c for c in clients if c["enable"]]
        if not active_clients:
            logging.info(f"Hysteria 2 inbound {ib_id} on port {ib['port']} has no active clients. Skipping startup.")
            continue
            
        try:
            stream_settings = json.loads(ib["stream_settings"] or "{}")
        except Exception:
            stream_settings = {}
        config_path = backend.hysteria.BIN_DIR / f"hysteria_{ib_id}.json"
        from backend.database import get_setting
        if get_setting(f"use_custom_hysteria_config_{ib_id}") == "true" and config_path.exists():
            logging.info(f"Hysteria 2 inbound {ib_id} is using custom configuration. Skipping generation.")
        else:
            config = backend.hysteria.generate_hysteria_config(ib_id, ib["port"], active_clients, stream_settings)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            
        logging.info(f"Starting Hysteria 2 on port {ib['port']} via sentinel-core...")
        try:
            admin_port = 0
            if isinstance(config, dict) and "trafficStats" in config:
                ts_listen = config["trafficStats"].get("listen", "")
                if ":" in ts_listen:
                    try:
                        admin_port = int(ts_listen.split(":")[-1])
                    except Exception:
                        pass
            if admin_port > 0:
                try:
                    from backend.sentinel_core_bridge import register_hysteria_port
                    register_hysteria_port(admin_port)
                except Exception:
                    pass

            from backend.sentinel_core_bridge import start_core
            if start_core("hysteria2", str(backend.hysteria.HYSTERIA_BIN_PATH), str(config_path)):
                logging.info(f"Hysteria 2 started successfully via sentinel-core for inbound {ib_id}.")
                time.sleep(0.15)
                success = True
            else:
                logging.error(f"sentinel-core failed to start Hysteria 2 for inbound {ib_id}")
                success = False
        except Exception as e:
            logging.error(f"Failed to start Hysteria 2 via sentinel-core: {e}")
            success = False
            
    return success

def stop_hysteria():
    """Останавливает все процессы Hysteria 2 через sentinel-core"""
    global hysteria_processes, _last_hysteria_stats
    _last_hysteria_stats.clear()
    try:
        from backend.sentinel_core_bridge import stop_core
        stop_core("hysteria2")
        logging.info("Hysteria 2 stopped via sentinel-core.")
    except Exception as e:
        logging.error(f"Error stopping Hysteria 2 via sentinel-core: {e}")
    hysteria_processes.clear()
    time.sleep(0.05)

def restart_hysteria():
    backend.hysteria.stop_hysteria()
    return backend.hysteria.start_hysteria()

def query_hysteria_traffic():
    """Считывает трафик Hysteria 2 через sentinel-core и обновляет БД"""
    global _last_hysteria_stats
    
    inbounds = get_all_inbounds()
    hysteria_inbounds = [ib for ib in inbounds if ib["protocol"] == "hysteria2" and ib["enable"]]
    if not hysteria_inbounds:
        return

    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic_data = get_unified_traffic() or {}
        
        if traffic_data and isinstance(traffic_data, dict):
            for email, stats in traffic_data.items():
                if not isinstance(stats, dict):
                    continue
                rx = int(stats.get("upBytes", 0) or stats.get("up", 0) or stats.get("rx", 0))
                tx = int(stats.get("downBytes", 0) or stats.get("down", 0) or stats.get("tx", 0))

                updated = False
                for ib in hysteria_inbounds:
                    ib_id = ib["id"]
                    up_key = f"{ib_id}:{email}:up"
                    prev_up = _last_hysteria_stats.get(up_key, 0)
                    up_delta = rx - prev_up if rx >= prev_up else rx
                    _last_hysteria_stats[up_key] = rx

                    down_key = f"{ib_id}:{email}:down"
                    prev_down = _last_hysteria_stats.get(down_key, 0)
                    down_delta = tx - prev_down if tx >= prev_down else tx
                    _last_hysteria_stats[down_key] = tx

                    if up_delta > 0 or down_delta > 0:
                        if update_client_traffic(ib_id, email, up_delta, down_delta):
                            update_inbound_traffic(ib_id, up_delta, down_delta)
                            updated = True
                            break

                if not updated and (rx > 0 or tx > 0):
                    prev_up = _last_hysteria_stats.get(f"global:{email}:up", 0)
                    up_delta = rx - prev_up if rx >= prev_up else rx
                    _last_hysteria_stats[f"global:{email}:up"] = rx

                    prev_down = _last_hysteria_stats.get(f"global:{email}:down", 0)
                    down_delta = tx - prev_down if tx >= prev_down else tx
                    _last_hysteria_stats[f"global:{email}:down"] = tx

                    if up_delta > 0 or down_delta > 0:
                        from backend.database import update_client_traffic_by_email
                        update_client_traffic_by_email(email, up_delta, down_delta)
        else:
            # Fallback direct query to active Hysteria instances (where /traffic yields deltas directly)
            for ib in hysteria_inbounds:
                ib_id = ib["id"]
                admin_port = 10100 + (ib["port"] % 1000)
                config_path = backend.hysteria.BIN_DIR / f"hysteria_{ib_id}.json"
                if config_path.exists():
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            h_cfg = json.load(f)
                            ts_listen = h_cfg.get("trafficStats", {}).get("listen", "")
                            if ":" in ts_listen:
                                admin_port = int(ts_listen.split(":")[-1])
                    except Exception:
                        pass

                try:
                    import urllib.request
                    req = urllib.request.Request(f"http://127.0.0.1:{admin_port}/traffic", headers={"User-Agent": "Sentinel-Panel"})
                    with urllib.request.urlopen(req, timeout=0.4) as resp:
                        if resp.status == 200:
                            raw_data = json.loads(resp.read().decode("utf-8"))
                            for email, t in raw_data.items():
                                rx_delta = int(t.get("rx", 0))
                                tx_delta = int(t.get("tx", 0))
                                if rx_delta > 0 or tx_delta > 0:
                                    if update_client_traffic(ib_id, email, rx_delta, tx_delta):
                                        update_inbound_traffic(ib_id, rx_delta, tx_delta)
                                    else:
                                        from backend.database import update_client_traffic_by_email
                                        update_client_traffic_by_email(email, rx_delta, tx_delta)
                except Exception:
                    pass
                    
    except Exception as e:
        logging.debug(f"Hysteria traffic stats poll error: {e}")

def kick_client_hysteria_api(inbound_id: int, email: str) -> bool:
    """Динамически сбрасывает сессии клиента через sentinel-core"""
    try:
        from backend.sentinel_core_bridge import kick_client
        if kick_client(email):
            return True
    except Exception:
        pass

    return True

