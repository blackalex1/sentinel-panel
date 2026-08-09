import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session

from backend.config import settings, DB_PATH
from backend.models import Base

# Определяем URL подключения (DML для приложения)
database_url = settings.DATABASE_URL
if not database_url:
    database_url = f"sqlite:///{DB_PATH}"

# Обеспечиваем совместимость с префиксом postgres://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Добавляем параметры подключения для SQLite
connect_args = {}
pool_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif database_url.startswith("postgresql"):
    connect_args = {
        # Не зависать бесконечно если PostgreSQL недоступен
        "connect_timeout": 10,
        # Видно в pg_stat_activity — удобно для дебага
        "application_name": "spectre-panel",
    }
    pool_args = {
        "pool_size": 20,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        # CRITICAL: проверяет живость соединения через SELECT 1 перед каждым checkout.
        # Без этого устаревшее соединение (после рестарта PG или firewall timeout)
        # приведёт к ошибке у первого запроса, который её получит.
        "pool_pre_ping": True,
    }

try:
    engine = create_engine(database_url, connect_args=connect_args, **pool_args)
    if database_url.startswith("postgresql"):
        with engine.connect() as conn:
            pass
except Exception as e:
    if database_url.startswith("postgresql"):
        logging.warning(f"PostgreSQL server not available ({e}). Falling back to local SQLite database.")
        database_url = f"sqlite:///{DB_PATH}"
        connect_args = {"check_same_thread": False}
        engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    else:
        raise e

# SQLite performance tuning: applied on every new connection via event hook.
# WAL mode: readers never block the writer; writer never blocks readers.
# synchronous=NORMAL: safe with WAL, avoids fsync on every transaction (only on checkpoints).
# cache_size: 10 000 pages × 4KB = ~40 MB page cache per connection.
# mmap_size: 128 MB memory-mapped I/O — reduces syscall overhead on read-heavy workloads.
# temp_store=MEMORY: stores temporary B-trees (for ORDER BY / GROUP BY) in RAM instead of disk.
if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-10000")   # negative = kibibytes, 10 000 KiB ≈ 10 MB
        cursor.execute("PRAGMA mmap_size=134217728")  # 128 MB
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

@contextmanager
def db_session():
    """Контекстный менеджер для безопасного управления сессиями бд"""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_db_connection():
    """Обратная совместимость для унаследованного кода"""
    return engine.raw_connection()
