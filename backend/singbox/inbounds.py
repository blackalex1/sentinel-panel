import json
import logging
from backend.ssl_utils import SSL_CERT_PATH, SSL_KEY_PATH

def parse_json_or_dict(val):
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except Exception:
            return {}
    return {}

def generate_singbox_inbounds(get_all_inbounds_fn=None, get_clients_fn=None) -> list:
    """Генерирует входящие подключения для ядра sing-box на основе данных из БД"""
    if get_all_inbounds_fn is None:
        from backend.database import get_all_inbounds as get_all_inbounds_fn
    if get_clients_fn is None:
        from backend.database import get_clients_for_inbound as get_clients_fn

    singbox_inbounds = []

    try:
        inbounds = get_all_inbounds_fn()
    except Exception as e:
        logging.error(f"Error fetching inbounds for sing-box: {e}")
        return []

    for ib in inbounds:
        try:
            if not ib.get("enable"):
                continue

            ib_id = ib["id"]
            port = ib["port"]
            protocol = ib["protocol"]
            core = ib.get("core") or ("hysteria" if protocol in ("hysteria", "hysteria2") else "xray")

            if core != "singbox":
                continue

            db_settings = parse_json_or_dict(ib.get("settings"))
            stream_settings = parse_json_or_dict(ib.get("stream_settings"))

            clients_stats = get_clients_fn(ib_id)
            clients_settings = db_settings.get("clients", []) if isinstance(db_settings.get("clients"), list) else []

            if not clients_stats and clients_settings:
                clients_stats = []
                for cs in clients_settings:
                    c_id = cs.get("id") or cs.get("uuid") or cs.get("password")
                    c_email = cs.get("email") or "user"
                    if c_id:
                        clients_stats.append({
                            "email": c_email,
                            "client_uuid_or_pwd": c_id,
                            "enable": True
                        })

            client_flow_map = {}
            for cs in clients_settings:
                c_id = cs.get("id") or cs.get("uuid") or cs.get("email")
                c_flow = cs.get("flow")
                if c_id and c_flow:
                    client_flow_map[c_id] = c_flow
                    if cs.get("email"):
                        client_flow_map[cs.get("email")] = c_flow

            users_list = []
            sb_proto = "hysteria2" if protocol in ("hysteria", "hysteria2") else protocol

            for c in clients_stats:
                if not c.get("enable", True):
                    continue
                email = c.get("email", "")
                secret = c.get("client_uuid_or_pwd", "")
                if sb_proto in ("vless", "vmess"):
                    u_obj = {"name": email, "uuid": secret}
                    flow_val = client_flow_map.get(secret) or client_flow_map.get(email)
                    if flow_val:
                        u_obj["flow"] = flow_val
                    elif sb_proto == "vless":
                        u_obj["flow"] = "xtls-rprx-vision"
                    users_list.append(u_obj)
                elif sb_proto in ("trojan", "shadowsocks", "hysteria2"):
                    users_list.append({
                        "name": email,
                        "password": secret
                    })
                elif sb_proto in ("socks", "http"):
                    users_list.append({
                        "username": email,
                        "password": secret
                    })
                else:
                    users_list.append({
                        "name": email,
                        "uuid": secret
                    })

            sb_inbound = {
                "type": sb_proto,
                "tag": f"inbound-{ib_id}",
                "listen": "::",
                "listen_port": port,
                "users": users_list
            }

            if sb_proto == "shadowsocks":
                sb_inbound["method"] = db_settings.get("method", "aes-256-gcm")

            # Настройки TLS / Reality для sing-box
            security = stream_settings.get("security", "")
            if security == "reality":
                reality_opts = stream_settings.get("realitySettings", {})
                inner_opts = reality_opts.get("settings", {}) if isinstance(reality_opts.get("settings"), dict) else {}

                raw_dest = str(inner_opts.get("dest") or reality_opts.get("dest") or "")
                if ":" in raw_dest:
                    dest_parts = raw_dest.rsplit(":", 1)
                    h_server = dest_parts[0]
                    try:
                        h_port = int(dest_parts[1])
                    except ValueError:
                        h_port = 443
                else:
                    h_server = raw_dest or "yahoo.com"
                    h_port = 443

                server_names = inner_opts.get("serverNames") or reality_opts.get("serverNames") or []
                server_name = server_names[0] if server_names else (inner_opts.get("serverName") or reality_opts.get("serverName") or h_server)

                short_ids = inner_opts.get("shortIds") or reality_opts.get("shortIds") or []
                short_id_list = [s for s in short_ids if s] if short_ids else []

                private_key = inner_opts.get("privateKey") or reality_opts.get("privateKey") or ""

                max_time_diff = (
                    inner_opts.get("maxTimeDiff")
                    or inner_opts.get("max_time_difference")
                    or reality_opts.get("maxTimeDiff")
                    or reality_opts.get("max_time_difference")
                )
                clean_mtd = ""
                if isinstance(max_time_diff, (int, float)) and max_time_diff > 0:
                    clean_mtd = f"{int(max_time_diff)}s"
                elif isinstance(max_time_diff, str) and max_time_diff.strip():
                    val = max_time_diff.lower().rstrip("s").strip()
                    if val.isdigit() and int(val) > 0:
                        clean_mtd = f"{val}s"

                reality_config = {
                    "enabled": True,
                    "handshake": {
                        "server": h_server,
                        "server_port": h_port
                    },
                    "private_key": private_key,
                    "short_id": short_id_list
                }
                if clean_mtd:
                    reality_config["max_time_difference"] = clean_mtd

                sb_inbound["tls"] = {
                    "enabled": True,
                    "reality": reality_config
                }
                if server_name:
                    sb_inbound["tls"]["server_name"] = server_name

            elif security == "tls":
                tls_opts = stream_settings.get("tlsSettings", {})
                server_name = tls_opts.get("serverName", "")
                alpn_input = tls_opts.get("alpn", ["h2", "http/1.1"])
                if isinstance(alpn_input, str):
                    alpn = [a.strip() for a in alpn_input.split(",") if a.strip()]
                elif isinstance(alpn_input, list):
                    alpn = [str(a).strip() for a in alpn_input if str(a).strip()]
                else:
                    alpn = ["h2", "http/1.1"]

                sb_tls = {
                    "enabled": True,
                    "server_name": server_name,
                    "alpn": alpn
                }
                cert_file = tls_opts.get("certificateFile")
                key_file = tls_opts.get("keyFile")
                if cert_file and key_file:
                    sb_tls["certificate_path"] = str(cert_file)
                    sb_tls["key_path"] = str(key_file)
                elif SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists():
                    sb_tls["certificate_path"] = str(SSL_CERT_PATH)
                    sb_tls["key_path"] = str(SSL_KEY_PATH)

                sb_inbound["tls"] = sb_tls

            # Настройки транспорта для sing-box (ws, grpc, httpupgrade, h2)
            network = stream_settings.get("network", "tcp")
            if network == "ws":
                ws_opts = stream_settings.get("wsSettings", {})
                sb_inbound["transport"] = {
                    "type": "ws",
                    "path": ws_opts.get("path", "/"),
                    "headers": ws_opts.get("headers", {})
                }
            elif network == "grpc":
                grpc_opts = stream_settings.get("grpcSettings", {})
                sb_inbound["transport"] = {
                    "type": "grpc",
                    "service_name": grpc_opts.get("serviceName", "")
                }
            elif network == "httpupgrade":
                http_opts = stream_settings.get("httpupgradeSettings", {})
                sb_inbound["transport"] = {
                    "type": "httpupgrade",
                    "path": http_opts.get("path", "/"),
                    "host": http_opts.get("host", "")
                }
            elif network in ("h2", "http"):
                h2_opts = stream_settings.get("httpSettings", {}) or stream_settings.get("h2Settings", {})
                sb_inbound["transport"] = {
                    "type": "http",
                    "host": h2_opts.get("host", []),
                    "path": h2_opts.get("path", "/")
                }

            singbox_inbounds.append(sb_inbound)
        except Exception as e:
            logging.error(f"Error building sing-box inbound for id {ib.get('id')}: {e}")

    return singbox_inbounds
