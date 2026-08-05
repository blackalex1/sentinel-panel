import time
from backend.models import SharedCache
import backend.database

def get_shared_cache(key: str) -> str | None:
    now = int(time.time())
    try:
        with backend.database.db_session() as session:
            item = session.query(SharedCache).filter(SharedCache.key == key, SharedCache.expires_at > now).first()
            if item:
                return item.value
    except Exception:
        pass
    return None

def set_shared_cache(key: str, value: str, duration_seconds: int):
    expires_at = int(time.time()) + duration_seconds
    try:
        with backend.database.db_session() as session:
            # Delete if exists to overwrite
            session.query(SharedCache).filter(SharedCache.key == key).delete()
            item = SharedCache(key=key, value=value, expires_at=expires_at)
            session.add(item)
    except Exception:
        pass

def delete_shared_cache(key: str):
    try:
        with backend.database.db_session() as session:
            session.query(SharedCache).filter(SharedCache.key == key).delete()
    except Exception:
        pass

def clean_expired_shared_cache():
    now = int(time.time())
    try:
        with backend.database.db_session() as session:
            session.query(SharedCache).filter(SharedCache.expires_at < now).delete()
    except Exception:
        pass
