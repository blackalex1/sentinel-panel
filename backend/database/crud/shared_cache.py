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

def atomic_increment_shared_cache(key: str, duration_seconds: int) -> int:
    """Atomically increment an integer counter stored in SharedCache.

    Uses a single SQL UPSERT so the operation is safe under concurrent
    access from multiple Uvicorn workers:
      - If the key does not exist (or has expired): inserts with value=1.
      - If the key exists and has not expired: increments the stored integer by 1.

    Returns the new counter value, or -1 on error.
    """
    now = int(time.time())
    expires_at = now + duration_seconds
    try:
        with backend.database.db_session() as session:
            from sqlalchemy import text
            result = session.execute(
                text("""
                    INSERT INTO shared_cache (key, value, expires_at)
                    VALUES (:key, '1', :exp)
                    ON CONFLICT(key) DO UPDATE SET
                        value = CASE
                            WHEN shared_cache.expires_at <= :now
                            THEN '1'
                            ELSE CAST(CAST(shared_cache.value AS INTEGER) + 1 AS TEXT)
                        END,
                        expires_at = CASE
                            WHEN shared_cache.expires_at <= :now
                            THEN :exp
                            ELSE shared_cache.expires_at
                        END
                    RETURNING CAST(value AS INTEGER)
                """),
                {"key": key, "exp": expires_at, "now": now}
            )
            row = result.fetchone()
            return row[0] if row else 1
    except Exception:
        pass
    return -1

def get_int_shared_cache(key: str) -> int:
    """Returns the integer value stored under key, or 0 if absent/expired."""
    val = get_shared_cache(key)
    if val is None:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

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
