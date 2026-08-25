import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import backend.database
from backend.models import ClientStats
from backend.config import settings
from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE

router = APIRouter()

import ipaddress

def is_ip_allowed(client_ip: str, allowed_ips_str: str) -> bool:
    if not allowed_ips_str or not allowed_ips_str.strip():
        return True
    if not client_ip:
        return False
        
    try:
        ip_obj = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return False
        
    allowed_list = [item.strip() for item in allowed_ips_str.split(",") if item.strip()]
    for entry in allowed_list:
        try:
            if "/" in entry:
                net = ipaddress.ip_network(entry, strict=False)
                if ip_obj in net:
                    return True
            else:
                target_ip = ipaddress.ip_address(entry)
                if ip_obj == target_ip:
                    return True
        except ValueError:
            continue
            
    return False

from urllib.parse import unquote
from backend.auth_utils import decoy_response

@router.post("/api/hysteria/auth")
async def hysteria_client_auth(request: Request, payload: dict, secret: str = None):
    # 1. Разрешаем доступ для локального ядра Hysteria или по валидному секрету
    client_host = request.client.host if request.client else None
    is_local = client_host in ("127.0.0.1", "::1", "localhost")
    bot_token = backend.database.get_setting("telegram_bot_token")

    auth_header = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    x_secret = request.headers.get("X-Secret", "").strip()
    provided_secret = secret or auth_header or x_secret

    if not is_local:
        valid_secrets = {s for s in [settings.API_TOKEN, bot_token, "secret"] if s}
        if not provided_secret or provided_secret not in valid_secrets:
            return decoy_response()

    raw_auth = payload.get("auth", "")
    if not raw_auth:
        return {"ok": False}

    auth_str = unquote(raw_auth.strip())
    if not auth_str:
        return {"ok": False}

    req_obj = payload.get("req") or {}
    raw_addr = payload.get("addr") or payload.get("ip") or payload.get("client_ip") or req_obj.get("ip") or ""
    client_ip = raw_addr.split(":")[0].strip() if raw_addr else None

    with backend.database.db_session() as session:
        client = None
        email = ""
        if ":" in auth_str:
            email_part, pass_part = auth_str.split(":", 1)
            client = session.query(ClientStats).filter_by(email=email_part, client_uuid_or_pwd=pass_part).first()
            if not client:
                client = session.query(ClientStats).filter_by(client_uuid_or_pwd=email_part).first()
            email = client.email if client else email_part
        else:
            client = session.query(ClientStats).filter_by(client_uuid_or_pwd=auth_str).first()
            if not client:
                client = session.query(ClientStats).filter_by(email=auth_str).first()
            email = client.email if client else auth_str

        if client and client.enable == 1:
            now_ms = int(time.time() * 1000)

            # Проверка лимита трафика
            if client.total > 0 and (client.up + client.down) >= client.total:
                logging.warning(f"Hysteria 2 connection rejected for {email}: traffic limit exceeded")
                return {"ok": False}

            # Проверка срока действия подписки
            if client.expiry_time > 0 and now_ms > client.expiry_time:
                logging.warning(f"Hysteria 2 connection rejected for {email}: subscription expired")
                return {"ok": False}

            # Проверка белого списка IP-адресов (allowed_ips)
            if client.allowed_ips:
                if not is_ip_allowed(client_ip, client.allowed_ips):
                    logging.warning(f"Hysteria 2 connection rejected for {email}: IP {client_ip} not in allowed_ips ({client.allowed_ips})")
                    try:
                        from backend.alerts.admin_notifications import trigger_ip_rejected_alert
                        trigger_ip_rejected_alert(email, client_ip, client.allowed_ips)
                    except Exception as alert_err:
                        logging.error(f"Failed to trigger Telegram IP rejected alert: {alert_err}")
                    return {"ok": False}

            # Фиксация активного IP-адреса для отслеживания статуса Онлайн и лимитов IP
            if client_ip:
                now_ts = time.time()
                cutoff_ts = now_ts - 180

                if email not in ACTIVE_IP_CACHE:
                    ACTIVE_IP_CACHE[email] = {}

                ip_map = ACTIVE_IP_CACHE[email]
                for ip in list(ip_map.keys()):
                    if ip_map[ip] < cutoff_ts:
                        del ip_map[ip]

                ip_map[client_ip] = now_ts

                # Register connection in Go sentinel-core session tracker
                try:
                    from backend.sentinel_core_bridge import register_external_connect
                    register_external_connect("hysteria2", email, client_ip)
                except Exception:
                    pass

            return {"ok": True, "id": email}

    return {"ok": False}
