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
    if is_xray_running():
        logging.info("Xray is already running.")
        return True
        
    inbounds = get_all_inbounds()
    has_active_xray = False
    for ib in inbounds:
        if not ib["enable"]:
            continue
        ib_core = ib.get("core") or ("hysteria" if ib["protocol"] == "hysteria2" else "xray")
        if ib["protocol"] != "hysteria2":
            if ib_core == "xray":
                has_active_xray = True
                break
        else:
            try:
                stream_settings = json.loads(ib["stream_settings"] or "{}")
                if stream_settings.get("hysteria", {}).get("routingViaXray"):
                    has_active_xray = True
                    break
            except Exception:
                pass
                
    if not has_active_xray:
        logging.info("No active Xray inbounds or Hysteria routing via Xray found. Xray core will not be started.")
        return True

    stop_xray()
    backend.xray.ensure_xray_installed()
    backend.xray.write_xray_config()
    
    logging.info("Verifying Xray configuration...")
    try:
        test_cmd = [str(backend.xray.XRAY_BIN_PATH), "run", "-config", str(backend.config.XRAY_CONFIG_PATH), "-test"]
        test_res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)  # nosec B603
        if test_res.returncode != 0:
            err_msg = test_res.stderr.strip() or test_res.stdout.strip()
            logging.error(f"Xray config verification failed: {err_msg}")
            print(f"[Xray Config Error] {err_msg}", flush=True)
            LAST_XRAY_ERROR = err_msg
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

    logging.info(f"Starting Xray process: {backend.xray.XRAY_BIN_PATH}")
    for _attempt in range(3):
        try:
            xray_process = subprocess.Popen(
                [str(backend.xray.XRAY_BIN_PATH), "run", "-config", str(backend.config.XRAY_CONFIG_PATH)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )  # nosec B603

            time.sleep(0.3)
            ret = xray_process.poll()
            if ret is not None:
                logging.warning(
                    f"Xray process exited immediately with code {ret}, attempt {_attempt + 1}/3"
                )
                xray_process = None
                if _attempt < 2:
                    time.sleep(0.5)
                    continue
                backend.xray.log_xray_errors()
                return False

            logging.info("Xray process started successfully.")
            threading.Thread(target=backend.xray.tail_xray_logs, daemon=True).start()
            return True
        except Exception as e:
            logging.error(f"Failed to start Xray process: {e}")
            return False
    return False




def stop_xray():
    """Останавливает процесс Xray"""
    global xray_process, _last_session_stats
    _last_session_stats.clear()
    if xray_process:
        try:
            logging.info("Stopping Xray process...")
        except Exception:
            pass
        xray_process.terminate()
        try:
            xray_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            xray_process.kill()
        xray_process = None
        time.sleep(0.5)   # give Windows time to release ports before next bind
        try:
            logging.info("Xray process stopped.")
        except Exception:
            pass
    elif "pytest" not in sys.modules:
        if backend.xray.IS_WINDOWS:
            taskkill_path = shutil.which("taskkill") or r"C:\Windows\System32\taskkill.exe"
            subprocess.run([taskkill_path, "/F", "/IM", "xray.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603
        else:
            killall_path = shutil.which("killall") or "/usr/bin/killall"
            subprocess.run([killall_path, "xray"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603
        try:
            logging.info("Killed any orphan Xray processes.")
        except Exception:
            pass


def restart_xray():
    """Перезапускает процесс Xray с новым конфигом"""
    import backend.watchdog_state
    if not backend.watchdog_state.in_watchdog_context:
        backend.watchdog_state.reset_xray_watchdog()
    backend.xray.stop_xray()
    return backend.xray.start_xray()

def is_xray_running():
    """Проверяет, запущен ли процесс Xray"""
    global xray_process
    if xray_process is not None:
        return xray_process.poll() is None
    
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("-test" in str(arg) for arg in cmdline):
                continue
            name = proc.info.get("name") or ""
            if name == backend.xray.XRAY_BIN_NAME or name == "xray":
                if "pytest" in sys.modules:
                    if any(str(backend.config.XRAY_CONFIG_PATH) in str(arg) for arg in cmdline):
                        return True
                else:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
            
    return False

def query_traffic_stats():
    """Опрашивает gRPC API Xray для получения статистики трафика и обновляет БД"""
    if not backend.xray.is_xray_running():
        return
    if not backend.xray.XRAY_BIN_PATH.exists():
        return
        
    try:
        cmd = [str(backend.xray.XRAY_BIN_PATH), "api", "statsquery", "--server=127.0.0.1:10085"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)  # nosec B603
        if result.returncode != 0:
            logging.warning(f"Xray statsquery returned error: {result.stderr}")
            return
            
        data = json.loads(result.stdout)
        stats = data.get("stat", [])
        process_stats_deltas(stats)
            
    except subprocess.TimeoutExpired:
        logging.warning("Xray statsquery timed out.")
        backend.xray.log_xray_errors()
    except Exception as e:
        logging.error(f"Error querying Xray stats: {e}")
        backend.xray.log_xray_errors()

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
    """Динамически удаляет клиента через gRPC API Xray для мгновенного разрыва активных сессий"""
    if not backend.xray.is_xray_running() or not backend.xray.XRAY_BIN_PATH.exists():
        return False
    try:
        tag = f"inbound-{inbound_id}"
        cmd = [
            str(backend.xray.XRAY_BIN_PATH), "api", "removeclient",
            "--server=127.0.0.1:10085",
            f"--inboundTag={tag}",
            f"--email={email}"
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)  # nosec B603
        if result.returncode == 0:
            logging.info(f"Successfully removed client {email} from inbound {inbound_id} via gRPC API.")
            return True
        else:
            logging.warning(f"Failed to remove client {email} via Xray API: {result.stderr}")
            return False
    except Exception as e:
        logging.error(f"Error calling Xray removeclient API: {e}")
        return False

def get_xray_logs(lines_count: int = 150) -> list:
    """Возвращает последние строки лог-файла Xray"""
    if not backend.xray.XRAY_LOG_PATH.exists():
        return ["Лог-файл пуст или еще не создан."]
        
    try:
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
                try:
                    from backend.client_alerts import process_xray_log_line
                    process_xray_log_line(line)
                except Exception as ex:
                    logging.error(f"Error processing Xray log line: {ex}")
    except Exception as e:
        logging.error(f"Error tailing Xray logs: {e}")

