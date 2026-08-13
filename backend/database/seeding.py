import os
import json
import time
import logging
import string
import secrets

from sqlalchemy import create_engine, inspect, text

from backend.config import settings, DB_PATH
from backend.models import (
    Base, User, Inbound, ClientStats, SystemSetting, Outbound, RoutingRule, UserSession
)
from backend.database.connection import db_session
from backend.database.crud.auth import hash_password

def init_db():
    """Создает таблицы базы данных и записывает начальные настройки под правами администратора"""
    # 1. Создание структуры таблиц под учетной записью администратора (DDL)
    admin_url = settings.DATABASE_ADMIN_URL or settings.DATABASE_URL
    if not admin_url:
        admin_url = f"sqlite:///{DB_PATH}"
    if admin_url.startswith("postgres://"):
        admin_url = admin_url.replace("postgres://", "postgresql://", 1)
        
    connect_args_admin = {}
    if admin_url.startswith("sqlite"):
        connect_args_admin = {"check_same_thread": False}
        
    if admin_url.startswith("postgresql"):
        admin_engine = None
        last_admin_err = None
        for attempt in range(12):
            try:
                temp_engine = create_engine(admin_url, connect_args={"connect_timeout": 5})
                with temp_engine.connect() as conn:
                    admin_engine = temp_engine
                    break
            except Exception as e:
                last_admin_err = e
                time.sleep(1)
        
        if admin_engine is None:
            logging.warning(f"PostgreSQL admin connection failed after retries ({last_admin_err}). Falling back to SQLite: {DB_PATH}")
            admin_url = f"sqlite:///{DB_PATH}"
            connect_args_admin = {"check_same_thread": False}
            admin_engine = create_engine(admin_url, connect_args=connect_args_admin)
    else:
        admin_engine = create_engine(admin_url, connect_args=connect_args_admin)

    try:
        Base.metadata.create_all(admin_engine)
        logging.info("Database schemas verified/created successfully.")
        
        # Check and apply migrations
        with admin_engine.connect() as conn:
            inspector = inspect(admin_engine)
            if "inbounds" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("inbounds")]
                if "core" not in columns:
                    logging.info("[Migration] Adding core to inbounds table...")
                    conn.execute(text("ALTER TABLE inbounds ADD COLUMN core VARCHAR DEFAULT 'xray'"))
                    conn.commit()
            if "client_stats" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("client_stats")]
                if "last_seen_up" not in columns:
                    logging.info("[Migration] Adding last_seen_up and last_seen_down to client_stats table...")
                    conn.execute(text("ALTER TABLE client_stats ADD COLUMN last_seen_up BIGINT DEFAULT 0"))
                    conn.execute(text("ALTER TABLE client_stats ADD COLUMN last_seen_down BIGINT DEFAULT 0"))
                    conn.commit()
                if "block_reason" not in columns:
                    logging.info("[Migration] Adding block_reason to client_stats table...")
                    conn.execute(text("ALTER TABLE client_stats ADD COLUMN block_reason VARCHAR DEFAULT ''"))
                    conn.commit()
                if "allowed_ips" not in columns:
                    logging.info("[Migration] Adding allowed_ips to client_stats table...")
                    conn.execute(text("ALTER TABLE client_stats ADD COLUMN allowed_ips VARCHAR DEFAULT ''"))
                    conn.commit()
            if "users" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("users")]
                if "totp_secret" not in columns:
                    logging.info("[Migration] Adding totp_secret and totp_enabled to users table...")
                    conn.execute(text("ALTER TABLE users ADD COLUMN totp_secret VARCHAR DEFAULT NULL"))
                    conn.execute(text("ALTER TABLE users ADD COLUMN totp_enabled INTEGER DEFAULT 0"))
                    conn.commit()
            if "outbounds" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("outbounds")]
                if "up" not in columns:
                    logging.info("[Migration] Adding up and down to outbounds table...")
                    conn.execute(text("ALTER TABLE outbounds ADD COLUMN up BIGINT DEFAULT 0"))
                    conn.execute(text("ALTER TABLE outbounds ADD COLUMN down BIGINT DEFAULT 0"))
                    conn.commit()
            if "user_sessions" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("user_sessions")]
                if "ip_address" not in columns:
                    logging.info("[Migration] Adding ip_address to user_sessions table...")
                    conn.execute(text("ALTER TABLE user_sessions ADD COLUMN ip_address VARCHAR DEFAULT NULL"))
                    conn.commit()
                if "user_agent" not in columns:
                    logging.info("[Migration] Adding user_agent to user_sessions table...")
                    conn.execute(text("ALTER TABLE user_sessions ADD COLUMN user_agent VARCHAR DEFAULT NULL"))
                    conn.commit()

            # Создание индексов (поддерживается и в PostgreSQL, и в SQLite через IF NOT EXISTS)
            if "client_stats" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_client_stats_email ON client_stats (email)"))
                conn.commit()
            if "audit_logs" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs (timestamp)"))
                conn.commit()
            if "user_sessions" in inspector.get_table_names():
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_sessions_expires_at ON user_sessions (expires_at)"))
                conn.commit()

    except Exception as e:
        if "postgresql" in admin_url:
            logging.error("=" * 80)
            logging.error(f"  ОШИБКА ПОДКЛЮЧЕНИЯ К POSTGRESQL: {e}")
            logging.error("  Убедитесь, что база данных запущена. Команда для запуска:")
            logging.error("  docker compose up -d db")
            logging.error("=" * 80)
        raise e
    finally:
        admin_engine.dispose()
        
    # Накладываем безопасные права доступа на файл базы данных SQLite
    try:
        if os.path.exists(DB_PATH):
            os.chmod(DB_PATH, 0o600)
    except Exception:
        pass
    
    with db_session() as session:
        # 1. Семена администратора по умолчанию
        admin_user = session.query(User).first()
        if not admin_user:
            if settings.ADMIN_USERNAME and settings.ADMIN_PASSWORD:
                uname = settings.ADMIN_USERNAME
                pwd = settings.ADMIN_PASSWORD
                is_generated = False
            else:
                uname = "admin_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
                pwd = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14))
                is_generated = True
                
            hashed = hash_password(pwd)
            default_admin = User(username=uname, password=hashed)
            session.add(default_admin)
            logging.info("Default administrator seeded into database.")
            
            if is_generated:
                logging.info("=" * 60)
                logging.info("  INITIAL ADMIN CREDENTIALS GENERATED:")
                logging.info(f"  Username: {uname}")
                logging.info(f"  Password: {pwd}")
                logging.info("  Please log in and change them immediately.")
                logging.info("=" * 60)
            else:
                # WIPE initial credentials from .env for security!
                try:
                    from backend.config import ENV_FILE
                    if ENV_FILE.exists():
                        with open(ENV_FILE, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        new_lines = []
                        for line in lines:
                            if not line.strip().startswith(("ADMIN_USERNAME=", "ADMIN_PASSWORD=")):
                                new_lines.append(line)
                        with open(ENV_FILE, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                        try:
                            os.chmod(ENV_FILE, 0o600)
                        except Exception:
                            pass
                        logging.info("Initial plaintext administrator credentials wiped from .env file successfully.")
                except Exception as e:
                    logging.error(f"Failed to wipe initial credentials from .env: {e}")
            
        # 2. Семена системных настроек маскировки
        decoy_type_setting = session.query(SystemSetting).filter_by(key="decoy_type").first()
        if not decoy_type_setting:
            session.add(SystemSetting(key="decoy_type", value="none"))
            
        decoy_val_setting = session.query(SystemSetting).filter_by(key="decoy_value").first()
        if not decoy_val_setting:
            session.add(SystemSetting(key="decoy_value", value="company_landing"))

        # Семена настроек Telegram по умолчанию
        tg_token_setting = session.query(SystemSetting).filter_by(key="telegram_bot_token").first()
        if not tg_token_setting:
            session.add(SystemSetting(key="telegram_bot_token", value=""))
            
        tg_admins_setting = session.query(SystemSetting).filter_by(key="telegram_admin_ids").first()
        if not tg_admins_setting:
            session.add(SystemSetting(key="telegram_admin_ids", value=""))

        tg_bot_enabled_setting = session.query(SystemSetting).filter_by(key="telegram_bot_enabled").first()
        if not tg_bot_enabled_setting:
            session.add(SystemSetting(key="telegram_bot_enabled", value="true"))

        tg_client_events_setting = session.query(SystemSetting).filter_by(key="telegram_client_events_enabled").first()
        if not tg_client_events_setting:
            session.add(SystemSetting(key="telegram_client_events_enabled", value="true"))

        # Семена настроек бэкапа по умолчанию
        backup_encrypt_setting = session.query(SystemSetting).filter_by(key="backup_encrypt").first()
        if not backup_encrypt_setting:
            session.add(SystemSetting(key="backup_encrypt", value="false"))
            
        backup_pwd_setting = session.query(SystemSetting).filter_by(key="backup_password").first()
        if not backup_pwd_setting:
            generated_pass = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
            session.add(SystemSetting(key="backup_password", value=generated_pass))
            
            logging.info("=" * 60)
            logging.info("  INITIAL BACKUP ENCRYPTION KEY GENERATED:")
            logging.info(f"  Backup Password: {generated_pass}")
            logging.info("  Keep it safe. Enabled backup files will be encrypted with this key.")
            logging.info("=" * 60)

        # 3. Семена исходящих подключений (Outbounds) по умолчанию
        if session.query(Outbound).count() == 0:
            session.add(Outbound(remark="Direct Connection", protocol="freedom", tag="direct", settings="{}", enable=1, is_system=1))
            session.add(Outbound(remark="Block Connection", protocol="blackhole", tag="blocked", settings="{}", enable=1, is_system=1))
            logging.info("Default outbounds seeded.")

        # 4. Семена правил маршрутизации (Routing Rules) по умолчанию
        if session.query(RoutingRule).count() == 0:
            # Читаем старые настройки для миграции
            block_torrent_val = session.query(SystemSetting).filter_by(key="block_torrent").first()
            bt_enable = 1 if (block_torrent_val and block_torrent_val.value == "true") else 0
            
            session.add(RoutingRule(remark="API Traffic", outbound_tag="api", inbound_tags='["api"]', enable=1, sort_order=1))
            session.add(RoutingRule(remark="Block BitTorrent", outbound_tag="blocked", protocols='["bittorrent"]', enable=bt_enable, sort_order=2))
            logging.info("Default routing rules seeded and migrated.")

        # 5. Семена входящих подключений (Inbounds) по умолчанию
        if session.query(Inbound).count() == 0:
            hys_port = 10000 + secrets.randbelow(40001)
            hys_stream_settings = {
                "hysteria": {
                    "obfsPassword": "",
                    "upMbps": 100,
                    "downMbps": 100,
                    "certMode": "self",
                    "masqType": "proxy",
                    "masqValue": "https://yahoo.com"
                }
            }
            default_hys = Inbound(
                remark="Default Hysteria 2",
                port=hys_port,
                protocol="hysteria2",
                settings="{}",
                stream_settings=json.dumps(hys_stream_settings),
                sniffing="{}",
                enable=0
            )
            session.add(default_hys)
            session.flush()
            
            hys_pwd = secrets.token_hex(6)
            default_client = ClientStats(
                inbound_id=default_hys.id,
                email="default_client",
                client_uuid_or_pwd=hys_pwd,
                enable=1,
                total=0,
                expiry_time=0,
                limit_ip=0
            )
            session.add(default_client)
            logging.info(f"Default Hysteria 2 inbound seeded on port {hys_port} with client 'default_client' (password: {hys_pwd}).")

    # 6. Load active sessions from database into memory to persist across restarts
    try:
        from backend.auth_utils import ACTIVE_SESSIONS
        now = int(time.time())
        with db_session() as session:
            active_db_sessions = session.query(UserSession).filter(UserSession.expires_at > now).all()
            for s in active_db_sessions:
                ACTIVE_SESSIONS.add(s.session_id)
        logging.info(f"Loaded {len(active_db_sessions)} active sessions from database.")
    except Exception as e:
        logging.error(f"Failed to load active sessions from database: {e}")

    # 7. Auto-migration: trim leading/trailing whitespace from client emails in database and inbounds settings JSON
    try:
        with db_session() as session:
            # First, check and update client_stats
            clients_to_fix = session.query(ClientStats).all()
            for c in clients_to_fix:
                if c.email and (c.email.startswith(" ") or c.email.endswith(" ")):
                    old_email = c.email
                    c.email = c.email.strip()
                    logging.info(f"[Auto-Trim] Trimmed whitespace from client_stats email: '{old_email}' -> '{c.email}'")
            
            # Second, check and update inbounds settings JSON
            inbounds_to_fix = session.query(Inbound).all()
            for ib in inbounds_to_fix:
                if ib.settings:
                    try:
                        settings_dict = json.loads(ib.settings)
                        clients_list = settings_dict.get("clients", [])
                        changed = False
                        for c_settings in clients_list:
                            email_settings = c_settings.get("email")
                            if email_settings and (email_settings.startswith(" ") or email_settings.endswith(" ")):
                                old_val = email_settings
                                c_settings["email"] = email_settings.strip()
                                changed = True
                                logging.info(f"[Auto-Trim] Trimmed whitespace from inbound {ib.id} settings client email: '{old_val}' -> '{c_settings['email']}'")
                        if changed:
                            ib.settings = json.dumps(settings_dict)
                    except Exception as ex:
                        logging.error(f"[Auto-Trim] Failed to parse/trim inbound {ib.id} settings JSON: {ex}")
            session.commit()
    except Exception as e:
        logging.error(f"[Auto-Trim] Failed to run client email auto-trim: {e}")

    # 8. Auto-migration: cleanup orphan routing rules referencing deleted inbounds or outbounds
    try:
        with db_session() as session:
            active_inbound_tags = {f"inbound-{ib.id}" for ib in session.query(Inbound).all()}
            active_outbound_tags = {ob.tag for ob in session.query(Outbound).all()}
            
            rules = session.query(RoutingRule).all()
            for r in rules:
                if r.outbound_tag not in active_outbound_tags:
                    session.delete(r)
                    logging.info(f"[Auto-Cleanup] Deleted orphan routing rule '{r.remark or r.id}' referencing deleted outbound '{r.outbound_tag}'")
                    continue
                if r.inbound_tags:
                    try:
                        tags = json.loads(r.inbound_tags)
                        if isinstance(tags, list) and tags:
                            valid_tags = [t for t in tags if t in active_inbound_tags or t.endswith("-socks") or t == "api"]
                            if not valid_tags:
                                session.delete(r)
                                logging.info(f"[Auto-Cleanup] Deleted orphan routing rule '{r.remark or r.id}' referencing deleted inbounds '{r.inbound_tags}'")
                            elif len(valid_tags) != len(tags):
                                r.inbound_tags = json.dumps(valid_tags)
                                logging.info(f"[Auto-Cleanup] Cleaned deleted inbounds from routing rule '{r.remark or r.id}'")
                    except Exception:
                        pass
            session.commit()
    except Exception as e:
        logging.error(f"[Auto-Cleanup] Failed to cleanup orphan routing rules: {e}")

    # 9. Auto-migration: remove "Block Ads (AdBlock)" and "Route ChatGPT via WARP" default routing rules if present
    try:
        with db_session() as session:
            deleted_count = session.query(RoutingRule).filter(RoutingRule.remark.in_(["Block Ads (AdBlock)", "Route ChatGPT via WARP"])).delete(synchronize_session=False)
            if deleted_count > 0:
                session.commit()
                logging.info(f"[Auto-Migration] Successfully removed {deleted_count} deprecated default routing rules.")
    except Exception as e:
        logging.error(f"[Auto-Migration] Failed to remove deprecated default routing rules: {e}")
