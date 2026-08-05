import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
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
    pool_args = {
        "pool_size": 20,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800
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
        engine = create_engine(database_url, connect_args=connect_args)
    else:
        raise e

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
