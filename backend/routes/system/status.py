import time
import psutil
from fastapi import APIRouter, Request

from backend.host_client import host_client
from backend.xray import is_xray_running, get_installed_xray_version
from backend.hysteria import is_hysteria_running, get_installed_hysteria_version
import backend.routes.system

router = APIRouter()

@router.get("/panel/api/server/status")
async def server_status_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    # Собираем метрики системы из хост-агента
    stats = host_client.send_command("get_system_stats")
    if stats.get("success"):
        cpu_percent = stats.get("cpu", 0.0)
        mem_current = stats.get("mem", {}).get("current", 0)
        mem_total = stats.get("mem", {}).get("total", 0)
        swap_current = stats.get("swap", {}).get("current", 0)
        swap_total = stats.get("swap", {}).get("total", 0)
        swap_percent = stats.get("swap", {}).get("percent", 0.0)
        uptime = stats.get("uptime", 0)
        net_up = stats.get("netIO", {}).get("up", 0)
        net_down = stats.get("netIO", {}).get("down", 0)
    else:
        # Резервный вариант сбора локальных метрик
        from backend.host_client import _cached_stats, _boot_time
        cpu_percent = _cached_stats["cpu"]
        mem_current = _cached_stats["mem"]["current"]
        mem_total = _cached_stats["mem"]["total"]
        swap_current = _cached_stats["swap"]["current"]
        swap_total = _cached_stats["swap"]["total"]
        swap_percent = _cached_stats["swap"]["percent"]
        uptime = int(time.time() - _boot_time) if _boot_time else 0
        net_up = _cached_stats["netIO"]["up"]
        net_down = _cached_stats["netIO"]["down"]
    
    # Disk stats
    from backend.host_client import _cached_stats
    disk_current = _cached_stats["disk"]["current"]
    disk_total = _cached_stats["disk"]["total"]
    disk_percent = _cached_stats["disk"]["percent"]

    # Получаем версию xray, hysteria и sing-box
    xray_status = "running" if is_xray_running() else "stopped"
    hysteria_status = "running" if is_hysteria_running() else "stopped"
    
    from backend.singbox import is_singbox_running, get_installed_singbox_version
    singbox_status = "running" if is_singbox_running() else "stopped"
    singbox_version = get_installed_singbox_version() or "Неизвестно"
    
    return {
        "success": True,
        "obj": {
            "cpu": cpu_percent,
            "mem": {
                "current": mem_current,
                "total": mem_total
            },
            "swap": {
                "current": swap_current,
                "total": swap_total,
                "percent": swap_percent
            },
            "disk": {
                "current": disk_current,
                "total": disk_total,
                "percent": disk_percent
            },
            "uptime": uptime,
            "netIO": {
                "up": net_up,
                "down": net_down
            },
            "xray": {
                "state": xray_status,
                "version": get_installed_xray_version()
            },
            "hysteria": {
                "state": hysteria_status,
                "version": get_installed_hysteria_version()
            },
            "singbox": {
                "state": singbox_status,
                "version": singbox_version
            }
        }
    }

@router.get("/panel/api/system/global-traffic")
async def global_traffic_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    import datetime
    from sqlalchemy import func
    from backend.database import db_session
    from backend.models import ClientTrafficDaily
    
    # Calculate cutoff date (30 days ago)
    today = datetime.date.today()
    cutoff_date = (today - datetime.timedelta(days=30)).isoformat()
    
    with db_session() as session:
        records = session.query(
            ClientTrafficDaily.date,
            func.sum(ClientTrafficDaily.up).label("total_up"),
            func.sum(ClientTrafficDaily.down).label("total_down")
        ).filter(ClientTrafficDaily.date >= cutoff_date)\
         .group_by(ClientTrafficDaily.date)\
         .order_by(ClientTrafficDaily.date)\
         .all()
         
    result = []
    # Fill in missing dates with 0
    date_map = {r.date: (r.total_up, r.total_down) for r in records}
    
    for i in range(30):
        d = (today - datetime.timedelta(days=29 - i)).isoformat()
        up, down = date_map.get(d, (0, 0))
        result.append({
            "date": d,
            "up": up or 0,
            "down": down or 0
        })
        
    return {"success": True, "obj": result}

@router.get("/panel/api/system/global-traffic-details")
async def global_traffic_details_api(request: Request, date: str = ""):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()

    import datetime
    from backend.database import db_session
    from backend.models import ClientTrafficDaily

    target_date = date.strip() or datetime.date.today().isoformat()

    with db_session() as session:
        records = session.query(
            ClientTrafficDaily.email,
            ClientTrafficDaily.up,
            ClientTrafficDaily.down
        ).filter(ClientTrafficDaily.date == target_date).all()

        total_day_up = sum(r.up or 0 for r in records)
        total_day_down = sum(r.down or 0 for r in records)
        total_day_bytes = total_day_up + total_day_down

        clients = []
        for r in records:
            up_bytes = int(r.up or 0)
            down_bytes = int(r.down or 0)
            total_bytes = up_bytes + down_bytes
            pct = round((total_bytes / total_day_bytes * 100), 2) if total_day_bytes > 0 else 0.0
            clients.append({
                "email": r.email,
                "up": up_bytes,
                "down": down_bytes,
                "total": total_bytes,
                "percent": pct
            })

        clients.sort(key=lambda x: x["total"], reverse=True)

    return {
        "success": True,
        "date": target_date,
        "total_up": total_day_up,
        "total_down": total_day_down,
        "total_bytes": total_day_bytes,
        "clients": clients
    }

@router.post("/panel/api/system/reboot")
async def system_reboot_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    res = host_client.send_command("reboot_system")
    return res

