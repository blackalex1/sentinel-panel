import os
import logging
import ipaddress
from fastapi import APIRouter, Request

from backend.auth_utils import check_auth, decoy_response

router = APIRouter()

def _is_valid_ip_or_cidr(val: str) -> bool:
    """Returns True if val is a valid IPv4/IPv6 address or CIDR network."""
    try:
        ipaddress.ip_address(val)
        return True
    except ValueError:
        pass
    try:
        ipaddress.ip_network(val, strict=False)
        return True
    except ValueError:
        pass
    return False

@router.post("/api/security/block-ip")
async def block_ip_api(request: Request, payload: dict = None):
    """Blocks an IP via OS firewall / ban center and kicks active sessions across Xray, Hysteria 2, and Sing-box."""
    if not check_auth(request):
        return decoy_response()

    if payload is None:
        try:
            payload = await request.json()
        except Exception:
            payload = {}

    ip = str(payload.get("ip") or "").strip()
    email = str(payload.get("email") or "").strip()

    if not ip:
        return {"success": False, "msg": "IP адрес обязателен"}

    if not _is_valid_ip_or_cidr(ip):
        logging.warning(f"[Block IP API] Rejected invalid IP format: {ip!r}")
        return {"success": False, "msg": "Некорректный формат IP-адреса"}

    # 1. Add IP to OS firewall / ban table
    try:
        if os.name != "nt":
            import subprocess
            subprocess.run(["iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as ex:
        logging.error(f"[Block IP API] Error blocking IP via iptables: {ex}")

    # 2. Add IP to Whitelist/Blacklist DB state if applicable
    try:
        from backend.database import add_blocked_ip
        add_blocked_ip(ip, reason=f"Blocked via Telegram Bot for user {email}")
    except Exception:
        pass

    # 3. Kick active connections for Xray, Hysteria 2, and Sing-box
    kicked_count = 0
    try:
        # Xray kick
        if email:
            import backend.scheduler
            backend.scheduler.remove_client_api(0, email)
            kicked_count += 1
    except Exception:
        pass

    try:
        # Hysteria 2 kick
        if email:
            import backend.scheduler
            backend.scheduler.kick_client_hysteria_api(0, email)
            kicked_count += 1
    except Exception:
        pass

    try:
        # Sing-box Clash API connection drop over loopback
        import requests
        url = "http://127.0.0.1:9090/connections"
        resp = requests.get(url, timeout=1)
        if resp.status_code == 200:
            data = resp.json()
            for conn in data.get("connections", []):
                conn_id = conn.get("id")
                metadata = conn.get("metadata", {})
                conn_user = metadata.get("user") or metadata.get("username") or ""
                conn_ip = metadata.get("sourceIP") or metadata.get("srcIP") or ""
                if conn_id and (conn_ip == ip or (email and conn_user == email)):
                    requests.delete(f"http://127.0.0.1:9090/connections/{conn_id}", timeout=1)
                    kicked_count += 1
    except Exception:
        pass

    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request) or "TelegramBot"
    log_action(actor, "block_ip", target=ip, details=f"user:{email}, kicked:{kicked_count}")

    return {"success": True, "msg": f"IP {ip} заблокирован. Активные соединения сброшены.", "ip": ip, "email": email}

@router.post("/api/security/allow-ip")
async def allow_ip_api(request: Request):
    """Allows an IP address and marks it as trusted."""
    if not check_auth(request):
        return decoy_response()

    payload = {}
    try:
        payload = await request.json()
    except Exception:
        try:
            form = await request.form()
            payload = dict(form)
        except Exception:
            payload = {}

    ip = str(payload.get("ip") or "").strip()
    email = str(payload.get("email") or "").strip()

    import ipaddress
    def is_valid_ip(val: str) -> bool:
        if not val or val == "ip":
            return False
        try:
            ipaddress.ip_address(val)
            return True
        except ValueError:
            pass
        try:
            ipaddress.ip_network(val, strict=False)
            return True
        except ValueError:
            pass
        return False

    if not ip or not is_valid_ip(ip):
        return {"success": False, "msg": "Невалидный IP адрес"}

    try:
        if os.name != "nt":
            import subprocess
            subprocess.run(["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    if email:
        try:
            from backend.database import db_session
            from backend.models import ClientStats
            from sqlalchemy import func
            clean_email = email.strip()
            with db_session() as session:
                clients = session.query(ClientStats).filter(func.lower(ClientStats.email) == func.lower(clean_email)).all()
                for c in clients:
                    cur = [x.strip() for x in (c.allowed_ips or "").split(",") if x.strip()]
                    if ip and ip not in cur:
                        cur.append(ip)
                    c.allowed_ips = ", ".join(cur)
                    session.add(c)
                session.commit()
        except Exception as e:
            import logging
            logging.error(f"Error updating client allowed_ips in allow_ip_api: {e}")

    from backend.audit import log_action, get_actor_username
    actor = get_actor_username(request) or "TelegramBot"
    log_action(actor, "allow_ip", target=ip, details=f"user:{email}")

    return {"success": True, "msg": f"IP {ip} разрешен для пользователя {email}."}
