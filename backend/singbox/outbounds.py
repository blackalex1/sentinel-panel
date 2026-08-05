import json
import logging

def parse_json_or_dict(val):
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except Exception:
            return {}
    return {}

def sanitize_singbox_config(config_dict: dict) -> dict:
    """Гарантирует правильные типы данных и синтаксис в итоговом JSON для sing-box"""
    if not isinstance(config_dict, dict):
        return config_dict

    outbounds = config_dict.get("outbounds", [])
    if isinstance(outbounds, list):
        for ob in outbounds:
            if not isinstance(ob, dict):
                continue
            if "server_ports" in ob:
                raw_ports = ob["server_ports"]
                if isinstance(raw_ports, str):
                    if "-" in raw_ports:
                        ob["server_ports"] = [raw_ports.replace("-", ":")]
                    elif "," in raw_ports:
                        ob["server_ports"] = [p.strip().replace("-", ":") for p in raw_ports.split(",") if p.strip()]
                    else:
                        ob["server_ports"] = [raw_ports.replace("-", ":")]
                elif isinstance(raw_ports, list):
                    ob["server_ports"] = [
                        str(p).strip().replace("-", ":") if isinstance(p, str) else str(p)
                        for p in raw_ports
                    ]
                if "server_port" in ob and not isinstance(ob["server_port"], int):
                    try:
                        ob["server_port"] = int(ob["server_port"])
                    except (ValueError, TypeError):
                        del ob["server_port"]
            tls = ob.get("tls")
            if isinstance(tls, dict) and tls.get("reality", {}).get("enabled"):
                if "utls" not in tls:
                    tls["utls"] = {"enabled": True, "fingerprint": "chrome"}

    return config_dict

def generate_singbox_outbounds(get_all_outbounds_fn=None) -> list:
    """Сбор исходящих подключений (outbounds) из БД для sing-box"""
    if get_all_outbounds_fn is None:
        from backend.database import get_all_outbounds as get_all_outbounds_fn

    singbox_outbounds = [
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"}
    ]

    try:
        db_outbounds = get_all_outbounds_fn()
        for ob in db_outbounds:
            if not ob.get("enable"):
                continue
            tag = ob.get("tag")
            if tag in ("direct", "block"):
                continue

            proto = ob.get("protocol")
            ob_settings = parse_json_or_dict(ob.get("settings"))
            ob_stream = parse_json_or_dict(ob.get("stream_settings"))

            sb_outbound = {
                "tag": tag,
                "type": proto if proto in ("direct", "block", "socks", "http", "wireguard", "vless", "vmess", "trojan", "shadowsocks", "hysteria", "hysteria2") else "direct"
            }

            if proto in ("socks", "http"):
                servers = ob_settings.get("servers", [])
                if servers:
                    srv = servers[0]
                    sb_outbound["server"] = srv.get("address", "")
                    sb_outbound["server_port"] = int(srv.get("port", 1080))
                    users = srv.get("users", [])
                    if users:
                        sb_outbound["username"] = users[0].get("user", "")
                        sb_outbound["password"] = users[0].get("pass", "")
                elif ob_settings.get("address") or ob_settings.get("server"):
                    sb_outbound["server"] = ob_settings.get("address") or ob_settings.get("server")
                    sb_outbound["server_port"] = int(ob_settings.get("port") or ob_settings.get("server_port") or 1080)
                    if ob_settings.get("user") or ob_settings.get("username"):
                        sb_outbound["username"] = ob_settings.get("user") or ob_settings.get("username")
                    if ob_settings.get("pass") or ob_settings.get("password"):
                        sb_outbound["password"] = ob_settings.get("pass") or ob_settings.get("password")

            elif proto == "vless":
                sb_outbound["type"] = "vless"
                v_vnext = ob_settings.get("vnext", [])
                if v_vnext:
                    vn = v_vnext[0]
                    sb_outbound["server"] = vn.get("address", "")
                    sb_outbound["server_port"] = int(vn.get("port", 443))
                    users = vn.get("users", [])
                    if users:
                        sb_outbound["uuid"] = users[0].get("id", "")
                        if users[0].get("flow"):
                            sb_outbound["flow"] = users[0].get("flow")
                else:
                    sb_outbound["server"] = ob_settings.get("address") or ob_settings.get("server") or ""
                    sb_outbound["server_port"] = int(ob_settings.get("port") or ob_settings.get("server_port") or 443)
                    sb_outbound["uuid"] = ob_settings.get("uuid") or ob_settings.get("id") or ""

                sec = ob_stream.get("security", "")
                if sec in ("tls", "reality"):
                    tls_opts = ob_stream.get("tlsSettings") or ob_stream.get("realitySettings") or {}
                    sb_outbound["tls"] = {
                        "enabled": True,
                        "server_name": tls_opts.get("serverName") or tls_opts.get("sni") or "",
                        "insecure": bool(tls_opts.get("allowInsecure", False))
                    }
                    if sec == "reality":
                        fp = tls_opts.get("fingerprint") or "chrome"
                        if fp in ("randomized", "random"):
                            fp = "chrome"
                        sb_outbound["tls"]["utls"] = {
                            "enabled": True,
                            "fingerprint": fp
                        }
                        sb_outbound["tls"]["reality"] = {
                            "enabled": True,
                            "public_key": tls_opts.get("publicKey", ""),
                            "short_id": tls_opts.get("shortId", "")
                        }

            elif proto == "vmess":
                sb_outbound["type"] = "vmess"
                v_vnext = ob_settings.get("vnext", [])
                if v_vnext:
                    vn = v_vnext[0]
                    sb_outbound["server"] = vn.get("address", "")
                    sb_outbound["server_port"] = int(vn.get("port", 443))
                    users = vn.get("users", [])
                    if users:
                        sb_outbound["uuid"] = users[0].get("id", "")
                        sb_outbound["security"] = users[0].get("security", "auto")
                else:
                    sb_outbound["server"] = ob_settings.get("address") or ob_settings.get("server") or ""
                    sb_outbound["server_port"] = int(ob_settings.get("port") or ob_settings.get("server_port") or 443)
                    sb_outbound["uuid"] = ob_settings.get("uuid") or ob_settings.get("id") or ""
                    sb_outbound["security"] = ob_settings.get("security", "auto")

            elif proto == "trojan":
                sb_outbound["type"] = "trojan"
                t_servers = ob_settings.get("servers", [])
                if t_servers:
                    srv = t_servers[0]
                    sb_outbound["server"] = srv.get("address", "")
                    sb_outbound["server_port"] = int(srv.get("port", 443))
                    sb_outbound["password"] = srv.get("password", "")
                else:
                    sb_outbound["server"] = ob_settings.get("address") or ob_settings.get("server") or ""
                    sb_outbound["server_port"] = int(ob_settings.get("port") or ob_settings.get("server_port") or 443)
                    sb_outbound["password"] = ob_settings.get("password") or ""

                sec = ob_stream.get("security", "tls")
                if sec == "tls":
                    tls_opts = ob_stream.get("tlsSettings", {})
                    sb_outbound["tls"] = {
                        "enabled": True,
                        "server_name": tls_opts.get("serverName", ""),
                        "insecure": bool(tls_opts.get("allowInsecure", False))
                    }

            elif proto == "shadowsocks":
                sb_outbound["type"] = "shadowsocks"
                ss_servers = ob_settings.get("servers", [])
                if ss_servers:
                    srv = ss_servers[0]
                    sb_outbound["server"] = srv.get("address", "")
                    sb_outbound["server_port"] = int(srv.get("port", 8388))
                    sb_outbound["method"] = srv.get("method", "aes-256-gcm")
                    sb_outbound["password"] = srv.get("password", "")
                else:
                    sb_outbound["server"] = ob_settings.get("address") or ob_settings.get("server") or ""
                    sb_outbound["server_port"] = int(ob_settings.get("port") or ob_settings.get("server_port") or 8388)
                    sb_outbound["method"] = ob_settings.get("method", "aes-256-gcm")
                    sb_outbound["password"] = ob_settings.get("password") or ""

            elif proto == "wireguard":
                sb_outbound["type"] = "wireguard"
                sb_outbound["server"] = ob_settings.get("address") or ob_settings.get("server") or ""
                sb_outbound["server_port"] = int(ob_settings.get("port") or ob_settings.get("server_port") or 51820)
                local_addr = ob_settings.get("local_address") or ob_settings.get("address_list") or []
                if isinstance(local_addr, str):
                    local_addr = [a.strip() for a in local_addr.split(",") if a.strip()]
                sb_outbound["local_address"] = local_addr
                sb_outbound["private_key"] = ob_settings.get("private_key") or ob_settings.get("secret_key") or ""
                sb_outbound["peer_public_key"] = ob_settings.get("peer_public_key") or ob_settings.get("public_key") or ""
                if ob_settings.get("pre_shared_key") or ob_settings.get("psk"):
                    sb_outbound["pre_shared_key"] = ob_settings.get("pre_shared_key") or ob_settings.get("psk")
                if ob_settings.get("mtu"):
                    try:
                        sb_outbound["mtu"] = int(ob_settings.get("mtu"))
                    except ValueError:
                        pass

            elif proto in ("hysteria", "hysteria2"):
                sb_outbound["type"] = "hysteria2"
                server = ob_settings.get("address") or ob_settings.get("server")
                port_raw = ob_settings.get("port") or ob_settings.get("server_port") or ob_stream.get("hysteriaSettings", {}).get("hop")
                
                if not server or not port_raw:
                    servers = ob_settings.get("servers", [])
                    if servers and isinstance(servers, list):
                        if not server:
                            server = servers[0].get("address") or servers[0].get("server")
                        if not port_raw:
                            port_raw = servers[0].get("port") or servers[0].get("server_port") or servers[0].get("hop")

                if not port_raw:
                    port_raw = 443

                sb_outbound["server"] = str(server or "").strip()

                port_str = str(port_raw).strip()
                if "-" in port_str:
                    sb_outbound["server_ports"] = [port_str.replace("-", ":")]
                elif "," in port_str:
                    sb_outbound["server_ports"] = [p.strip().replace("-", ":") for p in port_str.split(",") if p.strip()]
                else:
                    try:
                        sb_outbound["server_port"] = int(port_str)
                    except ValueError:
                        sb_outbound["server_ports"] = [port_str.replace("-", ":")]

                password = (
                    ob_settings.get("password")
                    or ob_settings.get("auth_str")
                    or ob_settings.get("auth")
                    or ob_settings.get("auth_password")
                    or ob_stream.get("hysteriaSettings", {}).get("auth")
                    or ob_stream.get("hysteriaSettings", {}).get("password")
                )
                if password:
                    sb_outbound["password"] = str(password)

                tls_enabled = ob_stream.get("security") in ("tls", "reality") or ob_settings.get("tls", True)
                server_name = (
                    ob_stream.get("tlsSettings", {}).get("serverName")
                    or ob_settings.get("server_name")
                    or ob_settings.get("sni")
                    or ""
                )
                insecure = ob_stream.get("tlsSettings", {}).get("allowInsecure")
                if insecure is None:
                    insecure = ob_settings.get("insecure")
                if insecure is None:
                    insecure = ob_settings.get("allowInsecure")
                if insecure is None and isinstance(ob_settings.get("tls"), dict):
                    insecure = ob_settings.get("tls", {}).get("insecure")
                if insecure is None:
                    insecure = True

                sb_outbound["tls"] = {
                    "enabled": bool(tls_enabled),
                    "server_name": server_name,
                    "insecure": bool(insecure)
                }

                obfs_type = ob_settings.get("obfs_type") or ob_settings.get("obfs") or ob_stream.get("hysteriaSettings", {}).get("obfs")
                obfs_password = ob_settings.get("obfs_password") or ob_settings.get("obfsPassword") or ob_stream.get("hysteriaSettings", {}).get("obfsPassword")
                if obfs_type:
                    if isinstance(obfs_type, dict):
                        sb_outbound["obfs"] = obfs_type
                    else:
                        sb_outbound["obfs"] = {
                            "type": str(obfs_type),
                            "password": str(obfs_password or "")
                        }

            # Настройки транспорта для аутбаундов
            network = ob_stream.get("network", "tcp")
            if network == "ws":
                ws_opts = ob_stream.get("wsSettings", {})
                sb_outbound["transport"] = {
                    "type": "ws",
                    "path": ws_opts.get("path", "/"),
                    "headers": ws_opts.get("headers", {})
                }
            elif network == "grpc":
                grpc_opts = ob_stream.get("grpcSettings", {})
                sb_outbound["transport"] = {
                    "type": "grpc",
                    "service_name": grpc_opts.get("serviceName", "")
                }
            elif network == "httpupgrade":
                http_opts = ob_stream.get("httpupgradeSettings", {})
                sb_outbound["transport"] = {
                    "type": "httpupgrade",
                    "path": http_opts.get("path", "/"),
                    "host": http_opts.get("host", "")
                }
            elif network in ("h2", "http"):
                h2_opts = ob_stream.get("httpSettings", {}) or ob_stream.get("h2Settings", {})
                sb_outbound["transport"] = {
                    "type": "http",
                    "host": h2_opts.get("host", []),
                    "path": h2_opts.get("path", "/")
                }

            backups = ob_settings.get("backup_outbounds")
            if isinstance(backups, list) and len(backups) > 0:
                valid_backups = [b for b in backups if b != tag]
                if valid_backups:
                    sb_outbound["tag"] = f"{tag}-primary"

                    probe_url = ob_settings.get("health_check_url") or "https://www.gstatic.com/generate_204"
                    probe_int = ob_settings.get("health_check_interval") or 15
                    fallback_strat = ob_settings.get("fallback_strategy", "priority")
                    
                    tolerance_val = 0 if fallback_strat == "priority" else (0 if fallback_strat == "least_ping" else 50)

                    urltest_ob = {
                        "type": "urltest",
                        "tag": tag,
                        "outbounds": [f"{tag}-primary"] + valid_backups,
                        "url": probe_url,
                        "interval": f"{probe_int}s",
                        "tolerance": tolerance_val
                    }
                    singbox_outbounds.append(urltest_ob)
                    singbox_outbounds.append(sb_outbound)
                else:
                    singbox_outbounds.append(sb_outbound)
            else:
                singbox_outbounds.append(sb_outbound)
    except Exception as e:
        logging.error(f"Error building sing-box outbounds from DB: {e}")

    return singbox_outbounds
