import os
import sys
import subprocess
import logging
from pathlib import Path
import psutil

from backend.config import BIN_DIR

TELEGRAM_BOT_LOG_PATH = BIN_DIR / "telegram_bot.log"

def restart_telegram_bot() -> bool:
    """
    Находит и завершает все запущенные процессы mini_bot.py,
    после чего запускает новый процесс в фоновом режиме.
    """
    current_pid = os.getpid()
    
    # 1. Поиск и завершение существующих процессов mini_bot.py
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            is_bot = False
            for arg in cmdline:
                if "mini_bot.py" in arg:
                    is_bot = True
                    break
            
            if is_bot and proc.info["pid"] != current_pid:
                logging.info(f"[Bot Manager] Terminating existing Telegram Bot process (PID {proc.info['pid']})...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    logging.warning(f"[Bot Manager] Process PID {proc.info['pid']} did not terminate. Killing...")
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # 2. Проверка, включен ли бот в настройках и задан ли токен
    from backend.database.crud.settings import get_setting
    bot_token = get_setting("telegram_bot_token", "")
    bot_enabled = get_setting("telegram_bot_enabled", "true") == "true"
    
    if not bot_token or not bot_enabled:
        logging.info("[Bot Manager] Telegram bot is disabled or token is empty. Not starting bot process.")
        return True

    # 3. Определение пути к скрипту бота
    # Корневой каталог проекта: backend/bot_manager.py -> parent of backend -> panel
    project_root = Path(__file__).resolve().parent.parent
    bot_path = project_root / "bot" / "mini_bot.py"
    
    if not bot_path.exists():
        logging.error(f"[Bot Manager] Cannot find bot script at: {bot_path}")
        return False
        
    logging.info(f"[Bot Manager] Starting new Telegram Bot process from: {bot_path}")
    
    try:
        # Открываем лог-файл на дозапись
        log_file = open(TELEGRAM_BOT_LOG_PATH, "a", encoding="utf-8", errors="ignore")
        
        # Запуск в фоновом режиме, независимом от родительского процесса
        if sys.platform != "win32":
            subprocess.Popen(
                [sys.executable, str(bot_path)],
                stdout=log_file,
                stderr=log_file,
                close_fds=True,
                start_new_session=True
            )
        else:
            # На Windows используем специальные флаги создания процесса
            subprocess.Popen(
                [sys.executable, str(bot_path)],
                stdout=log_file,
                stderr=log_file,
                close_fds=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
            
        logging.info("[Bot Manager] Telegram Bot process spawned successfully.")
        return True
    except Exception as e:
        logging.error(f"[Bot Manager] Failed to start Telegram Bot process: {e}")
        return False
