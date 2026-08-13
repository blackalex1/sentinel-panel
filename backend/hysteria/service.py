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
_hysteria_tailer_running = False

def tail_hysteria_logs():
    """Background thread to tail hysteria.log and print to stdout"""
    global _hysteria_tailer_running
    if _hysteria_tailer_running:
        return
    _hysteria_tailer_running = True
    
    try:
        # Wait for log file to be created
        for _ in range(10):
            if backend.hysteria.HYSTERIA_LOG_PATH.exists():
                break
            time.sleep(0.5)
            
        if not backend.hysteria.HYSTERIA_LOG_PATH.exists():
            _hysteria_tailer_running = False
            return
            
        with open(backend.hysteria.HYSTERIA_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(0, 2)
            while backend.hysteria.is_hysteria_running():
                try:
                    import os
                    if os.path.exists(backend.hysteria.HYSTERIA_LOG_PATH):
                        current_pos = f.tell()
                        file_size = os.path.getsize(backend.hysteria.HYSTERIA_LOG_PATH)
                        if current_pos > file_size:
                            f.seek(0)
                except Exception:
                    pass

                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                print(f"[Hysteria] {line.strip()}", flush=True)
                try:
                    from backend.log_streamer import push_log_line
                    push_log_line("hysteria", line)
                except Exception:
                    pass
                try:
                    from backend.client_alerts import process_hysteria_log_line
                    process_hysteria_log_line(line)
                except Exception as ex:
                    logging.error(f"Error processing Hysteria log line: {ex}")
    except Exception as e:
        logging.error(f"Error tailing Hysteria logs: {e}")
    finally:
        _hysteria_tailer_running = False

def get_hysteria_logs(lines_count: int = 150) -> list:
    """Возвращает последние строки лог-файла Hysteria 2"""
    if not backend.hysteria.HYSTERIA_LOG_PATH.exists():
        return ["Лог-файл пуст или еще не создан."]
        
    try:
        from backend.utils import read_last_lines
        lines = read_last_lines(backend.hysteria.HYSTERIA_LOG_PATH, lines_count)
        return [line.strip() for line in lines]
    except Exception as e:
        return [f"Ошибка чтения логов: {e}"]

def is_hysteria_running() -> bool:
    """Проверяет, запущен ли хотя бы один процесс Hysteria 2"""
    global hysteria_processes
    if hysteria_processes:
        return any(proc.poll() is None for proc in hysteria_processes.values())
        
    if "pytest" in sys.modules:
        return False
            
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
            
        logging.info(f"Starting Hysteria 2 on port {ib['port']} (Admin port: 10100+{ib_id})...")
        try:
            log_file = open(backend.hysteria.HYSTERIA_LOG_PATH, "a", encoding="utf-8", errors="ignore")
            import os
            env = os.environ.copy()
            log_level = "info"
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                        log_level = (c_data.get("log") or {}).get("level") or "info"
                except Exception:
                    pass
            env["HYSTERIA_LOG_LEVEL"] = log_level
            process = subprocess.Popen(
                [str(backend.hysteria.HYSTERIA_BIN_PATH), "server", "-c", str(config_path)],
                stdout=log_file,
                stderr=log_file,
                env=env,
                close_fds=True
            )  # nosec B603
            
            try:
                process.wait(timeout=0.5)
                logging.error(f"Hysteria 2 process for inbound {ib_id} exited immediately with code {process.returncode}!")
                success = False
            except subprocess.TimeoutExpired:
                hysteria_processes[ib_id] = process
        except Exception as e:
            logging.error(f"Failed to start Hysteria 2 for inbound {ib_id}: {e}")
            success = False
            
    if backend.hysteria.is_hysteria_running():
        import threading
        threading.Thread(target=backend.hysteria.tail_hysteria_logs, daemon=True).start()
        
    return success

def stop_hysteria():
    """Останавливает все процессы Hysteria 2"""
    global hysteria_processes, _last_hysteria_stats
    _last_hysteria_stats.clear()
    for ib_id, process in list(hysteria_processes.items()):
        try:
            logging.info(f"Stopping Hysteria 2 process for inbound {ib_id}...")
        except Exception:
            pass
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        del hysteria_processes[ib_id]
    time.sleep(0.2)

    if "pytest" not in sys.modules:
        if backend.hysteria.IS_WINDOWS:
            taskkill_path = shutil.which("taskkill") or r"C:\Windows\System32\taskkill.exe"
            subprocess.run([taskkill_path, "/F", "/IM", backend.hysteria.HYSTERIA_BIN_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603
        else:
            killall_path = shutil.which("killall") or "/usr/bin/killall"
            subprocess.run([killall_path, backend.hysteria.HYSTERIA_BIN_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603

def restart_hysteria():
    import backend.watchdog_state
    if not backend.watchdog_state.in_watchdog_context:
        backend.watchdog_state.reset_hysteria_watchdog()
    backend.hysteria.stop_hysteria()
    return backend.hysteria.start_hysteria()

def query_hysteria_traffic():
    """Считывает трафик по HTTP API Hysteria 2 и обновляет БД"""
    global _last_hysteria_stats
    
    inbounds = get_all_inbounds()
    hysteria_inbounds = [ib for ib in inbounds if ib["protocol"] == "hysteria2" and ib["enable"]]
    
    for ib in hysteria_inbounds:
        ib_id = ib["id"]
        if ib_id not in hysteria_processes:
            continue
            
        admin_port = 10100 + ib_id
        url = f"http://127.0.0.1:{admin_port}/traffic"
        
        try:
            response = requests.get(url, timeout=0.2)
            if response.status_code != 200:
                continue
                
            traffic_data = response.json()
            for email, stats in traffic_data.items():
                tx = int(stats.get("tx", 0)) # download
                rx = int(stats.get("rx", 0)) # upload
                
                up_key = f"{ib_id}:{email}:up"
                prev_up = _last_hysteria_stats.get(up_key, 0)
                up_delta = rx - prev_up if rx >= prev_up else rx
                _last_hysteria_stats[up_key] = rx
                
                down_key = f"{ib_id}:{email}:down"
                prev_down = _last_hysteria_stats.get(down_key, 0)
                down_delta = tx - prev_down if tx >= prev_down else tx
                _last_hysteria_stats[down_key] = tx
                
                if up_delta > 0 or down_delta > 0:
                    update_client_traffic(ib_id, email, up_delta, down_delta)
                    update_inbound_traffic(ib_id, up_delta, down_delta)
                    
        except Exception as e:
            try:
                logging.debug(f"Hysteria traffic stats poll error (process might not be ready yet): {e}")
            except Exception:
                pass

def kick_client_hysteria_api(inbound_id: int, email: str) -> bool:
    """Динамически сбрасывает QUIC-сессию клиента в Hysteria 2 без перезапуска процесса"""
    if inbound_id not in hysteria_processes:
        return False
    admin_port = 10100 + inbound_id
    url = f"http://127.0.0.1:{admin_port}/kick"
    try:
        payload = [email]
        response = requests.post(url, json=payload, timeout=0.5)
        if response.status_code == 200:
            logging.info(f"Successfully kicked client {email} from Hysteria 2 inbound {inbound_id} via Admin API.")
            return True
        else:
            logging.warning(f"Failed to kick client {email} in Hysteria 2: Status {response.status_code}, {response.text}")
            return False
    except Exception as e:
        try:
            logging.error(f"Error calling Hysteria 2 kick API for client {email}: {e}")
        except Exception:
            pass
        return False
