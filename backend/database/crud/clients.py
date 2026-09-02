from backend.models import ClientStats
import backend.database

def client_to_dict(c: ClientStats) -> dict:
    if not c:
        return None
    return {
        "id": c.id,
        "inbound_id": c.inbound_id,
        "email": c.email,
        "client_uuid_or_pwd": c.client_uuid_or_pwd,
        "up": c.up,
        "down": c.down,
        "total": c.total,
        "expiry_time": c.expiry_time,
        "enable": c.enable,
        "limit_ip": c.limit_ip,
        "allowed_ips": c.allowed_ips or "",
        "block_reason": c.block_reason or ""
    }

def get_clients_for_inbound(inbound_id: int):
    with backend.database.db_session() as session:
        clients = session.query(ClientStats).filter_by(inbound_id=inbound_id).order_by(ClientStats.id.asc()).all()
        return [backend.database.client_to_dict(c) for c in clients]

def get_client_by_email(inbound_id: int, email: str):
    with backend.database.db_session() as session:
        c = session.query(ClientStats).filter_by(inbound_id=inbound_id, email=email).first()
        return backend.database.client_to_dict(c)

def get_client_by_id_or_pwd(inbound_id: int, client_id: str):
    with backend.database.db_session() as session:
        c = session.query(ClientStats).filter(
            (ClientStats.inbound_id == inbound_id) & 
            ((ClientStats.client_uuid_or_pwd == client_id) | (ClientStats.email == client_id))
        ).first()
        return backend.database.client_to_dict(c)

def add_client_db(inbound_id: int, email: str, client_uuid_or_pwd: str, total_gb: int = 0, expiry_time: int = 0, limit_ip: int = 0, enable: int = 1, block_reason: str = "", allowed_ips: str = ""):
    with backend.database.db_session() as session:
        # Проверка уникальности email для данного inbound
        existing = session.query(ClientStats).filter_by(inbound_id=inbound_id, email=email).first()
        if existing:
            return False
            
        total_bytes = total_gb * 1024 * 1024 * 1024
        c = ClientStats(
            inbound_id=inbound_id,
            email=email,
            client_uuid_or_pwd=client_uuid_or_pwd,
            total=total_bytes,
            expiry_time=expiry_time,
            limit_ip=limit_ip,
            allowed_ips=allowed_ips or "",
            enable=enable,
            block_reason=block_reason if enable == 0 else ""
        )
        session.add(c)
        return True

def update_client_db(inbound_id: int, old_email: str = None, new_email: str = None, total_gb: int = 0, expiry_time: int = 0, limit_ip: int = 0, enable: int = 1, block_reason: str = None, email: str = None, client_uuid_or_pwd: str = None, allowed_ips: str = None):
    if old_email is None:
        old_email = email or ""
    if new_email is None:
        new_email = email or ""
        
    old_email = old_email.strip()
    new_email = new_email.strip()
    
    with backend.database.db_session() as session:
        # Look up by either email or UUID/password to be fully robust
        c = session.query(ClientStats).filter(
            (ClientStats.inbound_id == inbound_id) & 
            ((ClientStats.client_uuid_or_pwd == old_email) | (ClientStats.email == old_email))
        ).first()
        if not c:
            return False
            
        old_email_real = c.email
        c.email = new_email
        if client_uuid_or_pwd is not None:
            c.client_uuid_or_pwd = client_uuid_or_pwd.strip()
        c.total = total_gb * 1024 * 1024 * 1024
        c.expiry_time = expiry_time
        c.limit_ip = limit_ip
        if allowed_ips is not None:
            c.allowed_ips = allowed_ips.strip()
        
        if enable == 1:
            c.enable = 1
            c.block_reason = ""
        else:
            c.enable = 0
            if block_reason is not None:
                c.block_reason = block_reason
            elif not c.block_reason:
                c.block_reason = "Заблокирован администратором"
                
        try:
            from backend.models import ClientTrafficDaily
            session.query(ClientTrafficDaily).filter_by(email=old_email_real).update({"email": new_email})
        except Exception:
            pass
            
        return True

def block_client_db(inbound_id: int, email: str, reason: str):
    """Блокирует клиента в БД с указанием причины"""
    with backend.database.db_session() as session:
        c = session.query(ClientStats).filter_by(inbound_id=inbound_id, email=email).first()
        if c:
            c.enable = 0
            c.block_reason = reason
            return True
        return False

def unblock_client_db(inbound_id: int, email: str):
    """Разблокирует клиента в БД и очищает причину блокировки"""
    with backend.database.db_session() as session:
        c = session.query(ClientStats).filter_by(inbound_id=inbound_id, email=email).first()
        if c:
            c.enable = 1
            c.block_reason = ""
            return True
        return False

def delete_client_db(inbound_id: int, email: str):
    with backend.database.db_session() as session:
        c = session.query(ClientStats).filter_by(inbound_id=inbound_id, email=email).first()
        if not c:
            return False
        session.delete(c)
        return True

def update_client_traffic(inbound_id: int, email: str, up_add: int, down_add: int) -> bool:
    if up_add <= 0 and down_add <= 0:
        return True
    with backend.database.db_session() as session:
        # 1. Exact match by email for this specific inbound
        c = session.query(ClientStats).filter_by(inbound_id=inbound_id, email=email).first()
        # 2. Exact match by client_uuid_or_pwd or case-insensitive email
        if not c:
            c = session.query(ClientStats).filter(
                (ClientStats.inbound_id == inbound_id) &
                ((ClientStats.email.ilike(email)) | (ClientStats.client_uuid_or_pwd == email))
            ).first()
        # 3. Domain or token delimiter prefix matching (e.g. 'alice@domain.com' -> 'alice')
        if not c and ("@" in email or ":" in email):
            clean_user = email.split(":")[0].split("@")[0].strip()
            if clean_user:
                c = session.query(ClientStats).filter(
                    (ClientStats.inbound_id == inbound_id) &
                    (
                        (ClientStats.email == clean_user) |
                        (ClientStats.client_uuid_or_pwd == clean_user) |
                        (ClientStats.email.ilike(f"{clean_user}@%"))
                    )
                ).first()
        if c:
            c.up += max(0, up_add)
            c.down += max(0, down_add)
            return True
        return False

def update_client_traffic_by_email(email: str, up_add: int, down_add: int, core: str = None) -> bool:
    if up_add <= 0 and down_add <= 0:
        return True
    with backend.database.db_session() as session:
        # If core is specified, prefer client matching the core's inbound
        query = session.query(ClientStats)
        if core:
            from backend.models import Inbound
            query = query.join(Inbound, ClientStats.inbound_id == Inbound.id)
            norm_core = "singbox" if "sing" in core.lower() else ("hysteria" if "hysteria" in core.lower() else "xray")
            c = query.filter(
                (ClientStats.email == email) | (ClientStats.client_uuid_or_pwd == email),
                (Inbound.core == norm_core) | (Inbound.protocol.ilike(f"%{norm_core}%"))
            ).first()
            if c:
                c.up += max(0, up_add)
                c.down += max(0, down_add)
                return True

        # 1. Exact match by email
        c = session.query(ClientStats).filter_by(email=email).first()
        # 2. Exact match by client_uuid_or_pwd or case-insensitive email
        if not c:
            c = session.query(ClientStats).filter(
                (ClientStats.email.ilike(email)) | (ClientStats.client_uuid_or_pwd == email)
            ).first()
        # 3. Domain or token delimiter prefix matching (e.g. 'alice@domain.com' -> 'alice')
        if not c and ("@" in email or ":" in email):
            clean_user = email.split(":")[0].split("@")[0].strip()
            if clean_user:
                c = session.query(ClientStats).filter(
                    (ClientStats.email == clean_user) |
                    (ClientStats.client_uuid_or_pwd == clean_user) |
                    (ClientStats.email.ilike(f"{clean_user}@%"))
                ).first()
        if c:
            c.up += max(0, up_add)
            c.down += max(0, down_add)
            return True
        return False


