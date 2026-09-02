import os
import sys
import time
import tempfile
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# 1. Setup Temporary Test Environment before importing backend code
temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
temp_path = Path(temp_dir.name)

# Patch configuration paths in sys.modules/backend.config
worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
import backend.config
backend.config.DB_PATH = temp_path / f"test_panel_{worker_id}.db"
backend.config.XRAY_CONFIG_PATH = temp_path / f"config_{worker_id}.json"
backend.config.XRAY_LOG_PATH = temp_path / f"xray_{worker_id}.log"
backend.config.ENV_FILE = temp_path / f".env_{worker_id}"
backend.config.settings.DATABASE_URL = f"sqlite:///{backend.config.DB_PATH}"

# Set test configuration settings
backend.config.settings.PANEL_PORT = 12345
backend.config.settings.PANEL_SECRET_PATH = "ui_test_secret"
backend.config.settings.API_TOKEN = "test_bearer_token"
backend.config.settings.ADMIN_USERNAME = "test_admin"
backend.config.settings.ADMIN_PASSWORD = "test_password"
backend.config.settings.LOGIN_FAIL_DELAY = 0.0

import backend.database.crud.auth
backend.database.crud.auth.PBKDF2_ITERATIONS = 1000


# --- Автоконфигурация тестовой базы данных PostgreSQL / SQLite ---
test_admin_url = os.getenv("TEST_DATABASE_ADMIN_URL")
test_app_url = os.getenv("TEST_DATABASE_URL")

if worker_id != "master":
    if test_app_url and not test_app_url.startswith("sqlite"):
        test_app_url = f"{test_app_url}_{worker_id}"
    if test_admin_url and not test_admin_url.startswith("sqlite"):
        test_admin_url = f"{test_admin_url}_{worker_id}"

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
        app_user = "sentinel_app"
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

class CrossProcessCoreLock:
    def __init__(self):
        self.lock_path = os.path.join(tempfile.gettempdir(), "sentinel_real_core_test.lck")
        self.f = None

    def acquire(self):
        self.f = open(self.lock_path, "a+")
        if sys.platform == "win32":
            import msvcrt
            start = time.time()
            while True:
                try:
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except (OSError, IOError, PermissionError):
                    time.sleep(0.1)
                    if time.time() - start > 120:
                        break
        else:
            import fcntl
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX)

    def release(self):
        if self.f:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self.f.close()
            except Exception:
                pass
            self.f = None

@pytest.fixture(scope="function", autouse=True)
def cleanup_real_core_processes(request):
    """
    Autouse fixture: cleanly stop any VPN core processes after every test.

    CrossProcessCoreLock is intentionally NOT used here.
    Each xdist worker has its own isolated SQLite DB (test_panel_{worker_id}.db)
    and all subprocess.Popen calls are mocked in CI — no real cross-process
    port conflicts occur, so a global file mutex would only serialize all workers
    and cause timeouts.
    """
    try:
        yield
    finally:
        # Only clean up real cores if this test actually belonged to core_ops group
        marker = request.node.get_closest_marker("xdist_group")
        if marker and marker.args and marker.args[0] == "core_ops":
            import logging as _logging
            _logging.disable(_logging.CRITICAL)
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
            _logging.disable(_logging.NOTSET)

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
        from backend.routes.auth_routes.login import LOGIN_ATTEMPTS
        LOGIN_ATTEMPTS.clear()
    except Exception:
        try:
            from backend.routes.auth import LOGIN_ATTEMPTS
            LOGIN_ATTEMPTS.clear()
        except Exception:
            pass


@pytest.fixture(scope="function")
def client(isolated_db):
    """FastAPI TestClient fixture backed by the test's isolated database."""
    from backend.main import app
    return TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def cleanup_db_connections():
    yield
    from backend.database import engine
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def reset_port_allocator():
    """
    Reset the shared port-counter file once per pytest session.

    In xdist parallel mode this session fixture runs once per *worker process*.
    If every worker reset the counter we'd get a race: a late-starting worker
    resets to 49000 while an early worker has already allocated and is using
    those ports, causing the next get_free_port() call to return a port that
    is already bound by xray.

    Fix: only the first worker (gw0) or sequential-mode master resets.
    """
    _worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    if _worker_id in ("master", "gw0"):
        try:
            from tests.core_verifier import reset_port_counter
            reset_port_counter()
        except Exception:
            pass  # Non-fatal: allocator will self-heal on first get_free_port() call
    yield



@pytest.fixture(scope="session", autouse=True)
def mock_restart_services_background():
    """
    Globally replace restart_services_background with a no-op for all tests.

    Without this, every routing/inbound mutation endpoint would spawn a
    daemon timer thread that tries to restart Xray/Sing-box/Hysteria binaries
    which don't exist in the test environment. The no-op keeps tests fast,
    isolated, and free from background thread noise.
    """
    import unittest.mock as mock
    import backend.utils.service_restart as _restart_mod
    with mock.patch.object(_restart_mod, "restart_services_background", return_value=None):
        yield


@pytest.fixture(scope="function", autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Give every test its own fresh SQLite database.

    Patches ONLY session_factory (+ engine / Session) in
    backend.database.connection.  The original db_session() function reads
    session_factory from that module's __dict__ at *call time*, so patching
    session_factory alone is sufficient to redirect all DB access.

    We intentionally do NOT patch db_session itself.  If we did, any module
    that lazily does `from backend.database import db_session` (e.g. backend.audit
    pulled in by backend.client_alerts during a test body) would permanently capture
    the per-test closure.  After teardown that module's local reference still points
    to the previous test's disposed engine, so the next test's log_action() silently
    writes to the dead engine while the test reads from the new one.
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker, scoped_session
    import backend.database.connection as db_conn
    import backend.database as db_module
    from backend.models import Base
    from backend.database.seeding import init_db
    from backend.database import set_setting
    from backend.database.crud.settings import invalidate_settings_cache

    # Flush stale TTL-cached settings from any previous test before we switch engines.
    invalidate_settings_cache()

    db_file = tmp_path / "test_isolated.db"
    new_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 15.0},
    )

    @event.listens_for(new_engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()

    Base.metadata.create_all(new_engine)
    new_factory = sessionmaker(bind=new_engine)
    new_scoped  = scoped_session(new_factory)

    # Patch engine + session_factory + Session — NOT db_session.
    monkeypatch.setattr(db_conn, "engine",          new_engine)
    monkeypatch.setattr(db_conn, "session_factory", new_factory)
    monkeypatch.setattr(db_conn, "Session",         new_scoped)

    monkeypatch.setattr(db_module, "engine",          new_engine)
    monkeypatch.setattr(db_module, "session_factory", new_factory)
    monkeypatch.setattr(db_module, "Session",         new_scoped)


    # Seed with standard data
    init_db()
    set_setting("telegram_bot_token", "123456:ABC-DEF1234ghIkl-zyx")
    set_setting("telegram_admin_ids",  "55555,66666")

    yield

    # Prevent stale TTL values from leaking into the next test.
    invalidate_settings_cache()
    new_scoped.remove()
    new_engine.dispose()


