import logging
from backend.models import Inbound
from backend.database import db_session, get_clients_for_inbound
import backend.watchdog_state

def run_service_watchdog():
    """Service watchdog running to check if xray and hysteria are running when active inbounds exist."""
    import backend.scheduler
    
    backend.watchdog_state.in_watchdog_context = True
    try:
        with db_session() as session:
            # Check active xray inbounds
            has_xray_inbounds = session.query(Inbound).filter(
                Inbound.enable == 1,
                Inbound.protocol.in_(["vless", "vmess", "trojan", "shadowsocks", "socks", "http"]),
                (Inbound.core.is_(None) | (Inbound.core == "xray"))
            ).count() > 0
            
            # Check active hysteria inbounds
            import json
            hysteria_inbound_ids = []
            hysteria_inbounds = session.query(Inbound).filter_by(
                enable=1,
                protocol="hysteria2"
            ).all()
            for ib in hysteria_inbounds:
                hysteria_inbound_ids.append(ib.id)
                try:
                    stream_settings = json.loads(ib.stream_settings or "{}")
                    if stream_settings.get("hysteria", {}).get("routingViaXray"):
                        has_xray_inbounds = True
                except Exception:
                    pass
            
        # Check active singbox inbounds
        has_singbox_inbounds = session.query(Inbound).filter(
            Inbound.enable == 1,
            ((Inbound.core == "singbox") | (Inbound.protocol == "singbox"))
        ).count() > 0

        # Xray core check
        if has_xray_inbounds:
            if not backend.scheduler.is_xray_running():
                if backend.watchdog_state.consecutive_xray_restarts < 3:
                    backend.watchdog_state.consecutive_xray_restarts += 1
                    logging.warning(f"[Watchdog] Xray is dead but active inbounds exist. Restarting (attempt {backend.watchdog_state.consecutive_xray_restarts}/3)...")
                    backend.scheduler.restart_xray()
                else:
                    logging.error("[Watchdog] Xray failed to start after 3 attempts. Watchdog suspended for Xray.")
            else:
                backend.watchdog_state.consecutive_xray_restarts = 0
                
        # Hysteria 2 core check
        if hysteria_inbound_ids:
            # Check if there are active clients for hysteria inbounds
            has_active_clients = False
            for ib_id in hysteria_inbound_ids:
                clients = get_clients_for_inbound(ib_id)
                if any(c["enable"] for c in clients):
                    has_active_clients = True
                    break
                    
            if has_active_clients:
                if not backend.scheduler.is_hysteria_running():
                    if backend.watchdog_state.consecutive_hysteria_restarts < 3:
                        backend.watchdog_state.consecutive_hysteria_restarts += 1
                        logging.warning(f"[Watchdog] Hysteria 2 is dead but active inbounds exist. Restarting (attempt {backend.watchdog_state.consecutive_hysteria_restarts}/3)...")
                        backend.scheduler.restart_hysteria()
                    else:
                        logging.error("[Watchdog] Hysteria 2 failed to start after 3 attempts. Watchdog suspended for Hysteria 2.")
                else:
                    backend.watchdog_state.consecutive_hysteria_restarts = 0

        # Sing-box core check
        from backend.singbox import is_singbox_running, restart_singbox, stop_singbox
        if has_singbox_inbounds:
            if not is_singbox_running():
                if backend.watchdog_state.consecutive_singbox_restarts < 3:
                    backend.watchdog_state.consecutive_singbox_restarts += 1
                    logging.warning(f"[Watchdog] Sing-box is dead but active inbounds exist. Restarting (attempt {backend.watchdog_state.consecutive_singbox_restarts}/3)...")
                    restart_singbox()
                else:
                    logging.error("[Watchdog] Sing-box failed to start after 3 attempts. Watchdog suspended for Sing-box.")
            else:
                backend.watchdog_state.consecutive_singbox_restarts = 0
        else:
            if is_singbox_running():
                logging.info("[Watchdog] No active Sing-box inbounds found. Stopping Sing-box.")
                stop_singbox()
    finally:
        backend.watchdog_state.in_watchdog_context = False
