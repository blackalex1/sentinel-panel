import asyncio
import logging
import httpx
from backend.database import get_setting
from backend.alerts.geoip import get_geoip_info

async def async_send_telegram_alert(username: str, action: str, target: str, details: str):
    """Formats and sends a Telegram alert to admins."""
    if get_setting("telegram_bot_enabled", "true") != "true":
        return
    bot_token = get_setting("telegram_bot_token", "")
    admin_ids_str = get_setting("telegram_admin_ids", "")
    if not bot_token or not admin_ids_str:
        return
        
    admin_ids = [x.strip() for x in admin_ids_str.split(",") if x.strip()]
    if not admin_ids:
        return

    text = ""
    reply_markup = None
    if action in ("login_success", "login_telegram_success"):
        geoip = await get_geoip_info(target)
        emoji = "🟢" if action == "login_success" else "🔵"
        auth_type = "Пароль" if action == "login_success" else "Telegram WebApp"
        text = (
            f"{emoji} <b>Успешный вход в панель!</b>\n\n"
            f"👤 Пользователь: <code>{username}</code>\n"
            f"🌐 IP: <code>{target}</code>\n"
            f"🗺️ Гео: <b>{geoip}</b>\n"
            f"🔑 Метод: <i>{auth_type}</i>"
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "❌ Сбросить сессию", "callback_data": f"panel_term_sess:{username}:{target}"},
                    {"text": "🔑 Сбросить пароль", "callback_data": f"panel_reset_pwd:{username}"}
                ]
            ]
        }
    elif action == "login_rate_limited":
        text = (
            f"⚠️ <b>Внимание: Обнаружен Brute-force!</b>\n\n"
            f"🔴 IP <code>{target}</code> временно заблокирован из-за превынения лимита попыток входа.\n"
            f"ℹ️ Детали: <i>{details}</i>"
        )
        
    if not text:
        return
        
    async with httpx.AsyncClient(timeout=5.0) as client:
        for admin_id in admin_ids:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": admin_id,
                    "text": text,
                    "parse_mode": "HTML"
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                await client.post(url, json=payload)
            except Exception as e:
                logging.error(f"[Telegram Alert] Не удалось отправить сообщение администратору {admin_id}: {e}")

def trigger_telegram_alert(username: str, action: str, target: str = None, details: str = None):
    """Starts the Telegram alert sending process in a background task."""
    client_actions = (
        "xray_connect", "xray_disconnect",
        "hysteria_connect", "hysteria_disconnect",
        "hysteria2_connect", "hysteria2_disconnect",
        "singbox_connect", "singbox_disconnect"
    )
    if action not in ("login_success", "login_telegram_success", "login_rate_limited") and action not in client_actions:
        return
    try:
        loop = asyncio.get_running_loop()
        if action in client_actions:
            from backend.alerts.client_connections import handle_client_event
            loop.create_task(handle_client_event(action, target, details))
        else:
            loop.create_task(async_send_telegram_alert(username, action, target, details))
    except RuntimeError:
        pass

async def _send_alert_to_all_admins(text: str):
    """Sends a generic HTML message to all administrators."""
    if get_setting("telegram_bot_enabled", "true") != "true":
        return
    bot_token = get_setting("telegram_bot_token", "")
    admin_ids_str = get_setting("telegram_admin_ids", "")
    if not bot_token or not admin_ids_str:
        return
        
    admin_ids = [x.strip() for x in admin_ids_str.split(",") if x.strip()]
    if not admin_ids:
        return

    async with httpx.AsyncClient(timeout=5.0) as client:
        for admin_id in admin_ids:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": admin_id,
                    "text": text,
                    "parse_mode": "HTML"
                }
                await client.post(url, json=payload)
            except Exception as e:
                logging.error(f"[Telegram Alert] Не удалось отправить сообщение администратору {admin_id}: {e}")

def trigger_investigation_result_alert(culprit: str, tunnel: str, node_id: str, details: str):
    """Telegram alert: edge node completed investigation."""
    text = (
        f"`✅` <b>[IPS: Расследование от Edge-ноды завершено]</b>\n\n"
        f"🔍 Нода: <code>{node_id}</code>\n"
        f"👤 Нарушитель заблокирован глобально: <code>{culprit}</code>\n"
        f"🔓 Инбаунд/туннель разблокирован: <code>{tunnel}</code>\n"
        f"📋 Детали: <i>{details}</i>"
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_alert_to_all_admins(text))
    except RuntimeError:
        pass

def trigger_investigation_failed_alert(tunnel: str, node_id: str, details: str):
    """Telegram alert: edge node investigation failed."""
    text = (
        f"⚠️ <b>[IPS: Расследование не удалось (Edge-нода)]</b>\n\n"
        f"🔍 Нода: <code>{node_id}</code>\n"
        f"🚨 Инбаунд оставлен в бане: <code>{tunnel}</code>\n"
        f"📋 Детали: <i>{details}</i>\n\n"
        f"👇 <b>Разблокируйте инбаунд вручную</b>, когда проведёте расследование самостоятельно."
    )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_alert_to_all_admins(text))
    except RuntimeError:
        pass

REJECTED_ALERT_CACHE = {}

async def async_send_ip_rejected_alert(email: str, client_ip: str, allowed_ips: str):
    """Sends a Telegram alert with 'Approve IP' button when an unallowed IP tries to connect."""
    if get_setting("telegram_bot_enabled", "true") != "true":
        return
    bot_token = get_setting("telegram_bot_token", "")
    admin_ids_str = get_setting("telegram_admin_ids", "")
    if not bot_token or not admin_ids_str:
        return

    admin_ids = [x.strip() for x in admin_ids_str.split(",") if x.strip()]
    if not admin_ids:
        return

    import time
    cache_key = f"{email}:{client_ip}"
    now_ts = time.time()
    if cache_key in REJECTED_ALERT_CACHE and (now_ts - REJECTED_ALERT_CACHE[cache_key]) < 60:
        return
    REJECTED_ALERT_CACHE[cache_key] = now_ts

    geoip = await get_geoip_info(client_ip)
    text = (
        f"⚠️ <b>[Hysteria 2: Отклонено подключение по IP]</b>\n\n"
        f"👤 Клиент: <code>{email}</code>\n"
        f"🔴 Отклоненный IP: <code>{client_ip}</code>\n"
        f"🗺️ Гео: <b>{geoip}</b>\n"
        f"🟢 Вайтлист клиента: <code>{allowed_ips or 'Не задан'}</code>\n\n"
        f"👇 <b>Одобрить этот IP для пользователя {email}?</b>"
    )
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": f"✅ Разрешить IP ({client_ip})", "callback_data": f"tg_allow_ip:{email}:{client_ip}"}
            ]
        ]
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        for admin_id in admin_ids:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": admin_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup
                }
                await client.post(url, json=payload)
            except Exception as e:
                logging.error(f"[Telegram Alert] Failed to send IP rejected alert for {email}: {e}")

def trigger_ip_rejected_alert(email: str, client_ip: str, allowed_ips: str):
    """Starts the IP rejected Telegram alert task in background."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(async_send_ip_rejected_alert(email, client_ip, allowed_ips))
    except RuntimeError:
        pass

