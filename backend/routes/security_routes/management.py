import json
import logging
import datetime
from typing import Optional
from fastapi import APIRouter, Request, Form, Query
from sqlalchemy import func

from backend.auth_utils import check_auth, decoy_response
from backend.database import db_session
from backend.models import ClientStats, Inbound, ClientTrafficDaily
from backend.routes.security_routes.log_parsers import (
    find_email_in_hysteria_log,
    find_client_ip_for_email_in_hysteria_log,
    find_email_and_ip_in_xray_log
)

router = APIRouter()

@router.get("/api/security/client-by-connection")
async def client_by_connection(
    request: Request,
    client_ip: Optional[str] = Query(None),
    dst_ip: Optional[str] = Query(None),
    port: int = Query(...)
):
    if not check_auth(request):
        return decoy_response()
        
    email = find_email_in_hysteria_log(dst_ip, port)
    if email:
        real_client_ip = find_client_ip_for_email_in_hysteria_log(email)
        return {"success": True, "email": email, "source": "hysteria", "client_ip": real_client_ip}
        
    res = find_email_and_ip_in_xray_log(client_ip, dst_ip, port)
    if res:
        found_email, found_ip = res
        return {"success": True, "email": found_email, "source": "xray", "client_ip": found_ip}
        
    return {"success": False, "msg": "Client not found in logs"}

@router.get("/api/security/search-client")
async def search_client(request: Request, key: str = Query("")):
    if not check_auth(request):
        return decoy_response()
        
    from backend.links_generator import get_client_links
    
    found_clients = []
    host_header = request.headers.get("Host", "127.0.0.1")
    proto = request.url.scheme
    base_url = f"{proto}://{host_header}"
    
    with db_session() as session:
        if not key or not key.strip():
            clients = session.query(ClientStats).all()
        else:
            k = key.strip()
            # 1. Exact match
            clients = session.query(ClientStats).filter(
                (ClientStats.email == k) | (ClientStats.client_uuid_or_pwd == k)
            ).all()
            # 2. Case-insensitive / partial match if exact didn't find any
            if not clients:
                clients = session.query(ClientStats).filter(
                    (ClientStats.email.ilike(f"%{k}%")) | (ClientStats.client_uuid_or_pwd.ilike(f"%{k}%"))
                ).all()
        
        for c in clients:
            ib = session.query(Inbound).filter_by(id=c.inbound_id).first()
            if ib:
                c_dict = {
                    "id": c.id, "inbound_id": c.inbound_id, "email": c.email,
                    "client_uuid_or_pwd": c.client_uuid_or_pwd, "up": c.up, "down": c.down,
                    "total": c.total, "expiry_time": c.expiry_time, "enable": c.enable,
                    "limit_ip": c.limit_ip, "block_reason": c.block_reason or "",
                    "allowed_ips": c.allowed_ips or ""
                }
                ib_dict = {
                    "id": ib.id, "remark": ib.remark, "port": ib.port, "protocol": ib.protocol,
                    "settings": ib.settings, "stream_settings": ib.stream_settings, "sniffing": ib.sniffing,
                    "enable": ib.enable, "up": ib.up, "down": ib.down, "total": ib.total, "expiry_time": ib.expiry_time
                }
                
                links = []
                try:
                    links = get_client_links(ib_dict, c_dict, base_url)
                except Exception as e:
                    logging.error(f"Error generating client links for search API: {e}")
                    
                found_clients.append({
                    "inbound": ib_dict,
                    "client": c_dict,
                    "links": links
                })
                
    if found_clients or not key or not key.strip():
        return {"success": True, "clients": found_clients}
    return {"success": False, "msg": "Client not found"}

@router.post("/api/security/disable-client")
async def disable_client(request: Request, email: str = Form(...)):
    if not check_auth(request):
        return decoy_response()
        
    from backend.xray import restart_xray, remove_client_api
    from backend.hysteria import restart_hysteria, kick_client_hysteria_api
    from backend.singbox.service import restart_singbox, kick_singbox_user
    
    client_exists = False
    disabled_count = 0
    with db_session() as session:
        clients = session.query(ClientStats).filter(
            (ClientStats.email == email) | (ClientStats.client_uuid_or_pwd == email)
        ).all()
        if clients:
            client_exists = True
        for c in clients:
            if c.enable == 1:
                c.enable = 0
                c.block_reason = "IPS Auto-blocked"
                ib_id = c.inbound_id
                
                inbound = session.query(Inbound).filter_by(id=ib_id).first()
                if inbound:
                    try:
                        ib_settings = json.loads(inbound.settings or "{}")
                        ib_clients = ib_settings.get("clients", [])
                        for sc in ib_clients:
                            if sc.get("email") == email or sc.get("id") == email or sc.get("password") == email or sc.get("name") == email:
                                sc["enable"] = False
                                break
                        inbound.settings = json.dumps(ib_settings)
                    except Exception as e:
                        logging.error(f"Error updating inbound settings JSON: {e}")
                        
                    if inbound.protocol == "hysteria2":
                        try:
                            kick_client_hysteria_api(ib_id, email)
                        except Exception as e:
                            logging.error(f"Failed to kick Hysteria2 client: {e}")
                    else:
                        try:
                            remove_client_api(ib_id, email)
                        except Exception as e:
                            logging.error(f"Failed to remove Xray client: {e}")
                            
                    try:
                        kick_singbox_user(email)
                    except Exception as e:
                        logging.error(f"Failed to kick Sing-box user: {e}")
                            
                disabled_count += 1
        session.commit()
        
    if disabled_count > 0:
        from backend.utils.service_restart import restart_services_background
        restart_services_background(delay=0.5)

        
        try:
            from backend.audit import log_action, get_actor_username
            actor = get_actor_username(request) or "IPS-Sentinel"
            log_action(actor, "block_client_ips", target=email, details="IPS Auto-blocked due to intrusion threat")
        except Exception:
            pass
            
        return {"success": True, "msg": f"Client {email} blocked and active sessions terminated."}
    if client_exists:
        return {"success": True, "msg": f"Client {email} is already blocked."}
    return {"success": False, "msg": f"Client {email} not found."}

@router.post("/api/security/enable-client")
async def enable_client(request: Request, email: str = Form(...)):
    if not check_auth(request):
        return decoy_response()
        
    from backend.xray import restart_xray
    from backend.hysteria import restart_hysteria
    from backend.singbox.service import restart_singbox
    
    client_exists = False
    enabled_count = 0
    with db_session() as session:
        clients = session.query(ClientStats).filter(
            (ClientStats.email == email) | (ClientStats.client_uuid_or_pwd == email)
        ).all()
        if clients:
            client_exists = True
        for c in clients:
            if c.enable == 0:
                c.enable = 1
                c.block_reason = None
                ib_id = c.inbound_id
                
                inbound = session.query(Inbound).filter_by(id=ib_id).first()
                if inbound:
                    try:
                        ib_settings = json.loads(inbound.settings or "{}")
                        ib_clients = ib_settings.get("clients", [])
                        for sc in ib_clients:
                            if sc.get("email") == email or sc.get("id") == email or sc.get("password") == email or sc.get("name") == email:
                                sc["enable"] = True
                                break
                        inbound.settings = json.dumps(ib_settings)
                    except Exception as e:
                        logging.error(f"Error updating inbound settings JSON: {e}")
                        
                enabled_count += 1
        session.commit()
        
    if enabled_count > 0:
        from backend.utils.service_restart import restart_services_background
        restart_services_background(delay=0.5)

        
        try:
            from backend.audit import log_action, get_actor_username
            actor = get_actor_username(request) or "IPS-Sentinel"
            log_action(actor, "unblock_client_ips", target=email, details="Client unblocked via IPS Sentinel")
        except Exception:
            pass
            
        return {"success": True, "msg": f"Client {email} successfully enabled and unblocked."}
    if client_exists:
        return {"success": True, "msg": f"Client {email} is already active."}
    return {"success": False, "msg": f"Client {email} not found."}

@router.get("/api/security/top-traffic")
async def get_top_traffic(request: Request, period: str = Query("today")):
    if not check_auth(request):
        return decoy_response()
        
    today_str = datetime.date.today().isoformat()
    month_prefix = datetime.date.today().strftime("%Y-%m-") + "%"
    
    with db_session() as session:
        if period == "today":
            records = session.query(
                ClientTrafficDaily.email,
                ClientTrafficDaily.up,
                ClientTrafficDaily.down
            ).filter(ClientTrafficDaily.date == today_str).all()
        else:
            records = session.query(
                ClientTrafficDaily.email,
                func.sum(ClientTrafficDaily.up).label("up"),
                func.sum(ClientTrafficDaily.down).label("down")
            ).filter(ClientTrafficDaily.date.like(month_prefix)).group_by(ClientTrafficDaily.email).all()
            
        result = []
        for r in records:
            up_bytes = int(r.up or 0)
            down_bytes = int(r.down or 0)
            total_bytes = up_bytes + down_bytes
            result.append({
                "email": r.email,
                "up": up_bytes,
                "down": down_bytes,
                "total": total_bytes
            })
            
        result.sort(key=lambda x: x["total"], reverse=True)
        return {"success": True, "period": period, "users": result}
