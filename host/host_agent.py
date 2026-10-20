import os
import sys
import json
import socket
import logging
import signal
import threading
from pathlib import Path

# Add the directory and project root to sys.path to allow running directly from anywhere on the host
_host_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_host_dir)
for _p in [_parent_dir, _host_dir, "/opt/sentinel-panel"]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from agent.optimizations import (
    get_bbr_status,
    enable_bbr,
    get_optimization_status,
    apply_network_optimizations,
    get_ipv6_status,
    set_ipv6_disabled,
)
from agent.monitor import get_system_stats
from agent.warp import (
    get_warp_status,
    install_warp,
    register_warp,
    connect_warp,
    disconnect_warp,
    uninstall_warp,
)


# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [HostAgent] - %(levelname)s - %(message)s")

SOCKET_DIR = Path("/var/run/sentinel")
SOCKET_PATH = SOCKET_DIR / "agent.sock"

def _resolve_bin_dir() -> str:
    """Find the valid bin directory for sentinel-core."""
    candidates = [
        os.path.join(_parent_dir, "bin"),
        "/opt/sentinel-panel/bin",
        os.path.abspath("bin"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    target = os.path.join(_parent_dir, "bin")
    os.makedirs(target, exist_ok=True)
    return target

def handle_client(conn):
    """Handles Unix socket client connection."""
    buffer = ""
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buffer += data.decode("utf-8")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                    action = request.get("action")
                    logging.info(f"Received request for action: {action}")
                    
                    response = {"success": False, "msg": "Unknown action"}
                    
                    if action == "get_bbr_status":
                        response = {"success": True, "bbr_enabled": get_bbr_status()}
                    elif action == "enable_bbr":
                        success, msg = enable_bbr()
                        response = {"success": success, "msg": msg}
                    elif action == "get_system_stats":
                        response = get_system_stats()
                    elif action == "get_optimization_status":
                        response = {"success": True, "optimized": get_optimization_status()}
                    elif action == "apply_optimizations":
                        success, msg = apply_network_optimizations()
                        response = {"success": success, "msg": msg}
                    elif action == "get_ipv6_status":
                        status = get_ipv6_status()
                        response = {"success": True, "ipv6_disabled": status.get("ipv6_disabled", False), "supported": status.get("supported", True)}
                    elif action == "set_ipv6_disabled":
                        disable = request.get("disable", True)
                        success, msg = set_ipv6_disabled(disable)
                        response = {"success": success, "msg": msg}
                    elif action == "get_warp_status":
                        response = get_warp_status()
                    elif action == "install_warp":
                        success, msg = install_warp()
                        response = {"success": success, "msg": msg}
                    elif action == "register_warp":
                        license_key = request.get("license_key")
                        success, msg = register_warp(license_key)
                        response = {"success": success, "msg": msg}
                    elif action == "connect_warp":
                        success, msg = connect_warp()
                        response = {"success": success, "msg": msg}
                    elif action == "disconnect_warp":
                        success, msg = disconnect_warp()
                        response = {"success": success, "msg": msg}
                    elif action == "uninstall_warp":
                        success, msg = uninstall_warp()
                        response = {"success": success, "msg": msg}
                    elif action == "trigger_panel_update":
                        import subprocess
                        update_scripts = [
                            os.path.join(_parent_dir, "update.sh"),
                            "/opt/sentinel-panel/update.sh",
                            "update.sh",
                        ]
                        update_script = next((s for s in update_scripts if os.path.isfile(s)), None)
                        if update_script:
                            subprocess.Popen(["bash", update_script], start_new_session=True)
                            response = {"success": True, "msg": "Служба обновления запущена на хост-сервере."}
                        else:
                            response = {"success": False, "msg": "Скрипт обновления update.sh не найден."}
                    elif action == "get_core_version":
                        bin_dir = _resolve_bin_dir()
                        try:
                            from updater.core.sentinel_core import SentinelCoreManager
                            mgr = SentinelCoreManager(bin_dir=bin_dir, auto_mode=True)
                            is_installed, current_ver = mgr.get_installed_version()
                            response = {"success": True, "is_installed": is_installed, "version": current_ver}
                        except Exception as ce:
                            response = {"success": False, "msg": str(ce)}
                    elif action == "trigger_core_update":
                        core_ver = str(request.get("version", "")).strip()
                        force = bool(request.get("force", False))
                        bin_dir = _resolve_bin_dir()
                        installed_ok = False
                        inst_ver = ""
                        err_msg = ""

                        # Attempt 1: Modular updater SentinelCoreManager
                        try:
                            from updater.core.sentinel_core import SentinelCoreManager
                            mgr = SentinelCoreManager(bin_dir=bin_dir, auto_mode=True, force=force)
                            if not core_ver:
                                stable_v, _, latest_v = mgr.fetch_releases()
                                core_ver = stable_v or latest_v
                            if core_ver and mgr.download_core(core_ver):
                                _, inst_ver = mgr.get_installed_version()
                                installed_ok = True
                                response = {"success": True, "version": inst_ver or core_ver, "msg": f"Sentinel ядро {inst_ver or core_ver} успешно установлено."}
                            else:
                                err_msg = "Не удалось загрузить ядро через SentinelCoreManager."
                        except Exception as ce:
                            err_msg = str(ce)
                            logging.warning(f"HostAgent SentinelCoreManager update error: {ce}")

                        # Attempt 2: Fallback to fetch_core.sh script
                        if not installed_ok:
                            fetch_candidates = [
                                os.path.join(_parent_dir, "installation", "fetch_core.sh"),
                                "/opt/sentinel-panel/installation/fetch_core.sh",
                                os.path.abspath("installation/fetch_core.sh"),
                            ]
                            fetch_script = next((s for s in fetch_candidates if os.path.isfile(s)), None)
                            if fetch_script:
                                try:
                                    import subprocess
                                    cmd = ["bash", fetch_script, bin_dir, "--auto"]
                                    if force:
                                        cmd.append("--force")
                                    sub_res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                                    if sub_res.returncode == 0:
                                        installed_ok = True
                                        response = {
                                            "success": True,
                                            "version": core_ver or "latest",
                                            "msg": f"Sentinel ядро успешно установлено через {os.path.basename(fetch_script)}.",
                                        }
                                    else:
                                        response = {
                                            "success": False,
                                            "msg": f"Ошибка {fetch_script}: {sub_res.stderr or sub_res.stdout or err_msg}",
                                        }
                                except Exception as fe:
                                    response = {"success": False, "msg": f"{err_msg}; fallback error: {fe}"}
                            else:
                                response = {"success": False, "msg": err_msg or "Ошибка установки ядра"}
                        
                    conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                except json.JSONDecodeError:
                    conn.sendall(json.dumps({"success": False, "msg": "Invalid JSON"}).encode("utf-8") + b"\n")
                except Exception as e:
                    logging.error(f"Error processing command: {e}")
                    conn.sendall(json.dumps({"success": False, "msg": str(e)}).encode("utf-8") + b"\n")
    except Exception as e:
        logging.error(f"Connection error: {e}")
    finally:
        conn.close()

def cleanup_socket():
    """Removes the socket file."""
    if SOCKET_PATH.exists():
        try:
            SOCKET_PATH.unlink()
            logging.info("Cleaned up UNIX socket file.")
        except Exception as e:
            logging.error(f"Failed to remove socket file: {e}")

def signal_handler(signum, frame):
    logging.info(f"Signal {signum} received. Shutting down...")
    cleanup_socket()
    sys.exit(0)

def main():
    if sys.platform != "linux":
        logging.error("HostAgent is only supported on Linux host systems.")
        sys.exit(1)

    # Register signals for clean exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Ensure socket directory exists
    SOCKET_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_socket()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(SOCKET_PATH))
        server.listen(5)
        
        # Set broad permissions so the docker group or containers can access it
        try:
            os.chmod(str(SOCKET_PATH), 0o666)
            # Try to chown to docker group if exists
            import grp
            try:
                docker_grp = grp.getgrnam("docker")
                os.chown(str(SOCKET_PATH), 0, docker_grp.gr_gid)
                os.chmod(str(SOCKET_PATH), 0o660) # 0660 is secure enough if group is docker
                logging.info("Socket permissions set to 0660 (root:docker)")
            except KeyError:
                # Docker group not found, leave 0666 so any container user can connect
                os.chmod(str(SOCKET_PATH), 0o666)
                logging.info("Socket permissions set to 0666 (docker group not found)")
        except Exception as e:
            logging.warning(f"Could not adjust socket permissions: {e}")

        logging.info(f"UNIX socket listener started at {SOCKET_PATH}")
        
        # Handle connection loop
        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
            
    except Exception as e:
        logging.critical(f"HostAgent crashed: {e}")
    finally:
        server.close()
        cleanup_socket()

if __name__ == "__main__":
    main()
