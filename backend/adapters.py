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

def detect_best_engine(protocol: str, explicit_core: str = "auto") -> str:
    """Определяет оптимальное ядро (sing-box или xray) на основе протокола и предпочтений."""
    core_norm = (explicit_core or "auto").strip().lower()
    if core_norm in ("singbox", "sing-box"):
        return "sing-box"
    if core_norm in ("xray", "xray-core"):
        return "xray"

    proto_norm = (protocol or "").strip().lower()
    if proto_norm in ("hysteria", "hysteria2", "wireguard", "tuic"):
        return "sing-box"
    
    return "xray"

def extract_common_outbound_params(settings: dict, stream_settings: dict) -> dict:
    """Извлекает и нормализует универсальные параметры исходящего соединения из любых разновидностей входных словарей."""
    settings = parse_json_or_dict(settings)
    stream_settings = parse_json_or_dict(stream_settings)

    tls_settings = stream_settings.get("tlsSettings") or stream_settings.get("tls_settings") or {}
    reality_settings = stream_settings.get("realitySettings") or stream_settings.get("reality_settings") or {}
    ws_settings = stream_settings.get("wsSettings") or stream_settings.get("ws_settings") or {}
    grpc_settings = stream_settings.get("grpcSettings") or stream_settings.get("grpc_settings") or {}
    hyst_settings = stream_settings.get("hysteria") or {}

    addr = settings.get("address") or settings.get("server") or settings.get("host")
    if not addr and "vnext" in settings and settings["vnext"]:
        addr = settings["vnext"][0].get("address")
    elif not addr and "servers" in settings and settings["servers"]:
        addr = settings["servers"][0].get("address")

    raw_port = settings.get("port") or settings.get("server_port")
    if not raw_port and "vnext" in settings and settings["vnext"]:
        raw_port = settings["vnext"][0].get("port")
    elif not raw_port and "servers" in settings and settings["servers"]:
        raw_port = settings["servers"][0].get("port")

    port_str = str(raw_port or 443).strip()
    first_port = port_str.split("-")[0].split(",")[0].strip()
    try:
        port_int = int(first_port)
    except ValueError:
        port_int = 443

    uuid_val = settings.get("uuid") or settings.get("id")
    if not uuid_val and "vnext" in settings and settings["vnext"]:
        users = settings["vnext"][0].get("users", [])
        if users:
            uuid_val = users[0].get("id") or users[0].get("uuid")

    password_val = (
        settings.get("password")
        or settings.get("pass")
        or settings.get("auth")
        or settings.get("auth_str")
        or stream_settings.get("auth")
        or stream_settings.get("password")
        or hyst_settings.get("auth")
        or hyst_settings.get("password")
    )
    if not password_val and "servers" in settings and settings["servers"]:
        srv = settings["servers"][0]
        password_val = srv.get("password") or srv.get("pass") or srv.get("auth") or srv.get("auth_str")
        if not password_val:
            users = srv.get("users", [])
            if users:
                password_val = users[0].get("pass") or users[0].get("password") or users[0].get("auth")

    username_val = settings.get("user") or settings.get("username")
    if not username_val and "servers" in settings and settings["servers"]:
        srv = settings["servers"][0]
        username_val = srv.get("username") or srv.get("user")
        if not username_val:
            users = srv.get("users", [])
            if users:
                username_val = users[0].get("user") or users[0].get("username")

    network_val = stream_settings.get("network") or settings.get("network") or "tcp"
    security_val = stream_settings.get("security") or settings.get("security") or "none"

    raw_reality_sns = reality_settings.get("serverNames") or tls_settings.get("serverNames")
    if isinstance(raw_reality_sns, list) and raw_reality_sns:
        first_sn = raw_reality_sns[0]
    elif isinstance(raw_reality_sns, str):
        first_sn = raw_reality_sns.split(",")[0].strip()
    else:
        first_sn = None

    sni_val = (
        tls_settings.get("serverName")
        or tls_settings.get("sni")
        or reality_settings.get("serverName")
        or reality_settings.get("sni")
        or first_sn
        or hyst_settings.get("sni")
        or stream_settings.get("sni")
        or settings.get("sni")
        or addr
    )

    flow_val = settings.get("flow")
    if not flow_val and "vnext" in settings and settings["vnext"]:
        users = settings["vnext"][0].get("users", [])
        if users:
            flow_val = users[0].get("flow")

    return {
        "address": addr or "",
        "port": port_int,
        "uuid": uuid_val or "",
        "password": password_val or "",
        "username": username_val or "",
        "network": network_val,
        "security": security_val,
        "sni": sni_val or "",
        "flow": flow_val or "",
        "tls_settings": tls_settings,
        "reality_settings": reality_settings,
        "ws_settings": ws_settings,
        "grpc_settings": grpc_settings,
        "hysteria_settings": hyst_settings,
        "raw_settings": settings,
        "raw_stream_settings": stream_settings
    }

def build_singbox_outbound(protocol: str, settings: dict, stream_settings: dict = None, tag: str = "test-out") -> dict:
    """Строит структуру исходящего подключения для ядра Sing-box."""
    params = extract_common_outbound_params(settings, stream_settings or {})
    proto = (protocol or "").strip().lower()

    if proto in ("hysteria", "hysteria2", "hy2"):
        sb_ob = {
            "type": "hysteria2",
            "tag": tag,
            "server": params["address"],
            "server_port": params["port"],
            "password": params["password"],
            "tls": {
                "enabled": True,
                "insecure": True
            }
        }
        if params["sni"]:
            sb_ob["tls"]["server_name"] = params["sni"]
            
        obfs_val = (
            settings.get("obfs")
            or (stream_settings or {}).get("obfs")
            or params["hysteria_settings"].get("obfs")
        )
        if obfs_val:
            if isinstance(obfs_val, str):
                sb_ob["obfs"] = {
                    "type": "salamander",
                    "password": obfs_val
                }
            elif isinstance(obfs_val, dict):
                sb_ob["obfs"] = obfs_val
        return sb_ob

    if proto in ("socks", "http"):
        return {
            "type": proto,
            "tag": tag,
            "server": params["address"],
            "server_port": params["port"],
            "username": params["username"],
            "password": params["password"]
        }

    if proto == "vless":
        sb_ob = {
            "type": "vless",
            "tag": tag,
            "server": params["address"],
            "server_port": params["port"],
            "uuid": params["uuid"]
        }
        if params["flow"]:
            sb_ob["flow"] = params["flow"]

        if params["security"] in ("tls", "reality"):
            sb_ob["tls"] = {
                "enabled": True,
                "insecure": True,
                "server_name": params["sni"]
            }
            fp = (
                params["reality_settings"].get("fingerprint")
                or params["reality_settings"].get("fp")
                or params["tls_settings"].get("fingerprint")
                or params["tls_settings"].get("fp")
                or "chrome"
            )
            sb_ob["tls"]["utls"] = {
                "enabled": True,
                "fingerprint": fp
            }
            if params["security"] == "reality":
                pbk = (
                    params["reality_settings"].get("publicKey")
                    or params["reality_settings"].get("public_key")
                    or params["reality_settings"].get("pbk")
                )
                sid = (
                    params["reality_settings"].get("shortId")
                    or params["reality_settings"].get("short_id")
                    or params["reality_settings"].get("sid")
                )
                sb_ob["tls"]["reality"] = {
                    "enabled": True,
                    "public_key": pbk or "",
                    "short_id": sid or ""
                }
        return sb_ob

    if proto == "vmess":
        sb_ob = {
            "type": "vmess",
            "tag": tag,
            "server": params["address"],
            "server_port": params["port"],
            "uuid": params["uuid"],
            "security": "auto"
        }
        if params["security"] == "tls":
            sb_ob["tls"] = {
                "enabled": True,
                "insecure": True,
                "server_name": params["sni"]
            }
        return sb_ob

    if proto == "shadowsocks":
        method = params["raw_settings"].get("method") or "aes-256-gcm"
        return {
            "type": "shadowsocks",
            "tag": tag,
            "server": params["address"],
            "server_port": params["port"],
            "method": method,
            "password": params["password"]
        }

    # По умолчанию фоллбэк на direct
    return {"type": "direct", "tag": tag}

def build_xray_outbound(protocol: str, settings: dict, stream_settings: dict = None, tag: str = "test-out") -> dict:
    """Строит структуру исходящего подключения для ядра Xray."""
    params = extract_common_outbound_params(settings, stream_settings or {})
    proto = (protocol or "").strip().lower()

    if proto in ("hysteria", "hysteria2"):
        # Для Xray Hysteria 2 передаем совместимую структуру
        xray_settings = {
            "version": 2,
            "servers": [
                {
                    "address": params["address"],
                    "port": params["port"],
                    "password": params["password"]
                }
            ]
        }
        return {
            "protocol": "hysteria",
            "settings": xray_settings,
            "tag": tag
        }

    from backend.xray import clean_stream_settings

    if proto == "vless":
        xray_settings = {
            "vnext": [
                {
                    "address": params["address"],
                    "port": params["port"],
                    "users": [
                        {
                            "id": params["uuid"] or params["password"],
                            "encryption": "none",
                            "flow": params["flow"]
                        }
                    ]
                }
            ]
        }
        # Сохраняем encryption, если был явно передан
        raw_vnext = params["raw_settings"].get("vnext")
        if isinstance(raw_vnext, list) and raw_vnext:
            users_list = raw_vnext[0].get("users") or [{}]
            if users_list and users_list[0].get("encryption"):
                xray_settings["vnext"][0]["users"][0]["encryption"] = users_list[0]["encryption"]
        elif params["raw_settings"].get("encryption"):
            xray_settings["vnext"][0]["users"][0]["encryption"] = params["raw_settings"]["encryption"]

        stream_settings_out = {
            "network": params["network"] or "tcp",
            "security": params["security"] or "none"
        }
        if params["security"] == "reality":
            real_set = params["reality_settings"]
            pbk = real_set.get("publicKey") or real_set.get("public_key") or real_set.get("pbk") or ""
            sid = real_set.get("shortId") or real_set.get("short_id") or real_set.get("sid") or ""
            spx = real_set.get("spiderX") or real_set.get("spider_x") or real_set.get("spx") or "/"
            fp = (
                real_set.get("fingerprint")
                or real_set.get("fp")
                or params["tls_settings"].get("fingerprint")
                or params["tls_settings"].get("fp")
                or "chrome"
            )
            stream_settings_out["realitySettings"] = {
                "serverName": params["sni"],
                "fingerprint": fp,
                "show": False,
                "publicKey": pbk,
                "shortId": sid,
                "spiderX": spx
            }
        elif params["security"] == "tls":
            tls_set = params["tls_settings"]
            fp = tls_set.get("fingerprint") or tls_set.get("fp") or "chrome"
            stream_settings_out["tlsSettings"] = {
                "serverName": params["sni"],
                "fingerprint": fp
            }
            alpn = tls_set.get("alpn")
            if alpn:
                if isinstance(alpn, str):
                    stream_settings_out["tlsSettings"]["alpn"] = [x.strip() for x in alpn.split(",") if x.strip()]
                elif isinstance(alpn, list):
                    stream_settings_out["tlsSettings"]["alpn"] = alpn

        if params["network"] in ("ws", "httpupgrade", "xhttp"):
            ws_set = params["ws_settings"]
            stream_settings_out["wsSettings"] = {
                "path": ws_set.get("path") or "/",
                "headers": ws_set.get("headers") or {}
            }
        elif params["network"] == "grpc":
            grpc_set = params["grpc_settings"]
            stream_settings_out["grpcSettings"] = {
                "serviceName": grpc_set.get("serviceName") or grpc_set.get("service_name") or "grpc"
            }

        return {
            "protocol": "vless",
            "settings": xray_settings,
            "streamSettings": clean_stream_settings(stream_settings_out),
            "tag": tag
        }

    if proto == "vmess":
        xray_settings = {
            "vnext": [
                {
                    "address": params["address"],
                    "port": params["port"],
                    "users": [
                        {
                            "id": params["uuid"] or params["password"],
                            "security": "auto"
                        }
                    ]
                }
            ]
        }
        stream_settings_out = {
            "network": params["network"] or "tcp",
            "security": params["security"] or "none"
        }
        if params["security"] == "tls":
            stream_settings_out["tlsSettings"] = {
                "serverName": params["sni"],
                "fingerprint": params["tls_settings"].get("fingerprint") or "chrome"
            }
        return {
            "protocol": "vmess",
            "settings": xray_settings,
            "streamSettings": clean_stream_settings(stream_settings_out),
            "tag": tag
        }

    if proto == "trojan":
        xray_settings = {
            "servers": [
                {
                    "address": params["address"],
                    "port": params["port"],
                    "password": params["password"] or params["uuid"]
                }
            ]
        }
        stream_settings_out = {
            "network": params["network"] or "tcp",
            "security": "tls",
            "tlsSettings": {
                "serverName": params["sni"],
                "fingerprint": params["tls_settings"].get("fingerprint") or "chrome"
            }
        }
        return {
            "protocol": "trojan",
            "settings": xray_settings,
            "streamSettings": clean_stream_settings(stream_settings_out),
            "tag": tag
        }

    if proto in ("shadowsocks", "ss"):
        method = params["raw_settings"].get("method") or "2022-blake3-aes-128-gcm"
        xray_settings = {
            "servers": [
                {
                    "address": params["address"],
                    "port": params["port"],
                    "password": params["password"],
                    "method": method
                }
            ]
        }
        return {
            "protocol": "shadowsocks",
            "settings": xray_settings,
            "tag": tag
        }

    if proto in ("socks", "http"):
        users = []
        if params["username"] or params["password"]:
            users.append({"user": params["username"], "pass": params["password"]})
        return {
            "protocol": proto,
            "settings": {
                "servers": [
                    {
                        "address": params["address"],
                        "port": params["port"],
                        "users": users
                    }
                ]
            },
            "tag": tag
        }

    if proto in ("freedom", "direct"):
        return {
            "protocol": "freedom",
            "settings": {"domainStrategy": "AsIs"},
            "tag": tag
        }

    if proto in ("blackhole", "block"):
        return {
            "protocol": "blackhole",
            "settings": {"response": {"type": "none"}},
            "tag": tag
        }

    # Для остальных протоколов Xray используем сырые настройки с очисткой
    outbound = {
        "protocol": proto,
        "settings": parse_json_or_dict(settings),
        "tag": tag
    }
    if stream_settings:
        outbound["streamSettings"] = clean_stream_settings(parse_json_or_dict(stream_settings))

    return outbound

def build_outbound_config(engine: str, protocol: str, settings: dict, stream_settings: dict = None, tag: str = "test-out") -> dict:
    """Универсальный фасад адаптации исходящего подключения под указанное ядро."""
    engine_norm = detect_best_engine(protocol, engine)
    if engine_norm == "sing-box":
        return build_singbox_outbound(protocol, settings, stream_settings, tag)
    else:
        return build_xray_outbound(protocol, settings, stream_settings, tag)
