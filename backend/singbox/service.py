import os
import sys
import time
import json
import logging
from pathlib import Path
from backend.config import SINGBOX_BIN_PATH, SINGBOX_CONFIG_PATH, SINGBOX_LOG_PATH
from backend.singbox.config import write_singbox_config, get_all_inbounds

singbox_process = None
LAST_SINGBOX_ERROR = ""
_last_singbox_conn_stats = {}

def get_last_singbox_error() -> str:
    global LAST_SINGBOX_ERROR
    return LAST_SINGBOX_ERROR

def is_singbox_running() -> bool:
    """Проверяет, запущен ли процесс sing-box через sentinel-core supervisor"""
    global singbox_process
    if singbox_process is not None:
        if singbox_process.poll() is None:
            return True
        else:
            singbox_process = None

    try:
        from backend.sentinel_core_bridge import get_cores_status
        status = get_cores_status()
        if isinstance(status, dict):
            if "cores" in status and isinstance(status["cores"], list):
                for c in status["cores"]:
                    if c.get("name") in ("singbox", "sing-box") and c.get("running"):
                        return True
            elif status.get("sing-box", {}).get("running") or status.get("singbox", {}).get("running"):
                return True
    except Exception:
        pass

    try:
        import psutil
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                if any("check" in str(arg) for arg in cmdline):
                    continue
                name = (proc.info.get("name") or "").lower()
                if name in ("sing-box", "singbox", "sing-box.exe", "singbox.exe", SINGBOX_BIN_PATH.name.lower()):
                    return True
                if any("sing-box" in str(arg).lower() or "singbox" in str(arg).lower() for arg in cmdline):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass

    # Quick port / API probe fallback (Clash API on 127.0.0.1:9090)
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", 9090)) == 0:
                return True
    except Exception:
        pass

    return False

def start_singbox(force_generate: bool = False) -> bool:
    """Запускает процесс sing-box через sentinel-core"""
    global singbox_process, LAST_SINGBOX_ERROR
    LAST_SINGBOX_ERROR = ""
    if is_singbox_running():
        logging.info("Sing-box is already running.")
        return True

    inbounds = get_all_inbounds()
    has_active_singbox = False
    for ib in inbounds:
        if not ib.get("enable", 1):
            continue
        ib_core = ib.get("core") or ("hysteria" if ib.get("protocol") == "hysteria2" else "xray")
        if ib_core in ("singbox", "sing-box") or ib.get("protocol") in ("shadowtls", "naive"):
            has_active_singbox = True
            break

    if not has_active_singbox:
        logging.info("No active Sing-box inbounds found. Sing-box core will not be started.")
        stop_singbox()
        return True

    if not SINGBOX_BIN_PATH.exists():
        logging.error(f"Sing-box binary not found at {SINGBOX_BIN_PATH}")
        return False

    logging.info("Writing fresh Sing-box config before start...")
    write_singbox_config(force=force_generate)

    logging.info("Verifying Sing-box configuration...")
    try:
        from backend.sentinel_core_bridge import validate_core_config
        valid, out = validate_core_config("sing-box", str(SINGBOX_BIN_PATH), str(SINGBOX_CONFIG_PATH))
        if not valid:
            logging.error(f"Sing-box config verification failed: {out}")
            LAST_SINGBOX_ERROR = out
            return False
    except Exception as e:
        logging.error(f"Failed to run Sing-box config test: {e}")

    logging.info("Starting sing-box process via sentinel-core...")
    try:
        from backend.sentinel_core_bridge import start_core
        if start_core("sing-box", str(SINGBOX_BIN_PATH), str(SINGBOX_CONFIG_PATH)):
            logging.info("Sing-box started successfully via sentinel-core.")
            return True
        logging.error("sentinel-core failed to start sing-box.")
        return False
    except Exception as e:
        logging.error(f"Failed to start sing-box via sentinel-core: {e}")
        return False

def kick_all_singbox_connections():
    """Сбрасывает все активные сокеты и туннели клиентов через sentinel-core"""
    try:
        from backend.sentinel_core_bridge import kick_client
        kick_client("")
    except Exception:
        pass

def kick_singbox_user(username: str):
    """Сбрасывает соединения конкретного пользователя через sentinel-core"""
    if not username:
        return
    try:
        from backend.sentinel_core_bridge import kick_client
        kick_client(str(username).strip())
    except Exception:
        pass

def stop_singbox():
    """Останавливает процесс sing-box через sentinel-core"""
    global singbox_process, _last_singbox_conn_stats
    kick_all_singbox_connections()
    _last_singbox_conn_stats.clear()

    try:
        from backend.sentinel_core_bridge import stop_core
        stop_core("sing-box")
        logging.info("Sing-box stopped via sentinel-core.")
    except Exception as e:
        logging.error(f"Error stopping sing-box via sentinel-core: {e}")

    singbox_process = None

def restart_singbox(force_generate: bool = True) -> bool:
    """Перезапускает процесс sing-box с регенерацией свежей конфигурации"""
    stop_singbox()
    time.sleep(0.3)
    write_singbox_config(force=force_generate)
    return start_singbox(force_generate=force_generate)

def get_singbox_logs(lines_count: int = 100) -> list[str]:
    """Считывает последние строки из файла логов sing-box через sentinel-core supervisor"""
    if not SINGBOX_LOG_PATH.exists():
        return []
    try:
        from backend.sentinel_core_bridge import get_core_logs
        lines = get_core_logs(str(SINGBOX_LOG_PATH), lines_count)
        if lines:
            return [line.strip() for line in lines]

        with open(SINGBOX_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-lines_count:]]
    except Exception as e:
        logging.error(f"Failed to read sing-box logs: {e}")
        return []

def get_singbox_client_traffic_stats() -> dict:
    """
    Возвращает статистику трафика по email пользователей через sentinel-core:
    { email: {"up": total_up, "down": total_down} }
    """
    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic = get_unified_traffic()
        user_stats = {}
        if traffic and isinstance(traffic, dict):
            for email, stats in traffic.items():
                if isinstance(stats, dict):
                    user_stats[email] = {
                        "up": stats.get("upBytes", 0) or stats.get("up", 0) or stats.get("rx", 0),
                        "down": stats.get("downBytes", 0) or stats.get("down", 0) or stats.get("tx", 0)
                    }
        return user_stats
    except Exception as e:
        logging.debug(f"Failed to query Sing-box traffic stats: {e}")
        return {}

def _process_singbox_connection_data(data: dict):
    """
    Обрабатывает JSON структуру соединений Sing-box
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
            or metadata.get("clientUser")
            or metadata.get("inboundUser")
            or metadata.get("auth_user")
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

        inbound_tag = (
            metadata.get("inboundName")
            or metadata.get("inboundTag")
            or metadata.get("inbound")
            or metadata.get("type", "")
            or ""
        )
        ib_id = None
        if "inbound-" in inbound_tag:
            try:
                ib_part = inbound_tag[inbound_tag.find("inbound-") + 8:].split("/")[0].split("-")[0]
                ib_id = int(ib_part)
            except (ValueError, IndexError):
                pass

        if user:
            user = str(user).strip("[]").strip()
        elif ib_id is not None:
            try:
                from backend.database import get_clients_for_inbound
                ib_clients = get_clients_for_inbound(ib_id)
                active_ib_clients = [c for c in ib_clients if c.get("enable", True)]
                if len(active_ib_clients) == 1:
                    user = active_ib_clients[0]["email"]
                elif len(ib_clients) == 1:
                    user = ib_clients[0]["email"]
            except Exception:
                pass

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

                if src_ip and src_ip != "127.0.0.1":
                    from backend.sentinel_core_bridge import register_external_connect
                    register_external_connect("sing-box", user, src_ip)
            except Exception:
                pass

        if up_delta > 0 or down_delta > 0:
            if user:
                from backend.database import update_client_traffic
                updated_client = False
                if ib_id is not None:
                    updated_client = update_client_traffic(ib_id, user, up_delta, down_delta)
                if not updated_client:
                    update_client_traffic_by_email(user, up_delta, down_delta)

            if ib_id is not None:
                update_inbound_traffic(ib_id, up_delta, down_delta)

            outbound_tag = (
                conn.get("outbound")
                or conn.get("outboundName")
                or metadata.get("outbound")
                or metadata.get("outboundName")
                or (isinstance(conn.get("chains"), list) and conn.get("chains") and conn.get("chains")[0])
                or ""
            )
            if outbound_tag:
                try:
                    from backend.database import update_outbound_traffic
                    update_outbound_traffic(outbound_tag, up_delta, down_delta)
                except Exception:
                    pass

    # Удаляем завершенные соединения из кэша
    stale_ids = set(_last_singbox_conn_stats.keys()) - active_conn_ids
    for s_id in stale_ids:
        del _last_singbox_conn_stats[s_id]

def query_singbox_traffic():
    """
    Считывает трафик Sing-box через C-FFI sentinel-core bridge
    и начисляет точные дельты трафика и статус онлайн в реальном времени.
    """
    if not is_singbox_running():
        return

    try:
        from backend.sentinel_core_bridge import get_unified_traffic
        traffic_data = get_unified_traffic()
        if not traffic_data or not isinstance(traffic_data, dict):
            return

        from backend.database import update_client_traffic_by_email, get_all_inbounds, update_inbound_traffic
        inbounds = get_all_inbounds()
        singbox_inbounds = [ib for ib in inbounds if ib.get("core") == "singbox" and ib.get("enable")]
        now_ts = time.time()

        for email, stats in traffic_data.items():
            if not isinstance(stats, dict):
                continue
            up = int(stats.get("upBytes", 0))
            down = int(stats.get("downBytes", 0))

            prev_up, prev_down = _last_singbox_conn_stats.get(email, (0, 0))
            up_delta = up - prev_up if up >= prev_up else up
            down_delta = down - prev_down if down >= prev_down else down
            _last_singbox_conn_stats[email] = (up, down)

            if stats.get("online") or stats.get("connections", 0) > 0:
                try:
                    from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE
                    if email not in ACTIVE_IP_CACHE:
                        ACTIVE_IP_CACHE[email] = {}
                    ACTIVE_IP_CACHE[email]["127.0.0.1"] = now_ts
                except Exception:
                    pass

            if up_delta > 0 or down_delta > 0:
                update_client_traffic_by_email(email, up_delta, down_delta)
                for ib in singbox_inbounds:
                    update_inbound_traffic(ib["id"], up_delta, down_delta)
    except Exception as e:
        logging.debug(f"Failed to query Sing-box traffic via sentinel-core: {e}")
