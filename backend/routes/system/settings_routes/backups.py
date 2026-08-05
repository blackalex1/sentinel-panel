import logging
from fastapi import APIRouter, Request, Response

from backend.database import get_setting, set_setting
from backend.i18n import t

router = APIRouter()

@router.get("/api/system/backup/download")
async def download_backup_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    lang = get_setting("language", "ru")
    try:
        from backend.backup import create_backup_dump
        dump_str = create_backup_dump()
        return Response(
            content=dump_str,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=panel_backup.json"}
        )
    except Exception as e:
        return {"success": False, "msg": t("backup_create_error", lang, error=str(e))}

@router.post("/api/system/backup/upload")
async def upload_backup_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    lang = get_setting("language", "ru")
    try:
        form = await request.form()
        file = form.get("file")
        if not file:
            return {"success": False, "msg": t("backup_file_not_provided", lang)}
        content = await file.read()
        dump_str = content.decode("utf-8")
        
        if dump_str.startswith("enc1:"):
            password = form.get("password")
            if not password:
                password = get_setting("backup_password", "")
                
            if not password:
                return {
                    "success": False,
                    "code": "password_required",
                    "msg": t("backup_password_required", lang)
                }
                
            try:
                from backend.backup import decrypt_data
                dump_str = decrypt_data(dump_str, password)
            except Exception as e:
                logging.error(f"[Backup Upload] Failed to decrypt backup data: {e}")
                return {
                    "success": False,
                    "code": "invalid_password",
                    "msg": t("backup_invalid_password", lang)
                }
                
        from backend.backup import restore_backup_dump
        success, msg = restore_backup_dump(dump_str, lang=lang)
        return {"success": success, "msg": msg}
    except Exception as e:
        return {"success": False, "msg": t("backup_upload_error", lang, error=str(e))}

@router.post("/api/system/backup/clear")
async def clear_all_backups_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    lang = get_setting("language", "ru")
    try:
        from backend.config import BASE_DIR
        backups_dir = BASE_DIR / "backups"
        count = 0
        if backups_dir.exists():
            for f in backups_dir.glob("backup_*.json"):
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
        
        # Log action
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "clear_all_backups", details=f"deleted:{count}")
        
        return {"success": True, "msg": t("backup_clear_success", lang, count=count)}
    except Exception as e:
        return {"success": False, "msg": t("backup_clear_error", lang, error=str(e))}

@router.post("/api/settings/backup/password")
async def change_backup_password_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    lang = get_setting("language", "ru")
    try:
        data = await request.json()
        current_password = data.get("current_password", "").strip()
        new_password = data.get("new_password", "").strip()
        
        if not new_password:
            return {"success": False, "msg": t("backup_password_fields_required", lang)}
            
        stored_password = get_setting("backup_password", "")
        # Only verify current password if backup encryption is currently active/enabled
        encrypt_enabled = get_setting("backup_encrypt", "false") == "true"
        if stored_password:
            if current_password:
                if current_password != stored_password:
                    return {"success": False, "msg": t("backup_current_password_incorrect", lang)}
            elif encrypt_enabled:
                return {"success": False, "msg": t("backup_password_fields_required", lang)}
            
        set_setting("backup_password", new_password)
        
        # Log action
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "change_backup_password", details="status:success")
        
        return {"success": True, "msg": t("backup_password_changed_success", lang)}
    except Exception as e:
        return {"success": False, "msg": t("backup_password_change_error", lang, error=str(e))}
