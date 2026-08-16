from fastapi import APIRouter, Request

from backend.config import settings
from backend.database import get_setting, set_setting
from backend.i18n import t, get_lang

router = APIRouter()

@router.get("/api/settings")
async def get_settings_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
        
    from backend.models import User
    from backend.database import db_session
    totp_enabled = False
    admin_username = ""
    with db_session() as session:
        user = session.query(User).first()
        if user:
            totp_enabled = (user.totp_enabled == 1)
            admin_username = user.username
            
        from backend.database import get_quick_security_rules_state
        quick_states = get_quick_security_rules_state()

        from backend.models import Inbound
        has_custom_hysteria = any(
            get_setting(f"use_custom_hysteria_config_{ib.id}") == "true"
            for ib in session.query(Inbound).filter(Inbound.enable == 1, Inbound.protocol == "hysteria2").all()
        )

        return {
            "success": True,
            "api_token": "••••••••" if settings.API_TOKEN else "",
            "secret_path": settings.PANEL_SECRET_PATH,
            "admin_username": admin_username,
            "totp_enabled": totp_enabled,
            "decoy_type": get_setting("decoy_type", "none"),
            "decoy_value": get_setting("decoy_value", "company_landing"),
            "ssl_domain": get_setting("ssl_domain", ""),
            "ssl_email": get_setting("ssl_email", ""),
            "language": get_setting("language", "ru"),
            "session_timeout_days": int(get_setting("session_timeout_days", str(settings.SESSION_TIMEOUT_DAYS))),
            "telegram_bot_token": "••••••••" if get_setting("telegram_bot_token", "") else "",
            "telegram_admin_ids": get_setting("telegram_admin_ids", ""),
            "telegram_2fa_enabled": get_setting("telegram_2fa_enabled", "false") == "true",
            "telegram_bot_enabled": get_setting("telegram_bot_enabled", "true") == "true",
            "login_max_attempts": int(get_setting("login_max_attempts", str(settings.LOGIN_MAX_ATTEMPTS))),
            "login_attempts_period": int(get_setting("login_attempts_period", str(settings.LOGIN_ATTEMPTS_PERIOD))),
            "login_fail_delay": float(get_setting("login_fail_delay", str(settings.LOGIN_FAIL_DELAY))),
            "backup_enable": get_setting("backup_enable", "false") == "true",
            "backup_interval": get_setting("backup_interval", "daily"),
            "backup_rotation": int(get_setting("backup_rotation", "7")),
            "backup_telegram": get_setting("backup_telegram", "false") == "true",
            "backup_encrypt": get_setting("backup_encrypt", "false") == "true",
            "backup_password_set": bool(get_setting("backup_password", "")),
            "block_bittorrent": quick_states.get("block_bittorrent", get_setting("block_bittorrent", "false") == "true"),
            "block_bittorrent_outbound": quick_states.get("block_bittorrent_outbound", get_setting("block_bittorrent_outbound", "blocked")),
            "block_ads": quick_states.get("block_ads", get_setting("block_ads", "false") == "true"),
            "block_ads_outbound": quick_states.get("block_ads_outbound", get_setting("block_ads_outbound", "blocked")),
            "block_cn": quick_states.get("block_cn", get_setting("block_cn", "false") == "true"),
            "block_cn_outbound": quick_states.get("block_cn_outbound", get_setting("block_cn_outbound", "blocked")),
            "block_ru": quick_states.get("block_ru", get_setting("block_ru", "false") == "true"),
            "block_ru_outbound": quick_states.get("block_ru_outbound", get_setting("block_ru_outbound", "blocked")),
            "block_us": quick_states.get("block_us", get_setting("block_us", "false") == "true"),
            "block_us_outbound": quick_states.get("block_us_outbound", get_setting("block_us_outbound", "blocked")),
            "ip_checkers": quick_states.get("ip_checkers", get_setting("ip_checkers", "false") == "true"),
            "ip_checkers_outbound": quick_states.get("ip_checkers_outbound", get_setting("ip_checkers_outbound", "direct")),
            "mux_enabled": get_setting("mux_enabled", "false") == "true",
            "mux_concurrency": int(get_setting("mux_concurrency", "8")),
            "mux_xver": get_setting("mux_xver", "0") == "1",
            "use_custom_xray_config": get_setting("use_custom_xray_config", "false"),
            "use_custom_singbox_config": get_setting("use_custom_singbox_config", "false"),
            "use_custom_hysteria_config": "true" if has_custom_hysteria else "false"
        }

@router.post("/api/settings/update")
async def update_settings_api(request: Request):
    import backend.routes.system as system_facade
    if not system_facade.check_auth(request):
        return system_facade.decoy_response()
    
    lang = get_lang(request)
    try:
        data = await request.json()
        
        # 1. Access Credentials Card
        if "secret_path" in data:
            secret_path = data.get("secret_path")
            if not secret_path or not secret_path.isalnum():
                return {"success": False, "msg": t("settings_secret_path_invalid", lang=lang, category="backend")}
            system_facade.save_settings_to_env({
                "PANEL_SECRET_PATH": secret_path,
            })
            

            
        if "session_timeout_days" in data:
            try:
                session_timeout_days = int(data.get("session_timeout_days"))
                if session_timeout_days <= 0:
                    raise ValueError()
                set_setting("session_timeout_days", str(session_timeout_days))
            except ValueError:
                return {"success": False, "msg": t("settings_session_timeout_invalid", lang=lang, category="backend")}
 
        if "login_max_attempts" in data:
            try:
                login_max_attempts = int(data.get("login_max_attempts"))
                if login_max_attempts <= 0:
                    raise ValueError()
                set_setting("login_max_attempts", str(login_max_attempts))
            except ValueError:
                return {"success": False, "msg": t("settings_login_max_attempts_invalid", lang=lang, category="backend")}
 
        if "login_attempts_period" in data:
            try:
                login_attempts_period = int(data.get("login_attempts_period"))
                if login_attempts_period <= 0:
                    raise ValueError()
                set_setting("login_attempts_period", str(login_attempts_period))
            except ValueError:
                return {"success": False, "msg": t("settings_login_attempts_period_invalid", lang=lang, category="backend")}
 
        if "login_fail_delay" in data:
            try:
                login_fail_delay = float(data.get("login_fail_delay"))
                if login_fail_delay < 0:
                    raise ValueError()
                set_setting("login_fail_delay", str(login_fail_delay))
            except ValueError:
                return {"success": False, "msg": t("settings_login_fail_delay_invalid", lang=lang, category="backend")}
 
        # 2. Telegram Integration Card
        tg_changed = False
        if "telegram_bot_token" in data or "telegram_admin_ids" in data or "telegram_2fa_enabled" in data or "telegram_bot_enabled" in data:
            old_token = get_setting("telegram_bot_token", "")
            old_admin_ids = get_setting("telegram_admin_ids", "")
            old_bot_enabled = get_setting("telegram_bot_enabled", "true")
            
            tg_bot_token = data.get("telegram_bot_token", old_token).strip()
            if tg_bot_token == "••••••••":
                tg_bot_token = old_token
            tg_admin_ids = data.get("telegram_admin_ids", old_admin_ids).strip()
            tg_bot_enabled = "true" if data.get("telegram_bot_enabled", old_bot_enabled) in (True, "true") else "false"
            
            if tg_bot_token != old_token or tg_admin_ids != old_admin_ids or tg_bot_enabled != old_bot_enabled:
                tg_changed = True
                
            set_setting("telegram_bot_token", tg_bot_token)
            set_setting("telegram_admin_ids", tg_admin_ids)
            set_setting("telegram_bot_enabled", tg_bot_enabled)
            
            if "telegram_2fa_enabled" in data:
                set_setting("telegram_2fa_enabled", "true" if data.get("telegram_2fa_enabled") in (True, "true") else "false")
            
        # 3. Decoy Site Card
        decoy_updated = False
        if "decoy_type" in data:
            decoy_type = data.get("decoy_type")
            if decoy_type not in ("none", "static", "proxy", "redirect", "drop"):
                return {"success": False, "msg": t("settings_decoy_type_invalid", lang=lang, category="backend")}
            set_setting("decoy_type", decoy_type)
            decoy_updated = True
            
        if "decoy_value" in data:
            decoy_type = data.get("decoy_type", get_setting("decoy_type", "none"))
            decoy_value = data.get("decoy_value")
            if decoy_type in ("proxy", "redirect") and not decoy_value.startswith("http"):
                return {"success": False, "msg": t("settings_decoy_url_required", lang=lang, category="backend")}
            set_setting("decoy_value", decoy_value)
            decoy_updated = True

        if decoy_updated:
            try:
                from backend.xray import restart_xray
                from backend.hysteria import restart_hysteria
                from backend.singbox import restart_singbox
                restart_xray()
                restart_hysteria()
                restart_singbox()
            except Exception as e:
                logging.error(f"Error restarting cores after decoy update: {e}")
            
        # 4. SSL Domain / Email
        if "ssl_domain" in data:
            set_setting("ssl_domain", data.get("ssl_domain"))
        if "ssl_email" in data:
            set_setting("ssl_email", data.get("ssl_email"))
 
        # 5. Backup Settings
        if "backup_enable" in data:
            set_setting("backup_enable", "true" if data.get("backup_enable") in (True, "true") else "false")
        if "backup_interval" in data:
            val = data.get("backup_interval")
            if val in ("hourly", "daily", "weekly"):
                set_setting("backup_interval", val)
        if "backup_rotation" in data:
            try:
                rot = int(data.get("backup_rotation"))
                if rot <= 0:
                    raise ValueError()
                set_setting("backup_rotation", str(rot))
                
                # Immediate rotation cleanup
                from backend.config import BASE_DIR
                backups_dir = BASE_DIR / "backups"
                if backups_dir.exists():
                    backup_files = sorted(
                        list(backups_dir.glob("backup_*.json")),
                        key=lambda x: x.stat().st_mtime
                    )
                    while len(backup_files) > rot:
                        oldest_file = backup_files.pop(0)
                        try:
                            oldest_file.unlink()
                        except Exception:
                            pass
            except ValueError:
                return {"success": False, "msg": t("settings_backup_rotation_invalid", lang=lang, category="backend")}
        if "backup_telegram" in data:
            set_setting("backup_telegram", "true" if data.get("backup_telegram") in (True, "true") else "false")
        if "backup_encrypt" in data:
            new_encrypt = "true" if data.get("backup_encrypt") in (True, "true") else "false"
            old_encrypt = get_setting("backup_encrypt", "false")
            if old_encrypt == "true" and new_encrypt == "false":
                stored_password = get_setting("backup_password", "")
                if stored_password:
                    verify_password = data.get("verify_password", "").strip()
                    if not verify_password or verify_password != stored_password:
                        return {"success": False, "msg": t("backup_current_password_incorrect", lang=lang, category="backend")}
            set_setting("backup_encrypt", new_encrypt)
 
        # 6. Quick Block Rules & Outbound Parameters (Dynamic from sentinel-core presets)
        quick_block_changed = False
        dynamic_quick_keys = [k for k in data.keys() if k.startswith("block_") or k == "ip_checkers" or k == "ip_checkers_outbound"]
        if dynamic_quick_keys:
            from backend.database import sync_quick_security_rules
            sync_quick_security_rules(data)
            for key in dynamic_quick_keys:
                if key.endswith("_outbound"):
                    set_setting(key, str(data.get(key)))
                else:
                    set_setting(key, "true" if data.get(key) in (True, "true", 1, "1") else "false")
            quick_block_changed = True
                    
        if quick_block_changed:
            from backend.xray import write_xray_config, restart_xray
            from backend.hysteria import restart_hysteria
            write_xray_config()
            restart_xray()
            restart_hysteria()
            try:
                from backend.singbox import write_singbox_config, restart_singbox
                write_singbox_config(force=True)
                restart_singbox()
            except Exception:
                pass

        # 7. Client Multiplexing (Mux) Settings
        if "mux_enabled" in data:
            set_setting("mux_enabled", "true" if data.get("mux_enabled") in (True, "true") else "false")
        if "mux_concurrency" in data:
            try:
                concurrency = int(data.get("mux_concurrency"))
                if concurrency <= 0:
                    raise ValueError()
                set_setting("mux_concurrency", str(concurrency))
            except ValueError:
                return {"success": False, "msg": t("invalid_mux_concurrency", lang=lang, category="backend")}
        if "mux_xver" in data:
            set_setting("mux_xver", "1" if data.get("mux_xver") in (True, "true", "1", 1) else "0")

        # Log action
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "update_settings", target="general", details=f"Keys: {list(data.keys())}")
        
        # Trigger Telegram bot restart if settings changed
        if tg_changed:
            from backend.bot_manager import restart_telegram_bot
            restart_telegram_bot()
            
        return {
            "success": True,
            "obj": None,
            "msg": t("settings_saved_success", lang=lang, category="backend")
        }
    except Exception as e:
        return {"success": False, "msg": t("settings_save_error", lang=lang, category="backend", error=str(e))}

@router.get("/api/locales")
async def get_locales_list_api(request: Request):
    # Public endpoint — only returns a list of available language codes.
    # No sensitive data; accessible before login so the UI can load i18n.
    from backend.i18n import get_available_languages
    return {
        "success": True,
        "obj": get_available_languages()
    }

@router.get("/api/locales/{lang}")
async def get_locale_dict_api(request: Request, lang: str):
    # Public endpoint — only returns frontend UI translation strings.
    # No sensitive data; accessible before login so the login page renders correctly.
    from backend.i18n import _translations
    lang_lower = lang.lower()
    lang_data = _translations.get(lang_lower)

    # Fallback to English if requested is not found, then Russian
    if not lang_data:
        lang_data = _translations.get("en", _translations.get("ru", {}))

    frontend_translations = lang_data.get("frontend", {})
    return {
        "success": True,
        "obj": frontend_translations
    }
