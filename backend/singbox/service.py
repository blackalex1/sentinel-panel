import os
import sys
import time
import json
import socket
import struct
import logging
import threading
import subprocess
from pathlib import Path
from backend.config import SINGBOX_BIN_PATH, SINGBOX_CONFIG_PATH, SINGBOX_LOG_PATH
from backend.singbox.config import write_singbox_config

singbox_process = None
LAST_SINGBOX_ERROR = ""

def get_last_singbox_error() -> str:
    global LAST_SINGBOX_ERROR
    return LAST_SINGBOX_ERROR

def is_singbox_running() -> bool:
    """Проверяет, запущен ли процесс sing-box"""
    global singbox_process
    if singbox_process is not None:
        if singbox_process.poll() is None:
            return True
        else:
            singbox_process = None

    if not SINGBOX_BIN_PATH.exists():
        return False

    try:
        import psutil
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                if any("check" in str(arg) for arg in cmdline):
                    continue
                name = proc.info.get("name") or ""
                if name.lower() == SINGBOX_BIN_PATH.name.lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return False
    except Exception:
        return False

def start_singbox(force_generate: bool = False) -> bool:
    """Запускает процесс sing-box"""
    global singbox_process, LAST_SINGBOX_ERROR
    LAST_SINGBOX_ERROR = ""
    if is_singbox_running():
        logging.info("Sing-box is already running.")
        return True

    if not SINGBOX_BIN_PATH.exists():
        logging.error(f"Sing-box binary not found at {SINGBOX_BIN_PATH}")
        return False

    if force_generate or not SINGBOX_CONFIG_PATH.exists():
        logging.info("Writing fresh Sing-box config before start...")
        write_singbox_config()

    logging.info("Verifying Sing-box configuration...")
    try:
        test_cmd = [str(SINGBOX_BIN_PATH), "check", "-c", str(SINGBOX_CONFIG_PATH)]
        test_res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)  # nosec B603
        if test_res.returncode != 0:
            err_msg = test_res.stderr.strip() or test_res.stdout.strip()
            logging.error(f"Sing-box config verification failed: {err_msg}")
            LAST_SINGBOX_ERROR = err_msg
            return False
    except Exception as e:
        logging.error(f"Failed to run Sing-box config test: {e}")

    logging.info("Starting sing-box process...")

    log_file = open(SINGBOX_LOG_PATH, "a", encoding="utf-8")

    try:
        cmd = [str(SINGBOX_BIN_PATH), "run", "-c", str(SINGBOX_CONFIG_PATH)]
        singbox_process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(SINGBOX_BIN_PATH.parent)
        )
        time.sleep(1)
        if singbox_process.poll() is not None:
            err_msg = f"Sing-box terminated immediately with return code {singbox_process.returncode}"
            if SINGBOX_LOG_PATH.exists():
                try:
                    with open(SINGBOX_LOG_PATH, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        if lines:
                            err_msg += f": {''.join(lines[-5:]).strip()}"
                except Exception:
                    pass
            logging.error(f"Sing-box process terminated immediately: {err_msg}")
            LAST_SINGBOX_ERROR = err_msg
            singbox_process = None
            return False

        logging.info("Sing-box started successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to start sing-box: {e}")
        singbox_process = None
        return False

_last_singbox_conn_stats = {}
_singbox_ws_thread = None
_singbox_ws_stop = None

def _read_ws_frame(sock):
    """Reads one unmasked WebSocket frame from server (RFC 6455)"""
    head = sock.recv(2)
    if not head or len(head) < 2:
        return None, None
    b1, b2 = head[0], head[1]
    opcode = b1 & 0x0F
    is_masked = (b2 & 0x80) != 0
    length = b2 & 0x7F
    
    if length == 126:
        ext = sock.recv(2)
        if len(ext) < 2:
            return None, None
        length = struct.unpack("!H", ext)[0]
    elif length == 127:
        ext = sock.recv(8)
        if len(ext) < 8:
            return None, None
        length = struct.unpack("!Q", ext)[0]
        
    payload = bytearray()
    while len(payload) < length:
        chunk = sock.recv(min(65536, length - len(payload)))
        if not chunk:
            break
        payload.extend(chunk)
        
    if is_masked:
        mask = sock.recv(4)
        for i in range(len(payload)):
            payload[i] ^= mask[i % 4]
            
    return opcode, payload.decode("utf-8", errors="ignore")

def _singbox_ws_stream_worker(stop_event):
    """Фоновый WebSocket-поток к Clash API Sing-box для мгновенного учета закрытых сессий в реальном времени"""
    while not stop_event.is_set():
        if not is_singbox_running():
            time.sleep(1)
            continue
        ws = None
        try:
            ws = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ws.settimeout(5)
            ws.connect(("127.0.0.1", 9090))
            req = (
                "GET /connections HTTP/1.1\r\n"
                "Host: 127.0.0.1:9090\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            )
            ws.sendall(req.encode())
            
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = ws.recv(1024)
                if not chunk:
                    break
                resp += chunk
                
            if b"101 " not in resp:
                ws.close()
                time.sleep(2)
                continue
                
            ws.settimeout(None)
            while not stop_event.is_set():
                opcode, text = _read_ws_frame(ws)
                if opcode is None:
                    break
                if opcode == 1 and text:
                    try:
                        data = json.loads(text)
                        _process_singbox_connection_data(data)
                    except Exception:
                        pass
        except Exception as e:
            logging.debug(f"Singbox WebSocket stream reconnecting: {e}")
            time.sleep(2)
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

def _start_singbox_ws_stream():
    global _singbox_ws_thread, _singbox_ws_stop
    if "pytest" in sys.modules:
        return
    if _singbox_ws_thread is not None and _singbox_ws_thread.is_alive():
        return
    _singbox_ws_stop = threading.Event()
    _singbox_ws_thread = threading.Thread(target=_singbox_ws_stream_worker, args=(_singbox_ws_stop,), daemon=True)
    _singbox_ws_thread.start()

def _stop_singbox_ws_stream():
    global _singbox_ws_thread, _singbox_ws_stop
    if _singbox_ws_stop is not None:
        _singbox_ws_stop.set()
    _singbox_ws_thread = None
    _singbox_ws_stop = None

def stop_singbox():
    """Останавливает процесс sing-box"""
    global singbox_process, _last_singbox_conn_stats
    _stop_singbox_ws_stream()
    _last_singbox_conn_stats.clear()
    logging.info("Stopping sing-box process...")

    if singbox_process is not None:
        try:
            singbox_process.terminate()
            try:
                singbox_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                singbox_process.kill()
        except Exception as e:
            logging.error(f"Error terminating sing-box process object: {e}")
        singbox_process = None
        time.sleep(0.2)

    if "pytest" not in sys.modules:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/IM", SINGBOX_BIN_PATH.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["pkill", "-f", str(SINGBOX_BIN_PATH)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logging.error(f"Error terminating sing-box OS process: {e}")

    logging.info("Sing-box stopped.")

def restart_singbox(force_generate: bool = True) -> bool:
    """Перезапускает процесс sing-box с регенерацией свежей конфигурации"""
    stop_singbox()
    time.sleep(1)
    write_singbox_config()
    return start_singbox(force_generate=False)

def get_singbox_logs(lines_count: int = 100) -> list[str]:
    """Считывает последние строки из файла логов sing-box"""
    if not SINGBOX_LOG_PATH.exists():
        return []
    try:
        with open(SINGBOX_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-lines_count:]]
    except Exception as e:
        logging.error(f"Failed to read sing-box logs: {e}")
        return []

def get_singbox_client_traffic_stats() -> dict:
    """
    Опрашивает локальный Clash API Sing-box (127.0.0.1:9090/connections) 
    и возвращает байтовый объем трафика по email пользователей:
    { email: {"up": total_up, "down": total_down} }
    Также автоматически обновляет ACTIVE_IP_CACHE для онлайна и лимитов.
    """
    if not is_singbox_running():
        return {}
    import requests
    try:
        url = "http://127.0.0.1:9090/connections"
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            user_stats = {}
            connections = data.get("connections", [])
            now_ts = time.time()
            for conn in connections:
                metadata = conn.get("metadata", {})
                user = (
                    metadata.get("user")
                    or metadata.get("username")
                    or metadata.get("client")
                    or metadata.get("name")
                    or metadata.get("email")
                    or conn.get("user")
                    or conn.get("username")
                    or conn.get("client")
                    or conn.get("name")
                    or conn.get("email")
                    or conn.get("clientUser")
                    or conn.get("inboundUser")
                    or conn.get("auth_user")
                    or ""
                )
                if not user:
                    continue

                download = int(conn.get("download", 0))
                upload = int(conn.get("upload", 0))

                if user not in user_stats:
                    user_stats[user] = {"up": 0, "down": 0}
                user_stats[user]["down"] += download
                user_stats[user]["up"] += upload

                # Обновляем ACTIVE_IP_CACHE для отслеживания онлайна и ограничений IP
                src_ip = (
                    metadata.get("sourceIP")
                    or metadata.get("source_ip")
                    or metadata.get("clientIP")
                    or conn.get("sourceIP")
                    or conn.get("source_ip")
                    or "127.0.0.1"
                )
                try:
                    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                    if user not in ACTIVE_IP_CACHE:
                        ACTIVE_IP_CACHE[user] = {}
                    ACTIVE_IP_CACHE[user][src_ip] = now_ts
                except Exception:
                    pass

            return user_stats
    except Exception as e:
        logging.debug(f"Failed to query Sing-box Clash API stats: {e}")
    return {}

def _process_singbox_connection_data(data: dict):
    """
    Обрабатывает JSON структуру соединений от Sing-box Clash API (полученную по WebSocket или HTTP GET)
    и начисляет дельты трафика в ClientStats и Inbound.
    """
    global _last_singbox_conn_stats
    if not isinstance(data, dict):
        return

    from backend.database import update_client_traffic_by_email, update_inbound_traffic

    connections = data.get("connections", [])
    active_conn_ids = set()
    now_ts = time.time()

    for conn in connections:
        conn_id = str(conn.get("id") or "")
        if not conn_id:
            continue

        active_conn_ids.add(conn_id)
        metadata = conn.get("metadata", {})
        user = (
            metadata.get("user")
            or metadata.get("username")
            or metadata.get("client")
            or metadata.get("name")
            or metadata.get("email")
            or conn.get("user")
            or conn.get("username")
            or conn.get("client")
            or conn.get("name")
            or conn.get("email")
            or conn.get("clientUser")
            or conn.get("inboundUser")
            or conn.get("auth_user")
            or ""
        )

        download = int(conn.get("download", 0))
        upload = int(conn.get("upload", 0))

        prev_up, prev_down = _last_singbox_conn_stats.get(conn_id, (0, 0))

        up_delta = upload - prev_up if upload >= prev_up else upload
        down_delta = download - prev_down if download >= prev_down else download

        _last_singbox_conn_stats[conn_id] = (upload, download)

        # Обновляем ACTIVE_IP_CACHE для отслеживания онлайна и лимитов IP
        if user:
            src_ip = (
                metadata.get("sourceIP")
                or metadata.get("source_ip")
                or metadata.get("clientIP")
                or conn.get("sourceIP")
                or conn.get("source_ip")
                or "127.0.0.1"
            )
            try:
                from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                if user not in ACTIVE_IP_CACHE:
                    ACTIVE_IP_CACHE[user] = {}
                ACTIVE_IP_CACHE[user][src_ip] = now_ts
            except Exception:
                pass

        if up_delta > 0 or down_delta > 0:
            if user:
                update_client_traffic_by_email(user, up_delta, down_delta)

            inbound_tag = (
                metadata.get("inboundName")
                or metadata.get("inboundTag")
                or metadata.get("inbound")
                or metadata.get("type", "")
                or ""
            )
            if "inbound-" in inbound_tag:
                try:
                    ib_part = inbound_tag[inbound_tag.find("inbound-") + 8:].split("/")[0].split("-")[0]
                    ib_id = int(ib_part)
                    update_inbound_traffic(ib_id, up_delta, down_delta)
                except (ValueError, IndexError):
                    pass

    # Удаляем завершенные соединения из кэша
    stale_ids = set(_last_singbox_conn_stats.keys()) - active_conn_ids
    for s_id in stale_ids:
        del _last_singbox_conn_stats[s_id]

def query_singbox_traffic():
    """
    Опрашивает Clash API Sing-box (/connections) и производит по-соединениям (per-connection-ID)
    расчет дельт трафика, исключая потерю байт при разрывах сессий и сброс счетчиков.
    Обновляет ClientStats и Inbound в БД.
    """
    if not is_singbox_running():
        return

    _start_singbox_ws_stream()

    import requests
    try:
        url = "http://127.0.0.1:9090/connections"
        resp = requests.get(url, timeout=2)
        if resp.status_code != 200:
            return

        data = resp.json()
        _process_singbox_connection_data(data)

    except Exception as e:
        logging.debug(f"Failed to query Sing-box traffic: {e}")



