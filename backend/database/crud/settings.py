import time
import threading
from backend.models import SystemSetting
import backend.database

# ---------------------------------------------------------------------------
# In-memory TTL cache for system settings.
# Settings rarely change — a 10-second cache eliminates the most common
# N+1 pattern where a single request calls get_setting() 10–15 times.
# ---------------------------------------------------------------------------
_settings_cache: dict[str, tuple[str, float]] = {}  # key → (value, expires_at)
_settings_cache_lock = threading.Lock()
_SETTINGS_CACHE_TTL = 10.0  # seconds


def get_setting(key: str, default: str = "") -> str:
    """Возвращает значение настройки из кэша или БД."""
    now = time.monotonic()
    with _settings_cache_lock:
        cached = _settings_cache.get(key)
        if cached is not None and cached[1] > now:
            return cached[0]

    # Cache miss — hit the database
    with backend.database.db_session() as session:
        setting = session.query(SystemSetting).filter_by(key=key).first()
        value = setting.value if setting else default

    with _settings_cache_lock:
        _settings_cache[key] = (value, now + _SETTINGS_CACHE_TTL)

    return value


def set_setting(key: str, value: str):
    """Сохраняет или обновляет значение настройки в БД и сбрасывает кэш."""
    with backend.database.db_session() as session:
        setting = session.query(SystemSetting).filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            session.add(SystemSetting(key=key, value=str(value)))

    # Invalidate cache entry so next read sees the new value immediately
    with _settings_cache_lock:
        _settings_cache.pop(key, None)


def invalidate_settings_cache():
    """Полностью сбрасывает кэш настроек (вызывать после массового изменения настроек)."""
    with _settings_cache_lock:
        _settings_cache.clear()

