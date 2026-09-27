import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session

from backend.config import settings, DB_PATH
from backend.models import Base

def normalize_database_url(url: str) -> str:
    """
    Нормализует URL базы данных PostgreSQL, обеспечивая совместимость драйверов
    (psycopg v3 и psycopg2) как для SQLAlchemy 2.0, так и для SQLAlchemy 2.1+.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    has_psycopg = False
    try:
        import psycopg  # noqa: F401
        has_psycopg = True
    except ImportError:
        pass

    has_psycopg2 = False
    try:
        import psycopg2  # noqa: F401
        has_psycopg2 = True
    except ImportError:
        pass

    if url.startswith("postgresql://"):
        if not has_psycopg and has_psycopg2:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif has_psycopg and not has_psycopg2:
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql+psycopg://") and not has_psycopg and has_psycopg2:
        url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql+psycopg2://") and not has_psycopg2 and has_psycopg:
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

    return url

# Определяем URL подключения (DML для приложения)
database_url = settings.DATABASE_URL
if not database_url:
    database_url = f"sqlite:///{DB_PATH}"
else:
    database_url = normalize_database_url(database_url)

# Добавляем параметры подключения для SQLite
connect_args = {}
pool_args = {}
if database_url.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        "timeout": 15.0
    }
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
elif database_url.startswith("postgresql"):
    import time
    connect_args = {
        "connect_timeout": 5,
        "application_name": "sentinel-panel",
    }
    pool_args = {
        "pool_size": 20,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }
    engine = None
    last_err = None
    for attempt in range(12):
        try:
            temp_engine = create_engine(database_url, connect_args=connect_args, **pool_args)
            with temp_engine.connect() as conn:
                engine = temp_engine
                break
        except Exception as e:
            last_err = e
            time.sleep(1)
            
    if engine is None:
        logging.warning(f"PostgreSQL server not available after retries ({last_err}). Falling back to local SQLite database.")
        database_url = f"sqlite:///{DB_PATH}"
        connect_args = {"check_same_thread": False, "timeout": 15.0}
        engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)

# SQLite performance tuning: applied on every new connection via event hook.
# WAL mode: readers never block the writer; writer never blocks readers.
# synchronous=NORMAL: safe with WAL, avoids fsync on every transaction (only on checkpoints).
# busy_timeout=10000: wait up to 10 seconds for locks to clear instead of failing or spinning.
# cache_size: 20 000 pages × 1KB = ~20 MB page cache per connection.
# mmap_size: 128 MB memory-mapped I/O — reduces syscall overhead on read-heavy workloads.
# temp_store=MEMORY: stores temporary B-trees (for ORDER BY / GROUP BY) in RAM instead of disk.
if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA cache_size=-20000")   # negative = kibibytes, 20 000 KiB ≈ 20 MB
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
