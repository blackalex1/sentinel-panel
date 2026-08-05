import os
import sys
import tempfile
import urllib.parse
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# 1. Setup Temporary Test Environment before importing backend code
temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
temp_path = Path(temp_dir.name)

# Patch configuration paths in sys.modules/backend.config
import backend.config
backend.config.DB_PATH = temp_path / "test_panel.db"
backend.config.XRAY_CONFIG_PATH = temp_path / "config.json"
backend.config.XRAY_LOG_PATH = temp_path / "xray.log"
backend.config.ENV_FILE = temp_path / ".env"

# Set test configuration settings
backend.config.settings.PANEL_PORT = 12345
backend.config.settings.PANEL_SECRET_PATH = "ui_test_secret"
backend.config.settings.API_TOKEN = "test_bearer_token"
backend.config.settings.ADMIN_USERNAME = "test_admin"
backend.config.settings.ADMIN_PASSWORD = "test_password"

# --- Автоконфигурация тестовой базы данных PostgreSQL / SQLite ---
test_admin_url = os.getenv("TEST_DATABASE_ADMIN_URL")
test_app_url = os.getenv("TEST_DATABASE_URL")

def ensure_postgres_db_exists(admin_url: str):
    """Проверяет существование тестовой БД PostgreSQL и создает её при необходимости (IF NOT EXISTS)"""
    if not admin_url or not admin_url.startswith("postgresql"):
        return
        
    from sqlalchemy import create_engine, text
    parsed = urllib.parse.urlparse(admin_url)
    db_name = parsed.path.lstrip("/")
    
    # Подключаемся к системной БД postgres для выполнения DDL-команды создания базы
    postgres_parsed = parsed._replace(path="/postgres")
    postgres_url = urllib.parse.urlunparse(postgres_parsed)
    
    # Используем AUTOCOMMIT для выполнения CREATE DATABASE вне транзакции
    temp_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    try:
        with temp_engine.connect() as conn:
            res = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": db_name}
            ).fetchone()
            if not res:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"Created test database: {db_name}")
    except Exception as e:
        print(f"Warning: Failed to verify/create database {db_name}: {e}")
    finally:
        temp_engine.dispose()

    # Даем приложению (DML пользователю) права в тестовой базе
    try:
        app_user = "spectre_app"
        if test_app_url:
            parsed_app = urllib.parse.urlparse(test_app_url)
            if parsed_app.username:
                app_user = parsed_app.username
                
        grant_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with grant_engine.connect() as conn:
            conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {app_user}"))
            conn.execute(text(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {app_user}"))
            conn.execute(text(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {app_user}"))
            conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO {app_user}"))
            conn.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO {app_user}"))
            print(f"Granted database privileges to {app_user} in {db_name}")
    except Exception as e:
        print(f"Warning: Failed to grant database privileges in {db_name}: {e}")
    finally:
        if 'grant_engine' in locals():
            grant_engine.dispose()

if not test_app_url:
    # По умолчанию для тестов всегда используем SQLite, чтобы не требовать запущенного PostgreSQL.
    # Если разработчик явно хочет протестировать на PostgreSQL, он может задать TEST_DATABASE_URL.
    test_app_url = f"sqlite:///{backend.config.DB_PATH}"
    test_admin_url = f"sqlite:///{backend.config.DB_PATH}"

# Записываем тестовые URL подключения в настройки
backend.config.settings.DATABASE_URL = test_app_url
backend.config.settings.DATABASE_ADMIN_URL = test_admin_url

if test_admin_url.startswith("postgresql"):
    ensure_postgres_db_exists(test_admin_url)

# --- Удаление старых таблиц для чистоты тестов (клин-слейт) ---
if test_admin_url:
    from sqlalchemy import create_engine
    from backend.models import Base
    
    admin_conn_url = test_admin_url
    if admin_conn_url.startswith("postgres://"):
        admin_conn_url = admin_conn_url.replace("postgres://", "postgresql://", 1)
        
    connect_args = {}
    if admin_conn_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        
    temp_admin_engine = create_engine(admin_conn_url, connect_args=connect_args)
    try:
        Base.metadata.drop_all(temp_admin_engine)
        print("Dropped all tables in test database.")
    except Exception as e:
        print(f"Warning: Failed to clean up tables: {e}")
    finally:
        temp_admin_engine.dispose()

@pytest.fixture(scope="function", autouse=True)
def cleanup_real_core_processes():
    yield
    try:
        from backend.xray import stop_xray
        stop_xray()
    except Exception:
        pass
    try:
        from backend.singbox import stop_singbox
        stop_singbox()
    except Exception:
        pass
    try:
        from backend.hysteria import stop_hysteria
        stop_hysteria()
    except Exception:
        pass

# 2.5 Mock Host Client
import backend.host_client
def mock_send_command(action: str, params: dict = None, timeout: float = 3.0) -> dict:
    if action == "get_bbr_status":
        return {"success": True, "bbr_enabled": True}
    elif action == "enable_bbr":
        return {"success": True, "msg": "BBR enabled successfully"}
    elif action == "get_optimization_status":
        return {"success": True, "optimized": False}
    elif action == "apply_optimizations":
        return {"success": True, "msg": "[Mock] Network optimized."}
    elif action == "get_system_stats":
        return {
            "success": True,
            "cpu": 12.5,
            "mem": {"current": 1000000000, "total": 4000000000},
            "swap": {"current": 500000000, "total": 2000000000, "percent": 25.0},
            "uptime": 7200,
            "netIO": {"up": 500000, "down": 1500000}
        }
    return backend.host_client.host_client._mock_response(action, params)


backend.host_client.host_client.send_command = mock_send_command

# Initialize the test database once
from backend.database import init_db, set_setting
init_db()
set_setting("telegram_bot_token", "123456:ABC-DEF1234ghIkl-zyx")
set_setting("telegram_admin_ids", "55555,66666")

@pytest.fixture(scope="function", autouse=True)
def clear_login_attempts():
    """Clear login rate-limiting attempts before each test."""
    try:
        from backend.routes.auth import LOGIN_ATTEMPTS
        LOGIN_ATTEMPTS.clear()
    except Exception:
        pass

@pytest.fixture(scope="function")
def client():
    """FastAPI TestClient fixture."""
    from backend.main import app
    return TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def cleanup_db_connections():
    yield
    from backend.database import engine
    engine.dispose()
