import os
import sys
import json
import logging
import subprocess
import shutil
import time
import threading
import psutil
import backend.xray
from backend.database import get_all_inbounds, update_client_traffic, update_client_traffic_by_email, update_inbound_traffic

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

xray_process = None
LAST_XRAY_ERROR = ""

def get_last_xray_error() -> str:
    global LAST_XRAY_ERROR
    return LAST_XRAY_ERROR

# Хранилище показаний счетчиков gRPC в рамках текущей сессии Xray
_last_session_stats = {}

def start_xray():
    """Запускает процесс Xray"""
    global xray_process, LAST_XRAY_ERROR
    LAST_XRAY_ERROR = ""
        
    inbounds = get_all_inbounds()
    has_active_xray = False
    for ib in inbounds:
        if not ib.get("enable", 1):
            continue
        ib_core = ib.get("core") or ("hysteria" if ib.get("protocol") == "hysteria2" else "xray")
        if ib.get("protocol") != "hysteria2":
            if ib_core == "xray":
                has_active_xray = True
                break
        else:
            try:
                raw_ss = ib.get("stream_settings")
                if isinstance(raw_ss, str):
                    stream_settings = json.loads(raw_ss or "{}")
                elif isinstance(raw_ss, dict):
                    stream_settings = raw_ss
                else:
                    stream_settings = {}
                if stream_settings.get("hysteria", {}).get("routingViaXray") or stream_settings.get("routing_via_xray"):
                    has_active_xray = True
                    break
            except Exception:
                pass
                
    if not has_active_xray:
        logging.info("No active Xray inbounds or Hysteria routing via Xray found. Xray core will not be started.")
        stop_xray()
        return True

    stop_xray()
    backend.xray.ensure_xray_installed()
    backend.xray.write_xray_config()
    
    logging.info("Verifying Xray configuration...")
    try:
        from backend.sentinel_core_bridge import validate_core_config
        valid, out = validate_core_config("xray", str(backend.xray.XRAY_BIN_PATH), str(backend.config.XRAY_CONFIG_PATH))
        if not valid:
            logging.error(f"Xray config verification failed: {out}")
            LAST_XRAY_ERROR = out
            return False
    except Exception as e:
        logging.error(f"Failed to run Xray config test: {e}")
    
    # Ensure port 10085 (Xray gRPC API) is released before starting
    import socket
    for _ in range(15):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", 10085))
                break
        except OSError:
            time.sleep(0.2)

    logging.info(f"Starting Xray process via sentinel-core: {backend.xray.XRAY_BIN_PATH}")
    try:
        from backend.sentinel_core_bridge import start_core
        if start_core("xray", str(backend.xray.XRAY_BIN_PATH), str(backend.config.XRAY_CONFIG_PATH)):
            logging.info("Xray process started successfully via sentinel-core.")
            time.sleep(0.25)
            return True
        logging.error("sentinel-core failed to start Xray process.")
        return False
    except Exception as e:
        logging.error(f"Failed to start Xray process: {e}")
        return False


def stop_xray():
    """Останавливает процесс Xray через sentinel-core"""
    global xray_process, _last_session_stats
    _last_session_stats.clear()
    try:
        from backend.sentinel_core_bridge import stop_core
        stop_core("xray")
        logging.info("Xray process stopped via sentinel-core.")
    except Exception as e:
        logging.error(f"Failed to stop Xray process via sentinel-core: {e}")
    xray_process = None
    time.sleep(0.1)


def restart_xray():
    """Перезапускает процесс Xray с новым конфигом"""
    backend.xray.stop_xray()
    return backend.xray.start_xray()

def is_xray_running():
    """Проверяет, запущен ли процесс Xray через sentinel-core supervisor"""
    global xray_process
    if xray_process is not None:
        if xray_process.poll() is None:
            return True
        else:
            xray_process = None

    try:
        from backend.sentinel_core_bridge import get_cores_status
        status = get_cores_status()
        if isinstance(status, dict):
            if "cores" in status and isinstance(status["cores"], list):
                for c in status["cores"]:
                    if c.get("name") == "xray" and c.get("running"):
                        return True
            elif status.get("xray", {}).get("running"):
                return True
    except Exception:
        pass
    
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("-test" in str(arg) for arg in cmdline):
                continue
            name = (proc.info.get("name") or "").lower()
            xray_bin_name = backend.xray.XRAY_BIN_NAME.lower()
            if name == xray_bin_name or name in ("xray", "xray.exe"):
                if "pytest" in sys.modules:
                    target_cfg = os.path.normcase(os.path.abspath(str(backend.config.XRAY_CONFIG_PATH)))
                    if any(target_cfg in os.path.normcase(os.path.abspath(str(arg))) or os.path.normcase(str(backend.config.XRAY_CONFIG_PATH)) in os.path.normcase(str(arg)) for arg in cmdline):
                        return True
                else:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
            
    return False

def query_traffic_stats():
    """Считывает статистику трафика Xray через sentinel-core и обновляет БД."""
    if not backend.xray.is_xray_running():
        return

    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic_data = get_unified_traffic()
        if traffic_data and isinstance(traffic_data, dict):
            from backend.database import get_all_inbounds
            inbounds = get_all_inbounds()
            xray_inbounds = [ib for ib in inbounds if ib.get("core") != "singbox" and ib.get("protocol") != "hysteria2" and ib.get("enable")]

            for email, stats in traffic_data.items():
                if not isinstance(stats, dict):
                    continue
                rx = int(stats.get("upBytes", 0))
                tx = int(stats.get("downBytes", 0))

                up_key = f"user>>>{email}>>>traffic>>>uplink"
                prev_up = _last_session_stats.get(up_key, 0)
                up_delta = rx - prev_up if rx >= prev_up else rx
                _last_session_stats[up_key] = rx

                down_key = f"user>>>{email}>>>traffic>>>downlink"
                prev_down = _last_session_stats.get(down_key, 0)
                down_delta = tx - prev_down if tx >= prev_down else tx
                _last_session_stats[down_key] = tx

                if up_delta > 0 or down_delta > 0:
                    update_client_traffic_by_email(email, up_delta, down_delta)
                    for ib in xray_inbounds:
                        update_inbound_traffic(ib["id"], up_delta, down_delta)
                        
    except Exception as e:
        logging.debug(f"Error querying Xray stats via sentinel-core: {e}")

def process_stats_deltas(stats_list):
    """Вычисляет дельту трафика с момента предыдущего опроса и прибавляет к БД"""
    global _last_session_stats
    
    for stat in stats_list:
        name = stat.get("name", "")
        value = int(stat.get("value", 0))
        
        prev_val = _last_session_stats.get(name, 0)
        if value < prev_val:
            delta = value
        else:
            delta = value - prev_val
            
        _last_session_stats[name] = value
        
        if delta <= 0:
            continue
            
        parts = name.split(">>>")
        metric_type = parts[0]
        target = parts[1]
        direction = parts[3]
        
        up_add = delta if direction == "uplink" else 0
        down_add = delta if direction == "downlink" else 0
        
        if metric_type == "user":
            update_client_traffic_by_email(target, up_add, down_add)
                
        elif metric_type == "inbound":
            if target.startswith("inbound-") and not target.endswith("-socks"):
                try:
                    ib_id = int(target.split("-")[1])
                    update_inbound_traffic(ib_id, up_add, down_add)
                except ValueError:
                    pass
        elif metric_type == "outbound":
            from backend.database import update_outbound_traffic
            update_outbound_traffic(target, up_add, down_add)


def remove_client_api(inbound_id: int, email: str) -> bool:
    """Динамически сбрасывает сессии клиента через sentinel-core"""
    try:
        from backend.sentinel_core_bridge import kick_client
        if kick_client(email):
            return True
    except Exception:
        pass
    return True


def get_xray_logs(lines_count: int = 150) -> list:
    """Возвращает последние строки лог-файла Xray через sentinel-core supervisor"""
    if not backend.xray.XRAY_LOG_PATH.exists():
        return ["Лог-файл пуст или еще не создан."]
        
    try:
        from backend.sentinel_core_bridge import get_core_logs
        lines = get_core_logs(str(backend.xray.XRAY_LOG_PATH), lines_count)
        if lines:
            return [line.strip() for line in lines]
            
        from backend.utils import read_last_lines
        lines = read_last_lines(backend.xray.XRAY_LOG_PATH, lines_count)
        return [line.strip() for line in lines]
    except Exception as e:
        return [f"Ошибка чтения логов: {e}"]

def log_xray_errors():
    """Prints last 20 lines of Xray logs to output for easy container debugging."""
    try:
        logs = backend.xray.get_xray_logs(20)
        logging.error("--- Last 20 lines of Xray log ---")
        for line in logs:
            logging.error(line)
        logging.error("---------------------------------")
    except Exception as e:
        logging.error(f"Failed to output Xray logs: {e}")

def tail_xray_logs():
    """Background thread to tail xray.log and print to stdout"""
    global xray_process
    try:
        for _ in range(10):
            if backend.xray.XRAY_LOG_PATH.exists():
                break
            time.sleep(0.5)
            
        if not backend.xray.XRAY_LOG_PATH.exists():
            return
            
        with open(backend.xray.XRAY_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(0, 2)
            while xray_process and xray_process.poll() is None:
                try:
                    import os
                    if os.path.exists(backend.xray.XRAY_LOG_PATH):
                        current_pos = f.tell()
                        file_size = os.path.getsize(backend.xray.XRAY_LOG_PATH)
                        if current_pos > file_size:
                            f.seek(0)
                except Exception:
                    pass

                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                print(f"[Xray] {line.strip()}", flush=True)
                try:
                    from backend.log_streamer import push_log_line
                    push_log_line("xray", line)
                except Exception:
                    pass
    except Exception as e:
        logging.error(f"Error tailing Xray logs: {e}")

