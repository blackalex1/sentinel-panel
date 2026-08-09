from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    totp_secret = Column(String, nullable=True)
    totp_enabled = Column(Integer, default=0)



class Inbound(Base):
    __tablename__ = "inbounds"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    remark = Column(String, nullable=False)
    port = Column(Integer, unique=True, nullable=False)
    protocol = Column(String, nullable=False)
    core = Column(String, default="xray")
    settings = Column(String, nullable=True)          # JSON string
    stream_settings = Column(String, nullable=True)   # JSON string
    sniffing = Column(String, nullable=True)          # JSON string
    enable = Column(Integer, default=1)
    up = Column(BigInteger, default=0)
    down = Column(BigInteger, default=0)
    total = Column(BigInteger, default=0)
    expiry_time = Column(BigInteger, default=0)
    
    # Relationship to clients
    clients = relationship("ClientStats", back_populates="inbound", cascade="all, delete-orphan")


class ClientStats(Base):
    __tablename__ = "client_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    inbound_id = Column(Integer, ForeignKey("inbounds.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False, index=True)
    client_uuid_or_pwd = Column(String, nullable=False)
    up = Column(BigInteger, default=0)
    down = Column(BigInteger, default=0)
    total = Column(BigInteger, default=0)
    expiry_time = Column(BigInteger, default=0)
    enable = Column(Integer, default=1)
    limit_ip = Column(Integer, default=0)
    allowed_ips = Column(String, nullable=True, default="")
    block_reason = Column(String, nullable=True, default="")
    last_seen_up = Column(BigInteger, default=0)
    last_seen_down = Column(BigInteger, default=0)
    
    __table_args__ = (
        UniqueConstraint("inbound_id", "email", name="uq_inbound_client_email"),
    )
    
    # Relationship to inbound
    inbound = relationship("Inbound", back_populates="clients")


class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class ClientTrafficDaily(Base):
    __tablename__ = "client_traffic_daily"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    date = Column(String, nullable=False)  # YYYY-MM-DD
    up = Column(BigInteger, default=0)
    down = Column(BigInteger, default=0)
    
    __table_args__ = (
        UniqueConstraint("email", "date", name="uq_client_email_date"),
        # Отдельный индекс по date: планировщик каждые 30с делает filter_by(date=today)
        # Составной уникальный индекс (email, date) не ускоряет запросы только по date.
        Index("ix_client_traffic_daily_date", "date"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False, index=True)  # UTC epoch seconds
    username = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target = Column(String, nullable=True)
    details = Column(String, nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"
    
    session_id = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    created_at = Column(BigInteger, nullable=False)  # UTC epoch seconds
    expires_at = Column(BigInteger, nullable=False, index=True)  # UTC epoch seconds
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)


class Outbound(Base):
    __tablename__ = "outbounds"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    remark = Column(String, nullable=False)
    protocol = Column(String, nullable=False)
    tag = Column(String, unique=True, nullable=False)
    settings = Column(String, nullable=True)          # JSON string containing server, port, password, etc.
    stream_settings = Column(String, nullable=True)   # JSON string containing TLS/Reality settings
    enable = Column(Integer, default=1)
    is_system = Column(Integer, default=0)            # 1 for direct/blocked, cannot be deleted
    up = Column(BigInteger, default=0)
    down = Column(BigInteger, default=0)



class RoutingRule(Base):
    __tablename__ = "routing_rules"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    remark = Column(String, nullable=True)
    outbound_tag = Column(String, nullable=False)
    inbound_tags = Column(String, nullable=True)      # JSON list (e.g. ["api", "inbound-1"])
    users = Column(String, nullable=True)             # JSON list of user emails
    domains = Column(String, nullable=True)           # JSON list
    ips = Column(String, nullable=True)               # JSON list
    protocols = Column(String, nullable=True)         # JSON list
    enable = Column(Integer, default=1)
    sort_order = Column(Integer, default=0)


class Node(Base):
    __tablename__ = "nodes"
    
    id = Column(String, primary_key=True)                      # e.g. "edge-node-c1"
    name = Column(String, nullable=False)
    api_token_hash = Column(String, nullable=False)            # SHA-256 hash
    public_key = Column(String, nullable=True)                 # Hex-encoded Ed25519 Public Key
    status = Column(String, default="active")                  # active, blocked, compromised
    registered_at = Column(BigInteger, nullable=False)         # UTC epoch seconds


class NodeJoinCode(Base):
    __tablename__ = "node_join_codes"
    
    code = Column(String, primary_key=True)                    # Unique activation code
    expires_at = Column(BigInteger, nullable=False)            # UTC epoch seconds
    created_at = Column(BigInteger, nullable=False)            # UTC epoch seconds


class SharedCache(Base):
    __tablename__ = "shared_cache"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    expires_at = Column(BigInteger, nullable=False, index=True)


