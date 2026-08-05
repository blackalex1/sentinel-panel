import os
import secrets
import random
import string
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Определяем базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = CONFIG_DIR / ".env"

def generate_random_string(length: int = 12, chars: str = string.ascii_letters + string.digits) -> str:
    return "".join(secrets.choice(chars) for _ in range(length))

def init_env_file():
    """Инициализирует .env файл случайными значениями при первом запуске панели"""
    if not ENV_FILE.exists():
        # Генерация случайных параметров
        port = 15000 + secrets.randbelow(40001)
        secret_path = f"ui_{secrets.token_hex(6)}"
        api_token = secrets.token_hex(32)
        
        # Генерация безопасных учетных данных для базы данных
        db_admin_password = generate_random_string(24)
        db_app_password = generate_random_string(24)
        
        env_content = f"""# Настройки веб-панели
PANEL_PORT={port}
PANEL_SECRET_PATH={secret_path}

# Токен для интеграции с контроллером
API_TOKEN={api_token}

# Настройки СУБД PostgreSQL (Параметры безопасности)
POSTGRES_DB=spectre_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD={db_admin_password}

DB_APP_USER=spectre_app
DB_APP_PASSWORD={db_app_password}

# Строки подключения к БД (Администратор DDL / Приложение DML)
DATABASE_ADMIN_URL=postgresql://postgres:{db_admin_password}@127.0.0.1:5432/spectre_db
DATABASE_URL=postgresql://spectre_app:{db_app_password}@127.0.0.1:5432/spectre_db
"""
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(env_content)
        
        try:
            os.chmod(ENV_FILE, 0o600)
        except Exception:
            pass
        
        print("=" * 60)
        print("  СГЕНЕРИРОВАНЫ СЛУЧАЙНЫЕ НАСТРОЙКИ ДЛЯ ПЕРВОГО ЗАПУСКА:")
        print(f"  Порт панели:   {port}")
        print(f"  Секретный путь: /{secret_path}/")
        print(f"  API Токен бота: {api_token}")
        print(f"  Конфигурационный файл .env создан в {ENV_FILE}")
        print("=" * 60)



# Инициализируем файл окружения перед загрузкой настроек
init_env_file()

class Settings(BaseSettings):
    PANEL_PORT: int = 2053
    PANEL_SECRET_PATH: str = "ui"
    JWT_SECRET_KEY: str = secrets.token_hex(32)
    ADMIN_USERNAME: str | None = None
    ADMIN_PASSWORD: str | None = None
    API_TOKEN: str = "default_api_token"

    # Маскировка (Сайты-заглушки)
    DECOY_TYPE: str = "none"  # none, static, proxy
    DECOY_VALUE: str = "company_landing"  # имя шаблона или URL для прокси

    # База данных (SQLite по умолчанию, или PostgreSQL)
    DATABASE_ADMIN_URL: str = ""
    DATABASE_URL: str = ""

    # Настройки сессии (в днях)
    SESSION_TIMEOUT_DAYS: int = 7

    # Защита от брутфорса
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_ATTEMPTS_PERIOD: int = 60
    LOGIN_FAIL_DELAY: float = 1.0




    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

def save_settings_to_env(new_settings_dict: dict):
    """Сохраняет переданные настройки в .env и обновляет глобальный объект settings"""
    if not ENV_FILE.exists():
        init_env_file()
        
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    for key, val in new_settings_dict.items():
        updated = False
        val_str = str(val)
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={val_str}\n"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={val_str}\n")
            
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    try:
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        pass
        
    # Обновляем глобальный объект settings в памяти
    global settings
    for key, val in new_settings_dict.items():
        if hasattr(settings, key):
            attr_type = type(getattr(settings, key))
            try:
                setattr(settings, key, attr_type(val))
            except Exception:
                setattr(settings, key, val)



# Системные пути
BIN_DIR = BASE_DIR / "bin"
BIN_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = BASE_DIR / "panel.db"
XRAY_CONFIG_PATH = BIN_DIR / "config.json"
XRAY_LOG_PATH = BIN_DIR / "xray.log"
HYSTERIA_LOG_PATH = BIN_DIR / "hysteria.log"
SINGBOX_LOG_PATH = BIN_DIR / "singbox.log"
SINGBOX_CONFIG_PATH = BIN_DIR / "singbox.json"

# Имена и пути исполняемых файлов ядер в зависимости от ОС
IS_WINDOWS = sys.platform == "win32"
XRAY_BIN_NAME = "xray.exe" if IS_WINDOWS else "xray"
XRAY_BIN_PATH = BIN_DIR / XRAY_BIN_NAME

HYSTERIA_BIN_NAME = "hysteria.exe" if IS_WINDOWS else "hysteria"
HYSTERIA_BIN_PATH = BIN_DIR / HYSTERIA_BIN_NAME

SINGBOX_BIN_NAME = "sing-box.exe" if IS_WINDOWS else "sing-box"
SINGBOX_BIN_PATH = BIN_DIR / SINGBOX_BIN_NAME

