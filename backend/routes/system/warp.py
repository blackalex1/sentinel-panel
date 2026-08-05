import logging
from fastapi import APIRouter, Request

from backend.host_client import host_client
from backend.database import get_setting
import backend.routes.system

router = APIRouter()

def sync_warp_outbound_state(warp_connected: bool):
    """Синхронизирует исходящее подключение warp в БД и перезапускает Xray при необходимости"""
    from backend.database import db_session
    from backend.models import Outbound, RoutingRule
    from backend.xray import write_xray_config, restart_xray
    
    changed = False
    with db_session() as session:
        # Проверяем, существует ли уже warp outbound в БД
        warp_ob = session.query(Outbound).filter_by(tag="warp").first()
        
        if warp_connected:
            if not warp_ob:
                # Создаем новое исходящее подключение (SOCKS5 proxy, порт 40000)
                warp_ob = Outbound(
                    remark="WARP Proxy (SOCKS5)",
                    protocol="socks",
                    tag="warp",
                    settings='{"servers": [{"address": "127.0.0.1", "port": 40000}]}',
                    enable=1,
                    is_system=0
                )
                session.add(warp_ob)
                changed = True
                logging.info("WARP outbound created dynamically (WARP is connected).")
            elif warp_ob.enable != 1:
                warp_ob.enable = 1
                changed = True
                logging.info("WARP outbound enabled dynamically (WARP is connected).")
        else:
            # Если WARP отключен или не установлен, отключаем outbound в БД
            if warp_ob and warp_ob.enable == 1:
                warp_ob.enable = 0
                changed = True
                logging.info("WARP outbound disabled dynamically (WARP is disconnected).")
                
                # Также отключаем правила маршрутизации, ссылающиеся на warp, чтобы избежать ошибок старта Xray
                rules = session.query(RoutingRule).filter_by(outbound_tag="warp", enable=1).all()
                for r in rules:
                    r.enable = 0
                    logging.info(f"Routing rule '{r.remark}' disabled dynamically because warp tag is offline.")
                    
    if changed:
        try:
            write_xray_config()
            restart_xray()
            logging.info("Xray config regenerated and core restarted successfully after WARP sync.")
        except Exception as e:
            logging.error(f"Failed to restart Xray during WARP sync: {e}")


@router.get("/api/system/warp/status")
async def get_warp_status_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    status = host_client.send_command("get_warp_status", timeout=15.0)
    if not isinstance(status, dict):
        status = {}
        
    # Синхронизируем состояние БД в зависимости от статуса хоста
    if "connected" in status:
        sync_warp_outbound_state(status["connected"])
        
    # Добавляем сохраненную лицензию из БД, если на хосте она пустая или не установлена
    db_license = get_setting("warp_license", "")
    if not status.get("license") and db_license:
        status["license"] = db_license
        
    # Находим активные правила маршрутизации, зависящие от warp
    from backend.database import db_session
    from backend.models import RoutingRule
    dependent_rules = []
    try:
        with db_session() as session:
            rules = session.query(RoutingRule).filter_by(outbound_tag="warp", enable=1).all()
            dependent_rules = [{"id": r.id, "remark": r.remark or f"Rule #{r.id}"} for r in rules]
    except Exception as e:
        logging.error(f"Failed to query dependent routing rules: {e}")
        
    status["dependent_rules"] = dependent_rules
    return status


@router.post("/api/system/warp/install")
async def install_warp_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    res = host_client.send_command("install_warp", timeout=180.0)
    
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    if res.get("success"):
        log_action(actor, "install_warp", details="status:success")
        sync_warp_outbound_state(True)
    else:
        log_action(actor, "install_warp", details=f"status:failed, error:{res.get('msg')}")
        
    return res


@router.post("/api/system/warp/connect")
async def connect_warp_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    res = host_client.send_command("connect_warp", timeout=15.0)
    
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    if res.get("success"):
        log_action(actor, "connect_warp", details="status:success")
        sync_warp_outbound_state(True)
    else:
        log_action(actor, "connect_warp", details=f"status:failed, error:{res.get('msg')}")
        
    return res


@router.post("/api/system/warp/disconnect")
async def disconnect_warp_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    res = host_client.send_command("disconnect_warp", timeout=15.0)
    
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    if res.get("success"):
        log_action(actor, "disconnect_warp", details="status:success")
        sync_warp_outbound_state(False)
    else:
        log_action(actor, "disconnect_warp", details=f"status:failed, error:{res.get('msg')}")
        
    return res


@router.post("/api/system/warp/register")
async def register_warp_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    try:
        data = await request.json()
    except Exception:
        data = {}
        
    license_key = data.get("license_key")
    
    # Сохраняем лицензионный ключ в базу данных системных настроек
    from backend.database import set_setting
    if license_key is not None:
        set_setting("warp_license", license_key.strip())
        
    res = host_client.send_command("register_warp", {"license_key": license_key}, timeout=30.0)
    
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    if res.get("success"):
        details = f"status:success, license:{license_key[:4] + '...' if license_key else 'free'}"
        log_action(actor, "register_warp", details=details)
        
        # Запрашиваем новый статус и синхронизируем
        status = host_client.send_command("get_warp_status", timeout=15.0)
        if isinstance(status, dict) and "connected" in status:
            sync_warp_outbound_state(status["connected"])
    else:
        log_action(actor, "register_warp", details=f"status:failed, error:{res.get('msg')}")
        
    return res


@router.post("/api/system/warp/uninstall")
async def uninstall_warp_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
        
    res = host_client.send_command("uninstall_warp", timeout=120.0)
    
    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request)
    
    if res.get("success"):
        log_action(actor, "uninstall_warp", details="status:success")
        sync_warp_outbound_state(False)
    else:
        log_action(actor, "uninstall_warp", details=f"status:failed, error:{res.get('msg')}")
        
    return res
