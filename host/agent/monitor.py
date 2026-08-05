import time
import logging
import threading

try:
    import psutil
except ImportError:
    psutil = None

_cached_stats = {
    "cpu": 0.0,
    "mem": {"current": 0, "total": 0},
    "swap": {"current": 0, "total": 0, "percent": 0.0},
    "uptime": 0,
    "netIO": {"up": 0, "down": 0}
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
            net_io = psutil.net_io_counters()
            
            _cached_stats["cpu"] = cpu
            _cached_stats["mem"] = {"current": mem.used, "total": mem.total}
            _cached_stats["swap"] = swap_dict
            _cached_stats["netIO"] = {"up": net_io.bytes_sent, "down": net_io.bytes_recv}
        except Exception as e:
            logging.error(f"Error in stats worker thread: {e}")
        time.sleep(2.0)

if psutil is not None:
    threading.Thread(target=_stats_worker, daemon=True).start()

def get_system_stats() -> dict:
    """Gathers real host-level metrics."""
    global psutil
    stats = {
        "success": True,
        "cpu": 0.0,
        "mem": {"current": 0, "total": 0},
        "swap": {"current": 0, "total": 0, "percent": 0.0},
        "uptime": 0,
        "netIO": {"up": 0, "down": 0}
    }
    
    # Try importing psutil if not already loaded
    if psutil is None:
        try:
            import psutil as ps
            psutil = ps
            # Start worker if psutil became available
            threading.Thread(target=_stats_worker, daemon=True).start()
        except ImportError:
            pass

    if psutil is not None:
        try:
            stats["cpu"] = _cached_stats["cpu"]
            stats["mem"] = _cached_stats["mem"].copy()
            stats["swap"] = _cached_stats["swap"].copy()
            stats["uptime"] = int(time.time() - _boot_time) if _boot_time else 0
            stats["netIO"] = _cached_stats["netIO"].copy()
            return stats
        except Exception as e:
            logging.error(f"Error collecting host stats via psutil: {e}")
            # Fall back to native proc parsing on exception

    # Native fallback parsing of /proc (requires no external libraries)
    try:
        # Uptime
        with open("/proc/uptime", "r") as f:
            stats["uptime"] = int(float(f.readline().split()[0]))
    except Exception as e:
        logging.debug(f"Error parsing /proc/uptime: {e}")

    try:
        # Memory
        with open("/proc/meminfo", "r") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        meminfo[parts[0].rstrip(":")] = int(parts[1]) * 1024
                    except ValueError:
                        continue
            total = meminfo.get("MemTotal", 0)
            free = meminfo.get("MemFree", 0)
            buffers = meminfo.get("Buffers", 0)
            cached = meminfo.get("Cached", 0)
            used = total - free - buffers - cached
            stats["mem"]["current"] = max(0, used)
            stats["mem"]["total"] = total
            
            swap_total = meminfo.get("SwapTotal", 0)
            swap_free = meminfo.get("SwapFree", 0)
            swap_used = swap_total - swap_free
            stats["swap"]["total"] = swap_total
            stats["swap"]["current"] = max(0, swap_used)
            stats["swap"]["percent"] = round((swap_used / swap_total) * 100, 1) if swap_total > 0 else 0.0
    except Exception as e:
        logging.error(f"Error parsing /proc/meminfo: {e}")

    try:
        # CPU usage from loadavg
        with open("/proc/loadavg", "r") as f:
            load = float(f.readline().split()[0])
            import os
            cpu_count = os.cpu_count() or 1
            stats["cpu"] = min(100.0, round((load / cpu_count) * 100, 1))
    except Exception as e:
        logging.debug(f"Error parsing /proc/loadavg: {e}")

    try:
        # Network IO
        with open("/proc/net/dev", "r") as f:
            lines = f.readlines()
            up = 0
            down = 0
            for line in lines[2:]:
                parts = line.split()
                if not parts:
                    continue
                # Handle cases where interface name has no space after colon (e.g., eth0:12345)
                interface_part = parts[0]
                if ":" in interface_part:
                    name, rest = interface_part.split(":", 1)
                    if rest:
                        try:
                            down += int(rest)
                            if len(parts) >= 9:
                                up += int(parts[8])
                        except ValueError:
                            pass
                        continue
                if len(parts) >= 10:
                    try:
                        down += int(parts[1])
                        up += int(parts[9])
                    except ValueError:
                        pass
            stats["netIO"]["up"] = up
            stats["netIO"]["down"] = down
    except Exception as e:
        logging.error(f"Error parsing /proc/net/dev: {e}")

    return stats

