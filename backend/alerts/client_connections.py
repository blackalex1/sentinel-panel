import time
import datetime
import logging
import json
import httpx
from backend.database import get_setting
from backend.alerts.geoip import get_server_ip

active_activity_cards = {}

def format_card_msg(host_ip, username, protocol, lines, tx, rx):
    displayed_lines = lines[-15:]
    timeline = "\n".join(displayed_lines)
    if len(lines) > 15:
        timeline = "<i>... показать ещё ...</i>\n" + timeline
        
    def format_bytes(b):
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.2f} KB"
        elif b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.2f} MB"
        else:
            return f"{b / (1024 * 1024 * 1024):.2f} GB"
            
    download = format_bytes(tx)
    upload = format_bytes(rx)
    traffic_str = f"📥 <b>Скачано:</b> <code>{download}</code> | 📤 <b>Загружено:</b> <code>{upload}</code>\n\n"
    
    text = (
        f"📊 <b>[{protocol}: {host_ip}] Активность сессии</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь:</b> <code>{username}</code>\n\n"
        f"{traffic_str}"
        f"📋 <b>Хронология событий:</b>\n"
        f"{timeline}"
    )
    return text

def is_card_active(card, now_time):
    if not card:
        return False
    has_active = False
    for ip, conns in card.get('connections', {}).items():
        if conns:
            has_active = True
            break
    if has_active:
        return True
    last_act = card.get('last_activity_at', card.get('started_at', now_time))
    return now_time - last_act < 900.0

def check_new_ip_and_get_history(username, current_ip, current_timestamp, logs, allowed_ips=None):
    if allowed_ips:
        if isinstance(allowed_ips, str):
            allowed_list = [x.strip() for x in allowed_ips.split(",") if x.strip()]
        else:
            allowed_list = [str(x).strip() for x in allowed_ips if str(x).strip()]
        if current_ip in allowed_list:
            return False, []
            
    user_logs = []
    for log in logs:
        details_dict = {}
        try:
            if isinstance(log.get("details"), str):
                details_dict = json.loads(log["details"])
            elif isinstance(log.get("details"), dict):
                details_dict = log["details"]
        except Exception:
            pass
            
        log_user = details_dict.get("username") or log.get("username")
        if log_user == username:
            user_logs.append(log)
            
    user_logs.sort(key=lambda x: x["timestamp"], reverse=True)
    
    conns = []
    for log in user_logs:
        if log["timestamp"] >= current_timestamp:
            continue
            
        action = log["action"]
        if action in ("xray_connect", "hysteria_connect", "hysteria2_connect", "singbox_connect"):
            ip = log["target"]
            conn_time = log["timestamp"]
            
            disconnect_time = None
            duration_str = None
            
            for d_log in user_logs:
                d_action = d_log["action"]
                if d_action in ("xray_disconnect", "hysteria_disconnect", "hysteria2_disconnect", "singbox_disconnect") and d_log["target"] == ip:
                    if d_log["timestamp"] >= conn_time:
                        if disconnect_time is None or d_log["timestamp"] < disconnect_time:
                            disconnect_time = d_log["timestamp"]
                            try:
                                d_details = json.loads(d_log["details"]) if isinstance(d_log["details"], str) else d_log["details"]
                                duration_str = d_details.get("duration")
                            except Exception:
                                pass
                                
            if disconnect_time and not duration_str:
                diff = int(disconnect_time - conn_time)
                if diff < 0:
                    diff = 0
                if diff < 60:
                    duration_str = f"{diff} сек"
                elif diff < 3600:
                    duration_str = f"{diff // 60} мин {diff % 60} сек"
                else:
                    duration_str = f"{diff // 3600} ч {(diff % 3600) // 60} мин"
            elif not duration_str:
                duration_str = "неизвестно"
                
            conns.append({
                "ip": ip,
                "timestamp": conn_time,
                "duration": duration_str
            })
            if len(conns) >= 5:
                break
                
    if not conns:
        return False, []
        
    prev_ips = {c["ip"] for c in conns}
    is_new_ip = current_ip not in prev_ips
    return is_new_ip, conns

async def handle_client_event(action: str, client_ip: str, details_str: str):
    if get_setting("telegram_bot_enabled", "true") != "true" or get_setting("telegram_client_events_enabled", "true") != "true":
        return
        
    bot_token = get_setting("telegram_bot_token", "")
    admin_ids_str = get_setting("telegram_admin_ids", "")
    if not bot_token or not admin_ids_str:
        return
    admin_ids = [x.strip() for x in admin_ids_str.split(",") if x.strip()]
    if not admin_ids:
        return

    try:
        details = json.loads(details_str)
    except Exception:
        return

    username = details.get("username", "Unknown")
    tx = details.get("tx", 0)
    rx = details.get("rx", 0)
    duration_str = details.get("duration", "неизвестно")

    now_time = time.time()
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    host_ip = await get_server_ip()
    
    protocol = "Xray" if "xray" in action else ("Sing-box" if "sing" in action else "Hysteria")
    if protocol == "Xray":
        tx, rx = rx, tx  # Swap: tx becomes client download, rx becomes client upload
        
    key = (username, protocol)
    card = active_activity_cards.get(key)
    
    async def send_to_all(text, reply_markup=None):
        msgs = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for admin_id in admin_ids:
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    payload = {"chat_id": admin_id, "text": text, "parse_mode": "HTML"}
                    if reply_markup:
                        payload["reply_markup"] = reply_markup
                    r = await client.post(url, json=payload)
                    if r.status_code == 200:
                        msg_id = r.json().get("result", {}).get("message_id")
                        if msg_id:
                            msgs.append({"chat_id": admin_id, "message_id": msg_id})
                except Exception as e:
                    logging.error(f"[Telegram Client Alerts] Send error: {e}")
        return msgs

    async def edit_all(msgs, text):
        async with httpx.AsyncClient(timeout=5.0) as client:
            for m in msgs:
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                    payload = {"chat_id": m["chat_id"], "message_id": m["message_id"], "text": text, "parse_mode": "HTML"}
                    await client.post(url, json=payload)
                except Exception:
                    pass

    if action in ("xray_connect", "hysteria_connect", "hysteria2_connect", "singbox_connect"):
        # Check for new IP connection
        try:
            from backend.models import AuditLog, ClientStats
            from backend.database import db_session
            with db_session() as session:
                client = session.query(ClientStats).filter_by(email=username).first()
                allowed_ips_str = client.allowed_ips if client else ""
                
                db_logs = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100).all()
                logs_list = [{
                    "timestamp": l.timestamp,
                    "username": l.username,
                    "action": l.action,
                    "target": l.target,
                    "details": l.details
                } for l in db_logs]
            
            is_new_ip, history = check_new_ip_and_get_history(username, client_ip, now_time, logs_list, allowed_ips=allowed_ips_str)
            if is_new_ip:
                history_lines = []
                for h in history:
                    time_formatted = datetime.datetime.fromtimestamp(h["timestamp"]).strftime("%d.%m %H:%M")
                    history_lines.append(f"• <code>{h['ip']}</code> ({time_formatted}) — {h['duration']}")
                
                history_text = "\n".join(history_lines) if history_lines else "нет предыдущих подключений"
                
                alert_text = (
                    f"🚨 <b>[{protocol} Security: {host_ip}] Обнаружено подключение с нового IP!</b>\n\n"
                    f"👤 <b>Пользователь:</b> <code>{username}</code>\n"
                    f"🌐 <b>Новый IP-адрес:</b> <code>{client_ip}</code> ⚠️ [ВНИМАНИЕ]\n"
                    f"🕒 <b>Время:</b> <code>{timestamp}</code>\n\n"
                    f"📋 <b>Предыдущие подключения (для сравнения):</b>\n"
                    f"{history_text}"
                )
                inline_buttons = {
                    "inline_keyboard": [
                        [
                            {"text": f"➕ Одобрить IP ({client_ip})", "callback_data": f"tg_allow_ip:{username}:{client_ip}"},
                            {"text": "🔴 Заблокировать", "callback_data": f"tg_block_client:{username}"}
                        ]
                    ]
                }
                await send_to_all(alert_text, reply_markup=inline_buttons)
        except Exception as e:
            logging.error(f"[Telegram Client Alerts] Error checking new IP: {e}")

        event_line = f"🟢 <code>[{timestamp}]</code> Подключение с <code>{client_ip}</code>"
        if card and is_card_active(card, now_time):
            card['lines'].append(event_line)
            card['last_activity_at'] = now_time
            if client_ip not in card['connections']:
                card['connections'][client_ip] = []
            card['connections'][client_ip].append(datetime.datetime.now())
            
            msg_text = format_card_msg(host_ip, username, protocol, card['lines'], tx, rx)
            await edit_all(card['admin_messages'], msg_text)
        else:
            lines = [event_line]
            connections = {client_ip: [datetime.datetime.now()]}
            msg_text = format_card_msg(host_ip, username, protocol, lines, tx, rx)
            
            msgs = await send_to_all(msg_text)
            active_activity_cards[key] = {
                'started_at': now_time,
                'last_activity_at': now_time,
                'lines': lines,
                'connections': connections,
                'admin_messages': msgs
            }

    elif action in ("xray_disconnect", "hysteria_disconnect", "hysteria2_disconnect", "singbox_disconnect"):
        if card and is_card_active(card, now_time):
            card['last_activity_at'] = now_time
            
            if "hysteria" in action:
                conn_list = card['connections'].get(client_ip, [])
                if conn_list:
                    conn_time = conn_list.pop(0)
                    duration_sec = int((datetime.datetime.now() - conn_time).total_seconds())
                    if duration_sec < 60:
                        duration_str = f"{duration_sec} сек"
                    elif duration_sec < 3600:
                        duration_str = f"{duration_sec // 60} мин {duration_sec % 60} сек"
                    else:
                        duration_str = f"{duration_sec // 3600} ч {(duration_sec % 3600) // 60} мин"
            else:
                conn_list = card['connections'].get(client_ip, [])
                if conn_list:
                    conn_list.pop(0)
                    
            event_line = f"🔴 <code>[{timestamp}]</code> Отключение <code>{client_ip}</code> — {duration_str}"
            card['lines'].append(event_line)
            
            msg_text = format_card_msg(host_ip, username, protocol, card['lines'], tx, rx)
            await edit_all(card['admin_messages'], msg_text)
        else:
            msg_text = (
                f"🔴 <b>[{protocol}: {host_ip}] Клиент отключился</b>\n\n"
                f"👤 Пользователь: <code>{username}</code>\n"
                f"🌐 IP-адрес: <code>{client_ip}</code>\n"
                f"🕒 Время: <code>{timestamp}</code>"
            )
            await send_to_all(msg_text)

async def update_panel_active_cards_traffic():
    if get_setting("telegram_bot_enabled", "true") != "true" or get_setting("telegram_client_events_enabled", "true") != "true":
        return
        
    bot_token = get_setting("telegram_bot_token", "")
    if not bot_token:
        return
        
    now_time = time.time()
    host_ip = await get_server_ip()
    
    for (username, protocol), card in list(active_activity_cards.items()):
        if not is_card_active(card, now_time):
            continue
        if not card.get('admin_messages'):
            continue
            
        if protocol == "Xray":
            from backend.client_alerts import get_xray_user_traffic
            tx, rx = get_xray_user_traffic(username)
            tx, rx = rx, tx  # Swap: tx becomes client download, rx becomes client upload
        else:
            from backend.client_alerts import get_user_traffic_bytes
            tx, rx = get_user_traffic_bytes(username)
            
        msg_text = format_card_msg(host_ip, username, protocol, card['lines'], tx, rx)
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for m in card['admin_messages']:
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                    payload = {"chat_id": m["chat_id"], "message_id": m["message_id"], "text": msg_text, "parse_mode": "HTML"}
                    await client.post(url, json=payload)
                except Exception:
                    pass
