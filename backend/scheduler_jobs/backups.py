import time
import logging
import asyncio
from backend.database import get_setting, set_setting

def check_and_run_backups():
    """Automated backups checker and executor."""
    backup_enable = get_setting("backup_enable", "false") == "true"
    backup_telegram = get_setting("backup_telegram", "false") == "true"
    if not backup_enable and not backup_telegram:
        return
        
    backup_interval = get_setting("backup_interval", "daily")
    interval_seconds = 86400  # Default daily
    if backup_interval == "hourly":
        interval_seconds = 3600
    elif backup_interval == "weekly":
        interval_seconds = 604800
        
    last_backup = int(get_setting("last_backup_time", "0"))
    now_ts = int(time.time())
    
    if now_ts - last_backup >= interval_seconds:
        logging.info("[Backup Scheduler] Starting automated backup...")
        try:
            # 1. Run backup
            from backend.backup import create_backup_dump
            dump_data = create_backup_dump()
            
            # 2. Save locally
            from backend.config import BASE_DIR
            backups_dir = BASE_DIR / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            
            backup_filename = f"backup_{now_ts}.json"
            backup_file_path = backups_dir / backup_filename
            with open(backup_file_path, "w", encoding="utf-8") as f:
                f.write(dump_data)
            logging.info(f"[Backup Scheduler] Backup saved locally to {backup_file_path}")
            
            # 3. Rotate old backups (only if backup_enable is True)
            if backup_enable:
                try:
                    rotation_limit = int(get_setting("backup_rotation", "7"))
                except ValueError:
                    rotation_limit = 7
                    
                backup_files = sorted(
                    list(backups_dir.glob("backup_*.json")),
                    key=lambda x: x.stat().st_mtime
                )
                while len(backup_files) > rotation_limit:
                    oldest_file = backup_files.pop(0)
                    try:
                        oldest_file.unlink()
                        logging.info(f"[Backup Scheduler] Deleted old backup file: {oldest_file.name}")
                    except Exception as e:
                        logging.error(f"[Backup Scheduler] Failed to delete old backup file {oldest_file.name}: {e}")
            
            # 4. Telegram notification/sending
            telegram_attempted = False
            if backup_telegram:
                bot_token = get_setting("telegram_bot_token", "")
                admin_ids_str = get_setting("telegram_admin_ids", "")
                if bot_token and admin_ids_str:
                    admin_ids = [x.strip() for x in admin_ids_str.split(",") if x.strip()]
                    delete_after = not backup_enable
                    asyncio_send_backup_to_telegram(bot_token, admin_ids, str(backup_file_path), backup_filename, delete_after)
                    telegram_attempted = True
                    
            if not backup_enable and not telegram_attempted:
                # Local backup deletion to avoid disk leak
                try:
                    backup_file_path.unlink()
                    logging.warning("[Backup Scheduler] Telegram backup enabled but Telegram is not configured. Local backup deleted to avoid disk leak.")
                except Exception as e:
                    logging.error(f"[Backup Scheduler] Failed to delete local backup file: {e}")
                    
            # 5. Update last backup time
            set_setting("last_backup_time", str(now_ts))
            
        except Exception as e:
            logging.error(f"[Backup Scheduler] Automated backup failed: {e}")

def asyncio_send_backup_to_telegram(bot_token: str, admin_ids: list, file_path: str, filename: str, delete_after: bool = False):
    """Sends backup file to admins in Telegram (async background task)."""
    try:
        from aiogram import Bot
        from aiogram.types import FSInputFile
        
        async def send_to_all_and_cleanup():
            from backend.database import get_setting
            from backend.i18n import t
            lang = get_setting("language", "ru")
            caption_text = t("backup_scheduler_telegram_caption", lang, filename=filename)
            try:
                for admin_id in admin_ids:
                    bot = Bot(token=bot_token)
                    try:
                        document = FSInputFile(file_path, filename=filename)
                        await bot.send_document(
                            chat_id=admin_id,
                            document=document,
                            caption=caption_text,
                            parse_mode="HTML"
                        )
                    except Exception as ex:
                        logging.error(f"[Backup Scheduler] Failed to send document to {admin_id}: {ex}")
                    finally:
                        await bot.session.close()
            finally:
                if delete_after:
                    try:
                        import os
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logging.info(f"[Backup Scheduler] Temporary backup file deleted: {filename}")
                    except Exception as ex:
                        logging.error(f"[Backup Scheduler] Failed to delete temporary backup file {filename}: {ex}")
                        
        loop = asyncio.get_running_loop()
        loop.create_task(send_to_all_and_cleanup())
    except RuntimeError:
        if delete_after:
            try:
                import os
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
    except Exception as e:
        logging.error(f"[Backup Scheduler] Failed to schedule Telegram sending: {e}")
        if delete_after:
            try:
                import os
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
