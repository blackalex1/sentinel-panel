import os
import sys
import json
import socket
import logging
import signal
from pathlib import Path

# Add the directory to sys.path to allow running directly from anywhere on the host
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.optimizations import (
    get_bbr_status,
    enable_bbr,
    get_optimization_status,
    apply_network_optimizations,
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

SOCKET_DIR = Path("/var/run/spectre")
SOCKET_PATH = SOCKET_DIR / "agent.sock"

def handle_client(conn):
    """Handles Unix socket client connection."""
    buffer = ""
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buffer += data.decode("utf-8")
            if "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
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
            handle_client(conn)
            
    except Exception as e:
        logging.critical(f"HostAgent crashed: {e}")
    finally:
        server.close()
        cleanup_socket()

if __name__ == "__main__":
    main()
