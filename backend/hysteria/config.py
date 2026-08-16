"""Hysteria 2 configuration builder - powered by sentinel-core native compiler."""
import sys
import json
import logging
from backend.sentinel_core_bridge import build_server_config
from backend.database import get_setting

def generate_hysteria_config(inbound_id: int, port: int, clients: list, stream_settings: dict = None) -> dict:
    """Generates Hysteria 2 configuration JSON via sentinel-core."""
    try:
        if "pytest" in sys.modules:
            try:
                from tests.core_verifier import get_free_port
                admin_port = get_free_port()
            except Exception:
                admin_port = 10100 + (port % 1000)
        else:
            admin_port = 10100 + (port % 1000)

        hysteria_opts = stream_settings.get("hysteria", {}) if stream_settings else {}
        cert_mode = hysteria_opts.get("certMode", "self")
        cert_path = hysteria_opts.get("certPath", "")
        key_path = hysteria_opts.get("keyPath", "")
        if not (cert_mode == "custom" and cert_path and key_path):
            import backend.hysteria
            cert_path = str(backend.hysteria.HYSTERIA_CERT_PATH)
            key_path = str(backend.hysteria.HYSTERIA_KEY_PATH)

        secret_key = get_setting("telegram_bot_token") or "secret"
        auth_url = f"http://127.0.0.1:8000/api/hysteria/auth?secret={secret_key}"

        masq_type = hysteria_opts.get("masqType", "")
        masq_value = hysteria_opts.get("masqValue", "")
        masq_status_code = hysteria_opts.get("masqStatusCode", 0)
        if not masq_type:
            if not hysteria_opts.get("obfsPassword"):
                central_decoy_type = get_setting("decoy_type") or "none"
                central_decoy_val = get_setting("decoy_value") or ""
                if central_decoy_type == "drop":
                    masq_type = "drop"
                    masq_status_code = 444
                elif central_decoy_type == "proxy" and central_decoy_val:
                    masq_type = "proxy"
                    masq_value = central_decoy_val
        elif not masq_status_code and masq_type == "status" and masq_value:
            try:
                masq_status_code = int(masq_value)
            except Exception:
                pass

        up_mbps = hysteria_opts.get("upMbps", 0)
        down_mbps = hysteria_opts.get("downMbps", 0)

        socks_port = 0
        socks_user = ""
        socks_pass = ""
        if hysteria_opts.get("routingViaXray"):
            socks_port = 20000 + inbound_id
            socks_user = hysteria_opts.get("socksUsername", "")
            socks_pass = hysteria_opts.get("socksPassword", "")

        inbound_spec = [{
            "id": inbound_id,
            "port": port,
            "protocol": "hysteria2",
            "tag": f"inbound-{inbound_id}",
            "certPath": cert_path,
            "keyPath": key_path,
            "authUrl": auth_url,
            "adminPort": admin_port,
            "portHop": hysteria_opts.get("hop", ""),
            "obfsType": "salamander" if hysteria_opts.get("obfsPassword") else "",
            "obfsPassword": hysteria_opts.get("obfsPassword", ""),
            "bandwidthUp": f"{up_mbps} mbps" if isinstance(up_mbps, int) and up_mbps > 0 else str(up_mbps) if up_mbps else "",
            "bandwidthDown": f"{down_mbps} mbps" if isinstance(down_mbps, int) and down_mbps > 0 else str(down_mbps) if down_mbps else "",
            "masqType": masq_type,
            "masqValue": masq_value,
            "masqStatusCode": masq_status_code,
            "socksPort": socks_port,
            "socksUsername": socks_user,
            "socksPassword": socks_pass,
            "clients": [
                {"email": c["email"], "password": c["client_uuid_or_pwd"], "enable": bool(c.get("enable", True))}
                for c in clients if c.get("enable", True)
            ]
        }]

        res = build_server_config("hysteria2", inbound_spec)
        if isinstance(res, dict):
            if "config" in res:
                cfg = res["config"]
                if isinstance(cfg, str):
                    return json.loads(cfg)
                elif isinstance(cfg, dict):
                    return cfg
            return res
    except Exception as e:
        logging.error(f"Error compiling hysteria2 config via sentinel-core: {e}")
    return {}

def ensure_hysteria_quic_and_log(config: dict) -> dict:
    """Helper to ensure hysteria config has quic and log structure."""
    if not isinstance(config, dict):
        return {}
    if "quic" not in config:
        config["quic"] = {"initStreamReceiveWindow": 8388608, "maxStreamReceiveWindow": 8388608}
    if "log" not in config:
        config["log"] = {"level": "info"}
    return config
