import os
import sys
import logging
import asyncio
import time
import datetime
from aiogram import Bot, Dispatcher, html, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, BufferedInputFile, InputMediaPhoto, CallbackQuery
from aiogram.filters import CommandStart, Command
from pathlib import Path

# Добавляем корневую папку в sys.path, чтобы импортировать config и i18n
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

try:
    from backend.config import settings
except ImportError:
    class MockSettings:
        PANEL_PORT = 2053
        PANEL_SECRET_PATH = "ui"
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        TELEGRAM_ADMIN_IDS = os.getenv("TELEGRAM_ADMIN_IDS", "")
    settings = MockSettings()

from backend.i18n import t

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def generate_qr_code_png(data: str) -> bytes:
    import io
    import qrcode
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# Получение публичного IP-адреса сервера
async def get_public_ip():
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.ipify.org?format=json", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    res_json = await response.json()
                    return res_json.get("ip", "127.0.0.1")
    except Exception as e:
        logging.warning(f"Could not determine public IP: {e}")
    return "127.0.0.1"

# Проверка белого списка администраторов
def is_admin(user_id: int) -> bool:
    try:
        from backend.database import get_setting
        tg_admin_ids = get_setting("telegram_admin_ids", "")
    except Exception:
        tg_admin_ids = ""
    allowed_ids = [x.strip() for x in tg_admin_ids.split(",") if x.strip()]
    if not allowed_ids:
        return False
    return str(user_id) in allowed_ids

# Инициализация бота
try:
    from backend.database import get_setting
    bot_token = get_setting("telegram_bot_token", "")
    bot_enabled = get_setting("telegram_bot_enabled", "true") == "true"
except Exception:
    bot_token = ""
    bot_enabled = True

if not bot_token:
    logging.warning("TELEGRAM_BOT_TOKEN не задан ни в БД, ни в .env. Бот не запустится.")
    bot = None
    dp = None
elif not bot_enabled:
    logging.warning("Встроенный Telegram-бот отключен в настройках. Бот не запустится.")
    bot = None
    dp = None
else:
    bot = Bot(token=bot_token)
    dp = Dispatcher()

# Обработчики
if dp:
    @dp.message(CommandStart())
    @dp.message(Command("panel"))
    async def cmd_start(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied", lang, "bot"))
            logging.warning(f"Unauthorized Telegram access attempt from ID {user_id}")
            return
            
        public_ip = await get_public_ip()
        port = settings.PANEL_PORT
        secret_path = settings.PANEL_SECRET_PATH
        
        from backend.database import get_setting
        from backend.ssl_utils import SSL_CERT_PATH, SSL_KEY_PATH
        
        ssl_domain = get_setting("ssl_domain", "")
        has_ssl = SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists()
        
        host = ssl_domain if ssl_domain else public_ip
        scheme = "https" if (ssl_domain or has_ssl or port == 443) else "http"
        
        if (port == 443 and scheme == "https") or (port == 80 and scheme == "http"):
            webapp_url = f"{scheme}://{host}/{secret_path}/"
        else:
            webapp_url = f"{scheme}://{host}:{port}/{secret_path}/"
            
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_open_webapp", lang, "bot"), 
                    web_app=WebAppInfo(url=webapp_url)
                )
            ]
        ])
        
        await message.reply(
            t("welcome_admin", lang, "bot", name=html.escape(message.from_user.full_name)),
            reply_markup=markup,
            parse_mode="HTML"
        )

    @dp.message(Command("backup"))
    async def cmd_backup(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        try:
            from backend.backup import create_backup_dump
            dump_data = create_backup_dump()
            
            file_data = dump_data.encode("utf-8")
            document = BufferedInputFile(file_data, filename=f"vpn_backup_{int(time.time())}.json")
            await message.reply_document(document, caption=t("backup_sent", lang, "bot"))
        except Exception as e:
            logging.error(f"Failed to create backup via bot: {e}")
            await message.reply(t("backup_error", lang, "bot", error=str(e)))

    @dp.message(Command("status"))
    async def cmd_status(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        try:
            from backend.host_client import host_client
            stats = host_client.send_command("get_system_stats")
            
            from backend.database import db_session
            from backend.models import ClientStats, Inbound
            
            with db_session() as session:
                total_inbounds = session.query(Inbound).count()
                total_clients = session.query(ClientStats).count()
                active_clients = session.query(ClientStats).filter_by(enable=1).count()
                blocked_clients = total_clients - active_clients
                
            cpu = stats.get("cpu", 0.0)
            mem = stats.get("mem", {})
            mem_curr = mem.get("current", 0) / (1024**3)
            mem_tot = mem.get("total", 0) / (1024**3)
            uptime = stats.get("uptime", 0)
            
            # Аптайм перевод
            days = uptime // 86400
            hours = (uptime % 86400) // 3600
            minutes = (uptime % 3600) // 60
            
            uptime_days_unit = t("uptime_days", lang, "bot")
            uptime_hours_unit = t("uptime_hours", lang, "bot")
            uptime_minutes_unit = t("uptime_minutes", lang, "bot")
            uptime_str = f"{days}{uptime_days_unit} {hours}{uptime_hours_unit} {minutes}{uptime_minutes_unit}"
            
            msg = (
                f"📊 <b>{t('status_title', lang, 'bot')}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🖥️ {t('status_cpu', lang, 'bot')}: <b>{cpu}%</b>\n"
                f"💾 {t('status_memory', lang, 'bot')}: <b>{mem_curr:.2f} GB / {mem_tot:.2f} GB</b>\n"
                f"⏱ {t('status_uptime', lang, 'bot')}: <b>{uptime_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🖧 {t('status_inbounds', lang, 'bot')}: <b>{total_inbounds}</b>\n"
                f"👥 {t('status_total_clients', lang, 'bot')}: <b>{total_clients}</b>\n"
                f"🟢 {t('status_active_clients', lang, 'bot')}: <b>{active_clients}</b>\n"
                f"🔴 {t('status_blocked_clients', lang, 'bot')}: <b>{blocked_clients}</b>"
            )
            await message.reply(msg, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to get status via bot: {e}")
            await message.reply(t("status_error", lang, "bot", error=str(e)))

    @dp.message(Command("my"))
    async def cmd_my(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply(t("my_help", lang, "bot"), parse_mode="HTML")
            return
            
        search_key = args[1].strip()
        
        try:
            from backend.database import db_session
            from backend.models import ClientStats, Inbound
            from backend.links_generator import get_client_links
            
            found_clients = []
            with db_session() as session:
                clients = session.query(ClientStats).filter(
                    (ClientStats.email == search_key) | (ClientStats.client_uuid_or_pwd == search_key)
                ).all()
                for c in clients:
                    ib = session.query(Inbound).filter_by(id=c.inbound_id).first()
                    if ib:
                        c_dict = {
                            "id": c.id, "inbound_id": c.inbound_id, "email": c.email,
                            "client_uuid_or_pwd": c.client_uuid_or_pwd, "up": c.up, "down": c.down,
                            "total": c.total, "expiry_time": c.expiry_time, "enable": c.enable,
                            "limit_ip": c.limit_ip, "block_reason": c.block_reason or ""
                        }
                        ib_dict = {
                            "id": ib.id, "remark": ib.remark, "port": ib.port, "protocol": ib.protocol,
                            "settings": ib.settings, "stream_settings": ib.stream_settings, "sniffing": ib.sniffing,
                            "enable": ib.enable, "up": ib.up, "down": ib.down, "total": ib.total, "expiry_time": ib.expiry_time
                        }
                        found_clients.append((ib_dict, c_dict))
                        
            if not found_clients:
                await message.reply(t("my_not_found", lang, "bot"))
                return
                
            public_ip = await get_public_ip()
            port = settings.PANEL_PORT
            base_url = f"http://{public_ip}:{port}"
            
            for ib, c in found_clients:
                up_gb = c["up"] / (1024**3)
                down_gb = c["down"] / (1024**3)
                total_gb = c["total"] / (1024**3) if c["total"] > 0 else t("unlimited", lang, "bot")
                total_gb_str = f"{total_gb:.2f} GB" if isinstance(total_gb, float) else total_gb
                
                if c["enable"] == 1:
                    status_str = f"🟢 {t('active', lang, 'bot')}"
                else:
                    reason = c['block_reason'] or t('limits_exceeded', lang, 'bot')
                    status_str = f"🔴 {t('blocked', lang, 'bot')} ({reason})"
                
                exp_str = t("never_expires", lang, "bot")
                if c["expiry_time"] > 0:
                    dt = datetime.datetime.fromtimestamp(c["expiry_time"] / 1000)
                    exp_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    
                msg = (
                    f"🔑 <b>{t('sub_title', lang, 'bot', email=html.escape(c['email']))}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 {t('sub_inbound', lang, 'bot')}: <b>{ib['remark']} (:{ib['port']})</b>\n"
                    f"📡 {t('sub_proto', lang, 'bot')}: <b>{ib['protocol'].upper()}</b>\n"
                    f"🚦 {t('sub_downloaded', lang, 'bot')}: <b>{down_gb:.3f} GB</b>\n"
                    f"📤 {t('sub_uploaded', lang, 'bot')}: <b>{up_gb:.3f} GB</b>\n"
                    f"💾 {t('sub_limit', lang, 'bot')}: <b>{total_gb_str}</b>\n"
                    f"⏱ {t('sub_expires', lang, 'bot')}: <b>{exp_str}</b>\n"
                    f"⚡ {t('sub_status', lang, 'bot')}: <b>{status_str}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔗 {t('sub_keys', lang, 'bot')}\n"
                )
                
                links = get_client_links(ib, c, base_url)
                for link in links:
                    msg += f"<code>{html.escape(link)}</code>\n\n"
                    
                msg += f"{t('sub_click_to_copy', lang, 'bot')}"
                await message.reply(msg, parse_mode="HTML")
                
                # Генерируем и отправляем QR-коды медиагруппой
                media_group = []
                for idx, link in enumerate(links):
                    try:
                        qr_bytes = generate_qr_code_png(link)
                        photo_file = BufferedInputFile(qr_bytes, filename=f"qr_{idx}.png")
                        proto_name = link.split("://")[0].upper() if "://" in link else "VPN"
                        caption = f"QR-код {proto_name} ({idx+1})"
                        media_group.append(InputMediaPhoto(media=photo_file, caption=caption))
                    except Exception as qr_err:
                        logging.error(f"Error generating QR code in mini_bot: {qr_err}")
                
                if media_group:
                    try:
                        await message.answer_media_group(media=media_group)
                    except Exception as send_err:
                        logging.error(f"Error sending QR media group in mini_bot: {send_err}")
                
        except Exception as e:
            logging.error(f"Error checking sub info in bot: {e}")
            await message.reply(t("my_error", lang, "bot", error=str(e)))

    @dp.message(Command("ban"))
    async def cmd_ban(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.reply(t("ban_help", lang, "bot"), parse_mode="HTML")
            return
            
        email = args[1].strip()
        reason = args[2].strip() if len(args) > 2 else "Blocked via Telegram Bot"
        
        try:
            from backend.database import db_session
            from backend.models import ClientStats, Inbound
            from backend.xray import restart_xray, remove_client_api
            from backend.hysteria import restart_hysteria, kick_client_hysteria_api
            import json
            
            disabled_count = 0
            with db_session() as session:
                clients = session.query(ClientStats).filter_by(email=email).all()
                for c in clients:
                    if c.enable == 1:
                        c.enable = 0
                        c.block_reason = reason
                        ib_id = c.inbound_id
                        
                        inbound = session.query(Inbound).filter_by(id=ib_id).first()
                        if inbound:
                            try:
                                ib_settings = json.loads(inbound.settings or "{}")
                                ib_clients = ib_settings.get("clients", [])
                                for sc in ib_clients:
                                    if sc.get("email") == email:
                                        sc["enable"] = False
                                        break
                                inbound.settings = json.dumps(ib_settings)
                            except Exception as e:
                                logging.error(f"Error updating inbound settings JSON: {e}")
                                
                            if inbound.protocol == "hysteria2":
                                try:
                                    kick_client_hysteria_api(ib_id, email)
                                except Exception as e:
                                    logging.error(f"Failed to kick Hysteria2 client: {e}")
                            else:
                                try:
                                    remove_client_api(ib_id, email)
                                except Exception as e:
                                    logging.error(f"Failed to remove Xray client: {e}")
                                    
                        disabled_count += 1
                session.commit()
                
            if disabled_count > 0:
                restart_xray()
                restart_hysteria()
                await message.reply(t("ban_success", lang, "bot", email=email, reason=reason), parse_mode="HTML")
            else:
                await message.reply(t("ban_error", lang, "bot", error="Client not found or already blocked"))
        except Exception as e:
            logging.error(f"Error banning via bot: {e}")
            await message.reply(t("ban_error", lang, "bot", error=str(e)))

    @dp.message(Command("unban"))
    async def cmd_unban(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply(t("unban_help", lang, "bot"), parse_mode="HTML")
            return
            
        email = args[1].strip()
        
        try:
            from backend.database import db_session
            from backend.models import ClientStats, Inbound
            from backend.xray import restart_xray
            from backend.hysteria import restart_hysteria
            import json
            
            enabled_count = 0
            with db_session() as session:
                clients = session.query(ClientStats).filter_by(email=email).all()
                for c in clients:
                    if c.enable == 0:
                        c.enable = 1
                        c.block_reason = None
                        ib_id = c.inbound_id
                        
                        inbound = session.query(Inbound).filter_by(id=ib_id).first()
                        if inbound:
                            try:
                                ib_settings = json.loads(inbound.settings or "{}")
                                ib_clients = ib_settings.get("clients", [])
                                for sc in ib_clients:
                                    if sc.get("email") == email:
                                        sc["enable"] = True
                                        break
                                inbound.settings = json.dumps(ib_settings)
                            except Exception as e:
                                logging.error(f"Error updating inbound settings JSON: {e}")
                                
                        enabled_count += 1
                session.commit()
                
            if enabled_count > 0:
                restart_xray()
                restart_hysteria()
                await message.reply(t("unban_success", lang, "bot", email=email), parse_mode="HTML")
            else:
                await message.reply(t("unban_error", lang, "bot", error="Client not found or already active"))
        except Exception as e:
            logging.error(f"Error unbanning via bot: {e}")
            await message.reply(t("unban_error", lang, "bot", error=str(e)))

    @dp.message(Command("top"))
    async def cmd_top(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        args = message.text.split(maxsplit=1)
        period = "today"
        if len(args) > 1 and args[1].strip().lower() in ["month", "месяц"]:
            period = "month"
            
        try:
            from backend.database import db_session
            from backend.models import ClientTrafficDaily
            from sqlalchemy import func
            import datetime
            
            today_str = datetime.date.today().isoformat()
            month_prefix = datetime.date.today().strftime("%Y-%m-%")
            
            with db_session() as session:
                if period == "today":
                    records = session.query(
                        ClientTrafficDaily.email,
                        ClientTrafficDaily.up,
                        ClientTrafficDaily.down
                    ).filter(ClientTrafficDaily.date == today_str).all()
                else:
                    records = session.query(
                        ClientTrafficDaily.email,
                        func.sum(ClientTrafficDaily.up).label("up"),
                        func.sum(ClientTrafficDaily.down).label("down")
                    ).filter(ClientTrafficDaily.date.like(month_prefix)).group_by(ClientTrafficDaily.email).all()
                    
            result = []
            for r in records:
                up_val = int(r.up or 0)
                down_val = int(r.down or 0)
                result.append({
                    "email": r.email,
                    "total": up_val + down_val
                })
                
            result.sort(key=lambda x: x["total"], reverse=True)
            top_list = result[:10]
            
            title = "🏆 <b>Топ потребителей трафика (Сегодня)</b>" if period == "today" else "🏆 <b>Топ потребителей трафика (За месяц)</b>"
            msg = f"{title}\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            if not top_list:
                msg += "Нет данных по активности пользователей за этот период."
            else:
                for idx, item in enumerate(top_list, 1):
                    gb = item["total"] / (1024**3)
                    msg += f"{idx}. 👤 <code>{html.escape(item['email'])}</code>: <b>{gb:.3f} GB</b>\n"
            
            msg += "\n<i>Для переключения используйте: <code>/top today</code> или <code>/top month</code></i>"
            await message.reply(msg, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Error getting top traffic: {e}")
            await message.reply(f"❌ Ошибка при получении статистики: {e}")

    @dp.message(Command("audit", "logs"))
    async def cmd_audit(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        try:
            from backend.database import db_session
            from backend.models import AuditLog
            
            with db_session() as session:
                logs = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10).all()
                
            if not logs:
                await message.reply("📁 Лог аудита пуст.")
                return
                
            msg = "📋 <b>Последние действия в панели:</b>\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            for log in logs:
                dt = datetime.datetime.fromtimestamp(log.timestamp)
                time_str = dt.strftime("%d.%m %H:%M:%S")
                target_str = f" ➔ <code>{html.escape(log.target)}</code>" if log.target else ""
                details_str = f" (<i>{html.escape(log.details)}</i>)" if log.details else ""
                
                msg += f"🕒 <code>{time_str}</code> | 👤 <b>{html.escape(log.username)}</b>\n"
                msg += f"⚙️ <code>{html.escape(log.action)}</code>{target_str}{details_str}\n"
                msg += "────────────────────────\n"
                
            await message.reply(msg, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Failed to get audit logs via bot: {e}")
    @dp.message(Command("allow_ip"))
    async def cmd_allow_ip(message: Message):
        user_id = message.from_user.id
        lang = message.from_user.language_code or "ru"
        if not is_admin(user_id):
            await message.reply(t("access_denied_general", lang, "bot"))
            return
            
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.reply("<b>Использование:</b> <code>/allow_ip &lt;email&gt; &lt;ip&gt;</code>\nПример: <code>/allow_ip Den_double_v2 198.51.100.1</code>\nДля сброса: <code>/allow_ip Den_double_v2 clear</code>", parse_mode="HTML")
            return
            
        email = args[1].strip()
        ip_arg = args[2].strip() if len(args) > 2 else ""
        
        try:
            from backend.database import db_session
            from backend.models import ClientStats
            from backend.audit import log_action
            
            with db_session() as session:
                clients = session.query(ClientStats).filter_by(email=email).all()
                if not clients:
                    await message.reply(f"❌ Клиент <code>{email}</code> не найден.", parse_mode="HTML")
                    return
                    
                if ip_arg.lower() in ("clear", "reset", "all", "0", ""):
                    for c in clients:
                        c.allowed_ips = ""
                    new_allowed = "любые (очищено)"
                else:
                    for c in clients:
                        cur = [x.strip() for x in (c.allowed_ips or "").split(",") if x.strip()]
                        if ip_arg not in cur:
                            cur.append(ip_arg)
                        c.allowed_ips = ", ".join(cur)
                    new_allowed = clients[0].allowed_ips

            log_action("bot", "allow_ip", target=email, details=f"Set allowed_ips to {new_allowed} via telegram bot command")
            await message.reply(f"✅ <b>Обновлен список разрешенных IP для <code>{email}</code>:</b>\n<code>{new_allowed}</code>", parse_mode="HTML")
        except Exception as e:
            logging.error(f"Error executing allow_ip command: {e}")
            await message.reply(f"❌ Ошибка: {e}")

    @dp.callback_query(F.data.startswith("tg_allow_ip:"))
    async def cb_tg_allow_ip(callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = callback.from_user.language_code or "ru"
        if not is_admin(user_id):
            await callback.answer(t("access_denied_general", lang, "bot"), show_alert=True)
            return

        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("Ошибка формата", show_alert=True)
            return
        email = parts[1]
        ip = parts[2]

        try:
            from backend.database import db_session
            from backend.models import ClientStats
            from backend.audit import log_action

            new_allowed = ""
            with db_session() as session:
                clients = session.query(ClientStats).filter_by(email=email).all()
                if not clients:
                    await callback.answer("Клиент не найден", show_alert=True)
                    return

                for c in clients:
                    cur = [x.strip() for x in (c.allowed_ips or "").split(",") if x.strip()]
                    if ip not in cur:
                        cur.append(ip)
                    c.allowed_ips = ", ".join(cur)
                    new_allowed = c.allowed_ips

            log_action("bot", "allow_ip", target=email, details=f"Allowed IP {ip} via security alert callback button")
            await callback.message.edit_text(callback.message.html_text + f"\n\n✅ <b>IP {ip} добавлен в список разрешенных для клиента <code>{email}</code>.</b>\nТекущий список: <code>{new_allowed}</code>", parse_mode="HTML")
            await callback.answer(f"IP {ip} одобрен!", show_alert=False)
        except Exception as e:
            logging.error(f"Error approving IP via callback: {e}")
            await callback.answer(f"Ошибка: {e}", show_alert=True)

    @dp.callback_query(F.data.startswith("tg_block_client:"))
    async def cb_tg_block_client(callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = callback.from_user.language_code or "ru"
        if not is_admin(user_id):
            await callback.answer(t("access_denied_general", lang, "bot"), show_alert=True)
            return

        parts = callback.data.split(":", 1)
        if len(parts) < 2:
            await callback.answer("Ошибка формата", show_alert=True)
            return
        email = parts[1]

        try:
            from backend.database import db_session
            from backend.models import ClientStats
            from backend.hysteria import kick_client_hysteria_api
            from backend.xray import remove_client_api
            from backend.audit import log_action

            with db_session() as session:
                clients = session.query(ClientStats).filter_by(email=email).all()
                if not clients:
                    await callback.answer("Клиент не найден", show_alert=True)
                    return

                for c in clients:
                    c.enable = 0
                    c.block_reason = "Заблокирован через Telegram бота (security alert)"
                    ib_id = c.inbound_id
                    try:
                        kick_client_hysteria_api(ib_id, email)
                    except Exception:
                        pass
                    try:
                        remove_client_api(ib_id, email)
                    except Exception:
                        pass

            log_action("bot", "block_client", target=email, details="Blocked client via telegram security alert callback")
            await callback.message.edit_text(callback.message.html_text + f"\n\n🔴 <b>Клиент <code>{email}</code> полностью заблокирован.</b>", parse_mode="HTML")
            await callback.answer("Клиент заблокирован", show_alert=False)
        except Exception as e:
            logging.error(f"Error blocking client via callback: {e}")
            await callback.answer(f"Ошибка: {e}", show_alert=True)

    @dp.callback_query(F.data.startswith("tg_2fa_approve:"))
    async def cb_tg_2fa_approve(callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = callback.from_user.language_code or "ru"
        if not is_admin(user_id):
            await callback.answer(t("access_denied_general", lang, "bot"), show_alert=True)
            return

        token = callback.data.split(":", 1)[1]
        import aiohttp
        url = f"http://127.0.0.1:{settings.PANEL_PORT}/api/auth/tg-2fa/action"
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {settings.API_TOKEN}"}
                async with session.post(url, json={"token": token, "action": "approve"}, headers=headers) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if res.get("success"):
                            await callback.message.edit_text(f"✅ <b>Вход разрешен.</b>", parse_mode="HTML")
                        else:
                            await callback.answer(f"❌ Ошибка: {res.get('msg')}", show_alert=True)
                    else:
                        await callback.answer(f"❌ Ошибка HTTP {resp.status}", show_alert=True)
        except Exception as e:
            logging.error(f"Error approving tg 2fa: {e}")
            await callback.answer(f"❌ Ошибка соединения: {e}", show_alert=True)

    @dp.callback_query(F.data.startswith("tg_2fa_block:"))
    async def cb_tg_2fa_block(callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = callback.from_user.language_code or "ru"
        if not is_admin(user_id):
            await callback.answer(t("access_denied_general", lang, "bot"), show_alert=True)
            return

        parts = callback.data.split(":", 1)
        token = parts[1]
        
        import aiohttp
        url = f"http://127.0.0.1:{settings.PANEL_PORT}/api/auth/tg-2fa/action"
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {settings.API_TOKEN}"}
                async with session.post(url, json={"token": token, "action": "block"}, headers=headers) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        if res.get("success"):
                            await callback.message.edit_text("🛑 <b>IP-адрес заблокирован.</b>", parse_mode="HTML")
                        else:
                            await callback.answer(f"❌ Ошибка: {res.get('msg')}", show_alert=True)
                    else:
                        await callback.answer(f"❌ Ошибка HTTP {resp.status}", show_alert=True)
        except Exception as e:
            logging.error(f"Error blocking ip tg 2fa: {e}")
            await callback.answer(f"❌ Ошибка соединения: {e}", show_alert=True)

    @dp.callback_query(F.data.startswith("panel_term_sess:"))
    async def cb_panel_term_sess(callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = callback.from_user.language_code or "ru"
        if not is_admin(user_id):
            await callback.answer(t("access_denied_general", lang, "bot"), show_alert=True)
            return

        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("Ошибка формата данных", show_alert=True)
            return
        username = parts[1]
        ip = parts[2]

        try:
            from backend.database import get_all_sessions_db, delete_session_db
            from backend.auth_utils import ACTIVE_SESSIONS, CSRF_TOKENS
            from backend.audit import log_action
            
            sessions = get_all_sessions_db()
            terminated = 0
            for s in sessions:
                if s["username"] == username and (s["ip_address"] == ip or ip == "unknown" or not ip):
                    delete_session_db(s["session_id"])
                    ACTIVE_SESSIONS.discard(s["session_id"])
                    CSRF_TOKENS.pop(s["session_id"], None)
                    terminated += 1
            
            if terminated > 0:
                log_action("bot", "terminate_session", target=username, details=f"Terminated {terminated} sessions for IP {ip}")
                await callback.message.edit_text(callback.message.html_text + f"\n\n❌ <b>Сессии пользователя {username} с IP {ip} успешно сброшены ({terminated} сесс.).</b>", parse_mode="HTML")
                await callback.answer("Сессии успешно сброшены", show_alert=False)
            else:
                await callback.answer("Активные сессии не найдены", show_alert=True)
        except Exception as e:
            logging.error(f"Error terminating session via bot: {e}")
            await callback.answer(f"Ошибка: {e}", show_alert=True)

    @dp.callback_query(F.data.startswith("panel_reset_pwd:"))
    async def cb_panel_reset_pwd(callback: CallbackQuery):
        user_id = callback.from_user.id
        lang = callback.from_user.language_code or "ru"
        if not is_admin(user_id):
            await callback.answer(t("access_denied_general", lang, "bot"), show_alert=True)
            return

        parts = callback.data.split(":", 1)
        if len(parts) < 2:
            await callback.answer("Ошибка формата данных", show_alert=True)
            return
        username = parts[1]

        try:
            import secrets
            import string
            from backend.database.crud.auth import update_admin_password
            from backend.audit import log_action
            
            alphabet = string.ascii_letters + string.digits + "!@#$%&*+?="
            new_pwd = "".join(secrets.choice(alphabet) for _ in range(16))
            
            success = update_admin_password(username, new_pwd)
            if success:
                log_action("bot", "change_password", target=username, details="Admin password reset via telegram bot callback")
                await callback.message.edit_text(callback.message.html_text + f"\n\n🔑 <b>Пароль пользователя {username} успешно изменен!</b>\nНовый пароль: <tg-spoiler><code>{new_pwd}</code></tg-spoiler>", parse_mode="HTML")
                await callback.answer("Пароль успешно изменен", show_alert=False)
            else:
                await callback.answer("Пользователь не найден", show_alert=True)
        except Exception as e:
            logging.error(f"Error resetting password via bot: {e}")
            await callback.answer(f"Ошибка: {e}", show_alert=True)


async def main():
    if not bot:
        print("Telegram Bot Token не задан. Бот запущен не будет.")
        return
        
    logging.info("Starting Telegram Mini Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped.")
