import os
import sys
import json
import socket
import logging
import threading
import time

try:
    import psutil
except ImportError:
    psutil = None

_cached_stats = {
    "cpu": 0.0,
    "mem": {"current": 0, "total": 0},
    "swap": {"current": 0, "total": 0, "percent": 0.0},
    "uptime": 0,
    "netIO": {"up": 0, "down": 0},
    "disk": {"current": 0, "total": 0, "percent": 0.0}
}
_boot_time = 0.0

def _stats_worker():
    global _cached_stats, _boot_time
    if psutil is None:
        return
    try:
        _boot_time = psutil.boot_time()
        psutil.cpu_percent(interval=None)
    except Exception:
        pass
    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            try:
                swap = psutil.swap_memory()
                swap_dict = {"current": swap.used, "total": swap.total, "percent": swap.percent}
            except Exception:
                swap_dict = {"current": 0, "total": 0, "percent": 0.0}
            try:
                disk = psutil.disk_usage('/')
                disk_dict = {"current": disk.used, "total": disk.total, "percent": disk.percent}
            except Exception:
                disk_dict = {"current": 0, "total": 0, "percent": 0.0}
            net_io = psutil.net_io_counters()
            
            _cached_stats["cpu"] = cpu
            _cached_stats["mem"] = {"current": mem.used, "total": mem.total}
            _cached_stats["swap"] = swap_dict
            _cached_stats["disk"] = disk_dict
            _cached_stats["netIO"] = {"up": net_io.bytes_sent, "down": net_io.bytes_recv}
        except Exception as e:
            logging.error(f"Error in stats worker thread: {e}")
        time.sleep(2.0)

if psutil is not None:
    threading.Thread(target=_stats_worker, daemon=True).start()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [HostClient] - %(levelname)s - %(message)s")

SOCKET_PATH = "/var/run/spectre/agent.sock"

class HostClient:
    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = socket_path
        self.is_linux = sys.platform == "linux"
        self._mock_logged = False
        self._conn_failed_logged = False
        
        # Mock WARP State for testing/development
        self._mock_file = "warp_mock.json"
        self.load_mock_state()

    def load_mock_state(self):
        self.mock_warp_installed = False
        self.mock_warp_connected = False
        self.mock_warp_type = "free"
        self.mock_warp_license = ""
        if os.path.exists(self._mock_file):
            try:
                with open(self._mock_file, "r") as f:
                    data = json.load(f)
                    self.mock_warp_installed = data.get("installed", False)
                    self.mock_warp_connected = data.get("connected", False)
                    self.mock_warp_type = data.get("type", "free")
                    self.mock_warp_license = data.get("license", "")
            except Exception:
                pass

    def save_mock_state(self):
        try:
            with open(self._mock_file, "w") as f:
                json.dump({
                    "installed": self.mock_warp_installed,
                    "connected": self.mock_warp_connected,
                    "type": self.mock_warp_type,
                    "license": self.mock_warp_license
                }, f)
        except Exception:
            pass

    @property
    def is_mock(self) -> bool:
        if not self.is_linux:
            return True
        socket_exists = os.path.exists(self.socket_path)
        if not socket_exists:
            if not self._mock_logged:
                logging.info("HostClient is running in MOCK mode (socket file not found).")
                self._mock_logged = True
            return True
        else:
            if self._mock_logged:
                logging.info("HostClient socket detected, exiting MOCK mode.")
                self._mock_logged = False
            return False

    def send_command(self, action: str, params: dict = None, timeout: float = 3.0) -> dict:
        if self.is_mock:
            return self._mock_response(action, params)

        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(timeout)
            client.connect(self.socket_path)
            
            # Reset connection failed log flag on success
            self._conn_failed_logged = False
            
            payload = {"action": action}
            if params:
                payload.update(params)
                
            client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            
            # Read response
            buffer = ""
            while True:
                data = client.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8")
                if "\n" in buffer:
                    break
            
            client.close()
            
            if "\n" in buffer:
                line = buffer.split("\n", 1)[0]
                return json.loads(line)
            else:
                return {"success": False, "msg": "No valid response from agent"}
        except Exception as e:
            if not self._conn_failed_logged:
                logging.error(f"Failed to communicate with host agent over socket: {e}")
                self._conn_failed_logged = True
            if action == "reboot_system" and self.is_linux:
                def _do_reboot():
                    time.sleep(1)
                    os.system("sudo reboot || reboot")
                threading.Thread(target=_do_reboot, daemon=True).start()
                return {"success": True, "msg": "Инициализирована перезагрузка системы..."}
            return {"success": False, "msg": f"Ошибка связи с хост-агентом: {str(e)}"}

    def _mock_response(self, action: str, params: dict = None) -> dict:
        if action == "get_bbr_status":
            return {"success": True, "bbr_enabled": False}
        elif action == "enable_bbr":
            return {"success": True, "msg": "[Mock] BBR enabled (mock configuration successful)."}
        elif action == "get_optimization_status":
            return {"success": True, "optimized": False}
        elif action == "apply_optimizations":
            return {"success": True, "msg": "[Mock] Network optimized."}
        elif action == "get_system_stats":
            # Try to get local stats using psutil if available
            stats = {
                "success": True,
                "cpu": 0.0,
                "mem": {"current": 0, "total": 0},
                "uptime": 0,
                "netIO": {"up": 0, "down": 0}
            }
            try:
                stats["cpu"] = _cached_stats["cpu"]
                if psutil is not None:
                    stats["mem"] = _cached_stats["mem"].copy()
                    stats["uptime"] = int(time.time() - _boot_time) if _boot_time else 0
                    stats["netIO"] = _cached_stats["netIO"].copy()
                else:
                    raise Exception("psutil not available")
            except Exception:
                # hardcoded mock values if psutil is not available
                stats["cpu"] = 15.4
                stats["mem"] = {"current": 1024 * 1024 * 512, "total": 1024 * 1024 * 2048}
                stats["uptime"] = 3600
                stats["netIO"] = {"up": 1234567, "down": 7654321}
            return stats
        elif action == "get_warp_status":
            is_plus = self.mock_warp_type == "plus"
            return {
                "installed": self.mock_warp_installed,
                "connected": self.mock_warp_connected,
                "registration": self.mock_warp_type,
                "type": self.mock_warp_type,
                "license": self.mock_warp_license,
                "socks_port": 40000,
                "quota": 100 * 1024 * 1024 * 1024 if is_plus else 0,
                "usage": 25 * 1024 * 1024 * 1024 if is_plus else 0
            }
        elif action == "install_warp":
            self.mock_warp_installed = True
            self.mock_warp_connected = True
            self.mock_warp_type = "free"
            self.save_mock_state()
            return {"success": True, "msg": "[Mock] Cloudflare WARP installed and connected."}
        elif action == "register_warp":
            if not self.mock_warp_installed:
                return {"success": False, "msg": "WARP is not installed."}
            license_key = params.get("license_key") if params else None
            if license_key:
                license_key = license_key.strip()
                if len(license_key) < 15:
                    return {"success": False, "msg": "License key validation failed: key is too short or invalid"}
                self.mock_warp_type = "plus"
                self.mock_warp_license = license_key
                self.save_mock_state()
                return {"success": True, "msg": "[Mock] WARP+ License key applied successfully."}
            else:
                self.mock_warp_type = "free"
                self.mock_warp_license = ""
                self.save_mock_state()
                return {"success": True, "msg": "[Mock] Registered free WARP account."}
        elif action == "connect_warp":
            if not self.mock_warp_installed:
                return {"success": False, "msg": "WARP is not installed."}
            self.mock_warp_connected = True
            self.save_mock_state()
            return {"success": True, "msg": "[Mock] WARP connected."}
        elif action == "disconnect_warp":
            if not self.mock_warp_installed:
                return {"success": False, "msg": "WARP is not installed."}
            self.mock_warp_connected = False
            self.save_mock_state()
            return {"success": True, "msg": "[Mock] WARP disconnected."}
        elif action == "uninstall_warp":
            self.mock_warp_installed = False
            self.mock_warp_connected = False
            self.mock_warp_type = "free"
            self.mock_warp_license = ""
            self.save_mock_state()
            return {"success": True, "msg": "[Mock] WARP uninstalled."}
        elif action == "reboot_system":
            return {"success": True, "msg": "[Mock] Команда перезагрузки системы выполнена успешно."}
        return {"success": False, "msg": f"Unknown action in mock: {action}"}

# Global client instance
host_client = HostClient()
