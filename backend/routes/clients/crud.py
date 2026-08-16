import json
import logging
from fastapi import APIRouter, Request, Form
from pydantic import BaseModel
from typing import Optional

from backend.database import (
    add_client_db, get_inbound_by_id, update_inbound, get_client_by_id_or_pwd,
    delete_client_db, get_clients_for_inbound, update_client_db
)
from backend.xray import restart_xray
from backend.hysteria import restart_hysteria
from backend.links_generator import get_client_links, get_client_mihomo_yaml
from backend.i18n import t, get_lang
import backend.routes.clients

router = APIRouter()

class ClientSettings(BaseModel):
    id: int # inbound_id
    settings: str # JSON-строка {"clients": [...]}

@router.post("/panel/api/inbounds/addClient")
async def add_client_api(request: Request, payload: Optional[ClientSettings] = None, id: Optional[int] = Form(None), settings: Optional[str] = Form(None)):
    if not backend.routes.clients.check_auth(request):
        return backend.routes.clients.decoy_response()
        
    lang = get_lang(request)
    ib_id = id or (payload.id if payload else None)
    settings_str = settings or (payload.settings if payload else None)
    
    if not ib_id or not settings_str:
        return {"success": False, "msg": t("invalid_request_params", lang=lang, category="backend")}
        
    try:
        data = json.loads(settings_str)
        clients = data.get("clients", [])
        if not clients:
            return {"success": False, "msg": t("client_list_empty", lang=lang, category="backend")}
            
        client = clients[0] # Контроллер шлет по одному клиенту
        email = client.get("email")
        if email:
            email = email.strip()
        c_id = client.get("id") or client.get("password") # UUID для vmess/vless, пароль для trojan/ss
        if c_id:
            c_id = c_id.strip()
        total_gb = client.get("totalGB", 0)
        expiry_time = client.get("expiryTime", 0)
        limit_ip = client.get("limitIp", 0)
        allowed_ips = client.get("allowedIps") or client.get("allowed_ips") or ""
        enable = 1 if client.get("enable", True) else 0
        flow = client.get("flow", "")
        alter_id = client.get("alterId", 0)
        security = client.get("security", "auto")
        
        # Добавляем в базу данных
        success = add_client_db(ib_id, email, c_id, total_gb, expiry_time, limit_ip, enable, allowed_ips=allowed_ips)
        if success:
            from backend.audit import log_action, get_actor_username
            actor = get_actor_username(request)
            log_action(actor, "create_client", target=email, details=f"inbound_id:{ib_id}, total_gb:{total_gb}, limit_ip:{limit_ip}, allowed_ips:{allowed_ips}")
            # Обновляем JSON-настройки самого inbound
            inbound = get_inbound_by_id(ib_id)
            ib_settings = json.loads(inbound["settings"] or "{}")
            ib_clients = ib_settings.get("clients", [])
            
            # Удаляем старого клиента с таким же email если есть
            ib_clients = [c for c in ib_clients if c.get("email") != email]
            new_c = {
                "id": c_id,
                "email": email,
                "enable": bool(enable),
                "limitIp": limit_ip,
                "allowedIps": allowed_ips,
                "totalGB": total_gb,
                "expiryTime": expiry_time,
                "alterId": alter_id,
                "security": security
            }
            if inbound and inbound.get("protocol") == "vless" and flow:
                new_c["flow"] = flow
            ib_clients.append(new_c)
            ib_settings["clients"] = ib_clients
            
            update_inbound(
                ib_id, inbound["remark"], inbound["port"], inbound["protocol"],
                ib_settings, json.loads(inbound["stream_settings"]), json.loads(inbound["sniffing"]),
                inbound["enable"], inbound["total"], inbound["expiry_time"], core=inbound.get("core")
            )
            
            # Перезапуск сервисов в фоне с debounce
            from backend.utils.service_restart import restart_services_background
            restart_services_background(delay=0.5)
            return {"success": True, "msg": t("client_added", lang=lang, category="backend")}
            
        return {"success": False, "msg": t("client_email_exists", lang=lang, category="backend")}
    except Exception as e:
        return {"success": False, "msg": t("generic_error", lang=lang, category="backend", error=str(e))}

@router.post("/panel/api/inbounds/updateClient/{client_id}")
async def update_client_api(request: Request, client_id: str, payload: Optional[ClientSettings] = None, id: Optional[int] = Form(None), settings: Optional[str] = Form(None)):
    client_id = client_id.strip()
    if not backend.routes.clients.check_auth(request):
        return backend.routes.clients.decoy_response()
        
    lang = get_lang(request)
    ib_id = id or (payload.id if payload else None)
    settings_str = settings or (payload.settings if payload else None)
    
    if not ib_id or not settings_str:
        return {"success": False, "msg": t("invalid_request_params", lang=lang, category="backend")}
        
    try:
        data = json.loads(settings_str)
        clients = data.get("clients", [])
        if not clients:
            return {"success": False, "msg": t("client_list_empty", lang=lang, category="backend")}
            
        client = clients[0]
        email = client.get("email")
        if email:
            email = email.strip()
            
        # Находим существующего клиента для сверки его реального текущего email
        from backend.database.crud.clients import get_client_by_id_or_pwd
        existing_client = get_client_by_id_or_pwd(ib_id, client_id)
        if not existing_client:
            return {"success": False, "msg": t("client_not_found", lang=lang, category="backend")}
            
        real_old_email = existing_client["email"]
        
        # Проверяем уникальность нового email, только если он изменился
        if email != real_old_email:
            from backend.database.crud.clients import get_client_by_email
            existing_with_new_email = get_client_by_email(ib_id, email)
            if existing_with_new_email:
                return {"success": False, "msg": t("client_email_exists", lang=lang, category="backend")}
                
        c_id = client.get("id") or client.get("password")
        if c_id:
            c_id = c_id.strip()
            
        total_gb = client.get("totalGB", 0)
        expiry_time = client.get("expiryTime", 0)
        limit_ip = client.get("limitIp", 0)
        allowed_ips = client.get("allowedIps") if "allowedIps" in client else client.get("allowed_ips")
        enable = 1 if client.get("enable", True) else 0
        flow = client.get("flow", "")
        alter_id = client.get("alterId", 0)
        security = client.get("security", "auto")
        
        # Обновляем в client_stats
        success = update_client_db(ib_id, client_id, email, total_gb, expiry_time, limit_ip, enable, client_uuid_or_pwd=c_id, allowed_ips=allowed_ips)
        if success:
            from backend.audit import log_action, get_actor_username
            actor = get_actor_username(request)
            log_action(actor, "update_client", target=email, details=f"inbound_id:{ib_id}, old_email:{client_id}, new_email:{email}, total_gb:{total_gb}, limit_ip:{limit_ip}, allowed_ips:{allowed_ips}, enable:{enable}")
            # Сброс IP кэша в планировщике, если клиент активирован (снята блокировка)
            if enable == 1:
                try:
                    from backend.scheduler import ACTIVE_IP_CACHE
                    if email in ACTIVE_IP_CACHE:
                        ACTIVE_IP_CACHE[email] = {}
                    if client_id in ACTIVE_IP_CACHE:
                        ACTIVE_IP_CACHE[client_id] = {}
                except Exception as e:
                    logging.error(f"Failed to reset active IP cache: {e}")
            else:
                # Если заблокирован вручную, мгновенно рвем соединение
                inbound = get_inbound_by_id(ib_id)
                if inbound:
                    if inbound["protocol"] == "hysteria2":
                        try:
                            from backend.hysteria import kick_client_hysteria_api
                            kick_client_hysteria_api(ib_id, client_id)
                            if email != client_id:
                                kick_client_hysteria_api(ib_id, email)
                        except Exception as e:
                            logging.error(f"Failed to kick Hysteria2 client: {e}")
                    else:
                        try:
                            from backend.xray import remove_client_api
                            remove_client_api(ib_id, client_id)
                            if email != client_id:
                                remove_client_api(ib_id, email)
                        except Exception as e:
                            logging.error(f"Failed to remove Xray client via API: {e}")

            # Обновляем в настройках inbound
            inbound = get_inbound_by_id(ib_id)
            ib_settings = json.loads(inbound["settings"] or "{}")
            ib_clients = ib_settings.get("clients", [])
            
            for c in ib_clients:
                if c.get("email") == client_id or c.get("id") == client_id:
                    c["email"] = email
                    if "id" in c:
                        c["id"] = c_id
                    if "password" in c:
                        c["password"] = c_id
                    c["enable"] = bool(enable)
                    c["limitIp"] = limit_ip
                    c["totalGB"] = total_gb
                    c["expiryTime"] = expiry_time
                    c["alterId"] = alter_id
                    c["security"] = security
                    if inbound and inbound.get("protocol") == "vless":
                        c["flow"] = flow
                    else:
                        c.pop("flow", None)
                    break
            ib_settings["clients"] = ib_clients
            
            update_inbound(
                ib_id, inbound["remark"], inbound["port"], inbound["protocol"],
                ib_settings, json.loads(inbound["stream_settings"]), json.loads(inbound["sniffing"]),
                inbound["enable"], inbound["total"], inbound["expiry_time"], core=inbound.get("core")
            )
            
            if not bool(enable):
                try:
                    from backend.sentinel_core_bridge import kick_client
                    kick_client(email)
                except Exception:
                    pass

            from backend.utils.service_restart import restart_services_background
            restart_services_background(delay=0.5)
            return {"success": True, "msg": t("client_updated", lang=lang, category="backend")}
        return {"success": False, "msg": t("client_not_found", lang=lang, category="backend")}
    except Exception as e:
        return {"success": False, "msg": t("generic_error", lang=lang, category="backend", error=str(e))}

@router.post("/panel/api/inbounds/{inbound_id}/delClient/{client_id}")
async def delete_client_api(request: Request, inbound_id: int, client_id: str):
    client_id = client_id.strip()
    if not backend.routes.clients.check_auth(request):
        return backend.routes.clients.decoy_response()
        
    lang = get_lang(request)
    client = get_client_by_id_or_pwd(inbound_id, client_id)
    email = client["email"].strip() if client else client_id
    
    from backend.database import delete_client_db as delete_client
    success = delete_client(inbound_id, email)
    if not success and client_id != email:
        success = delete_client(inbound_id, client_id)
        
    if success:
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "delete_client", target=email, details=f"inbound_id:{inbound_id}")
        
        inbound = get_inbound_by_id(inbound_id)
        if inbound:
            ib_settings = json.loads(inbound["settings"] or "{}")
            ib_clients = ib_settings.get("clients", [])
            ib_clients = [c for c in ib_clients if c.get("email") not in (email, client_id) and c.get("id") not in (email, client_id) and c.get("password") not in (email, client_id)]
            ib_settings["clients"] = ib_clients
            
            update_inbound(
                inbound_id, inbound["remark"], inbound["port"], inbound["protocol"],
                ib_settings, json.loads(inbound["stream_settings"]), json.loads(inbound["sniffing"]),
                inbound["enable"], inbound["total"], inbound["expiry_time"], core=inbound.get("core")
            )
        
        try:
            from backend.sentinel_core_bridge import kick_client
            kick_client(email)
            if client_id != email:
                kick_client(client_id)
        except Exception:
            pass

        from backend.utils.service_restart import restart_services_background
        restart_services_background(delay=0.5)
        return {"success": True, "msg": t("client_deleted", lang=lang, category="backend")}
        
    return {"success": False, "msg": t("client_delete_error", lang=lang, category="backend")}

@router.get("/panel/api/inbounds/getClientLinks/{inbound_id}/{email}")
async def get_client_links_api(request: Request, inbound_id: int, email: str):
    email = email.strip()
    if not backend.routes.clients.check_auth(request):
        return backend.routes.clients.decoy_response()
        
    lang = get_lang(request)
    inbound = get_inbound_by_id(inbound_id)
    if not inbound:
        return {"success": False, "msg": t("inbound_not_found", lang=lang, category="backend")}
        
    # Ищем клиента в client_stats
    client = None
    clients = get_clients_for_inbound(inbound_id)
    for c in clients:
        if c["email"] == email:
            client = c
            break
            
    if not client:
        return {"success": False, "msg": t("client_not_found", lang=lang, category="backend")}
        
    # Генерируем ссылки
    host_header = request.headers.get("Host", "127.0.0.1")
    proto = request.url.scheme
    base_url = f"{proto}://{host_header}"
    
    links = get_client_links(inbound, client, base_url)
    mihomo_yaml = get_client_mihomo_yaml(inbound, client, base_url)
    return {"success": True, "obj": links, "mihomo": mihomo_yaml}

