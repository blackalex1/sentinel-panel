from backend.models import SystemSetting
import backend.database

def get_setting(key: str, default: str = "") -> str:
    """Возвращает значение настройки из БД"""
    with backend.database.db_session() as session:
        setting = session.query(SystemSetting).filter_by(key=key).first()
        if setting:
            return setting.value
        return default

def set_setting(key: str, value: str):
    """Сохраняет или обновляет значение настройки в БД"""
    with backend.database.db_session() as session:
        setting = session.query(SystemSetting).filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            session.add(SystemSetting(key=key, value=str(value)))
