import json
import logging
import backend.config
import backend.xray.config as xray_config_facade
from backend.xray.config_builder.sanitizer import clean_stream_settings

def generate_xray_config_json() -> dict:
    """Генерирует JSON конфигурации для Xray на основе данных из БД"""
    get_all_inbounds = xray_config_facade.get_all_inbounds
    get_clients_for_inbound = xray_config_facade.get_clients_for_inbound
    get_all_outbounds = xray_config_facade.get_all_outbounds
    get_all_routing_rules = xray_config_facade.get_all_routing_rules
    get_setting = xray_config_facade.get_setting

    inbounds = get_all_inbounds()
    
    xray_inbounds = []
    
    # 1. Добавляем системное входящее подключение для gRPC API управления
    xray_inbounds.append({
        "listen": "127.0.0.1",
        "port": 10085,
        "protocol": "dokodemo-door",
        "settings": {
            "address": "127.0.0.1"
        },
        "tag": "api"
    })
    
    # 2. Добавляем пользовательские входящие подключения (VLESS, VMess, Trojan, Shadowsocks)
    for ib in inbounds:
        if not ib["enable"]:
            continue
            
        protocol = ib["protocol"]
        ib_id = ib["id"]
        ib_core = ib.get("core") or ("hysteria" if protocol == "hysteria2" else "xray")

        # Если инбаунд предназначен для sing-box или другого ядра, не транслируем его в Xray напрямую
        if ib_core != "xray" and protocol != "hysteria2":
            continue

        if protocol == "hysteria2":
            try:
                stream_settings = json.loads(ib["stream_settings"] or "{}")
                hysteria_opts = stream_settings.get("hysteria", {})
                if hysteria_opts.get("routingViaXray"):
                    socks_username = hysteria_opts.get("socksUsername", "default_user")
                    socks_password = hysteria_opts.get("socksPassword", "default_pass")
                    xray_inbounds.append({
                        "listen": "127.0.0.1",
                        "port": 20000 + ib_id,
                        "protocol": "socks",
                        "settings": {
                            "auth": "password",
                            "accounts": [
                                {
                                    "user": socks_username,
                                    "pass": socks_password
                                }
                            ],
                            "udp": True
                        },
                        "tag": f"inbound-{ib_id}-socks"
                    })
            except Exception as e:
                logging.error(f"Error generating SOCKS5 inbound for Hysteria 2 routing: {e}")
            continue
            
        ib_id = ib["id"]
        port = ib["port"]
        
        # Загружаем настройки из БД
        try:
            db_settings = json.loads(ib["settings"] or "{}")
            stream_settings = json.loads(ib["stream_settings"] or "{}")
            sniffing = json.loads(ib["sniffing"] or "{}")
        except Exception as e:
            logging.error(f"Error parsing JSON for inbound {ib_id}: {e}")
            continue
            
        # Загружаем клиентов этого инбаунда из client_stats
        db_clients = get_clients_for_inbound(ib_id)
        
        # Формируем структуру настроек Xray в зависимости от протокола
        xray_settings = {}
        
        if protocol == "vless":
            clients_list = []
            for c in db_clients:
                if not c["enable"]:
                    continue
                client_flow = ""
                if db_settings.get("clients"):
                    for sc in db_settings["clients"]:
                        if sc.get("email") == c["email"]:
                            client_flow = sc.get("flow", "")
                            break
                clients_list.append({
                    "id": c["client_uuid_or_pwd"],
                    "email": c["email"],
                    "flow": client_flow
                })
            xray_settings = {
                "clients": clients_list,
                "decryption": db_settings.get("decryption", "none")
            }
            fallbacks = db_settings.get("fallbacks")
            if fallbacks:
                xray_settings["fallbacks"] = fallbacks
            elif stream_settings.get("security") in ("tls", "reality"):
                from backend.config import settings
                panel_port = getattr(settings, "PANEL_PORT", 8000)
                xray_settings["fallbacks"] = [{"dest": panel_port, "xver": 0}]
            
        elif protocol == "vmess":
            clients_list = []
            for c in db_clients:
                if not c["enable"]:
                    continue
                alter_id = 0
                if db_settings.get("clients"):
                    for sc in db_settings["clients"]:
                        if sc.get("email") == c["email"]:
                            alter_id = int(sc.get("alterId", 0))
                            break
                clients_list.append({
                    "id": c["client_uuid_or_pwd"],
                    "email": c["email"],
                    "alterId": alter_id
                })
            xray_settings = {
                "clients": clients_list
            }
            
        elif protocol == "trojan":
            clients_list = []
            for c in db_clients:
                if not c["enable"]:
                    continue
                clients_list.append({
                    "password": c["client_uuid_or_pwd"],
                    "email": c["email"]
                })
            xray_settings = {
                "clients": clients_list
            }
            fallbacks = db_settings.get("fallbacks")
            if fallbacks:
                xray_settings["fallbacks"] = fallbacks
            elif stream_settings.get("security") in ("tls", "reality"):
                from backend.config import settings
                panel_port = getattr(settings, "PANEL_PORT", 8000)
                xray_settings["fallbacks"] = [{"dest": panel_port, "xver": 0}]
            else:
                xray_settings["fallbacks"] = []
            
        elif protocol == "shadowsocks":
            method = db_settings.get("method") or "aes-256-gcm"
            is_legacy = not method.startswith("2022-blake3")
            clients_list = []
            for c in db_clients:
                if not c["enable"]:
                    continue
                client_item = {
                    "password": c["client_uuid_or_pwd"],
                    "email": c["email"]
                }
                if is_legacy:
                    client_item["method"] = method
                clients_list.append(client_item)
            xray_settings = {
                "method": method,
                "clients": clients_list,
                "network": "tcp,udp"
            }
            if not is_legacy and clients_list:
                xray_settings["password"] = clients_list[0]["password"]

        elif protocol in ("socks", "http"):
            accounts = []
            for c in db_clients:
                if not c["enable"]:
                    continue
                accounts.append({
                    "user": c["email"],
                    "pass": c["client_uuid_or_pwd"] or c["email"]
                })
            xray_settings = {
                "auth": "password" if accounts else "noauth",
                "accounts": accounts,
                "udp": True if protocol == "socks" else False
            }
        xray_inbound = {
            "port": port,
            "protocol": protocol,
            "settings": xray_settings,
            "tag": f"inbound-{ib_id}"
        }
        
        if stream_settings:
            stream_settings = clean_stream_settings(stream_settings)
            tls_settings = stream_settings.get("tlsSettings", {})
            if tls_settings:
                if not tls_settings.get("certificates"):
                    from backend.ssl_utils import SSL_CERT_PATH, SSL_KEY_PATH
                    if SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists():
                        tls_settings["certificates"] = [
                            {
                                "certificateFile": str(SSL_CERT_PATH),
                                "keyFile": str(SSL_KEY_PATH)
                            }
                        ]
            xray_inbound["streamSettings"] = stream_settings
            
        if "streamSettings" not in xray_inbound:
            xray_inbound["streamSettings"] = {}
        if "sockopt" not in xray_inbound["streamSettings"]:
            xray_inbound["streamSettings"]["sockopt"] = {}
        xray_inbound["streamSettings"]["sockopt"]["reusePort"] = True
        
        if sniffing:
            xray_inbound["sniffing"] = sniffing
            
        xray_inbounds.append(xray_inbound)
        
    # Загружаем исходящие подключения (Outbounds) из БД
    db_outbounds = get_all_outbounds()
    xray_outbounds = []
    for ob in db_outbounds:
        if ob["enable"] != 1:
            continue
        try:
            settings_dict = json.loads(ob["settings"] or "{}")
            stream_settings_dict = json.loads(ob["stream_settings"] or "{}")
        except Exception:
            settings_dict = {}
            stream_settings_dict = {}
        
        if ob["protocol"] in ("hysteria", "hysteria2"):
            addr = settings_dict.get("address") or settings_dict.get("server")
            if not addr and "servers" in settings_dict and settings_dict["servers"]:
                addr = settings_dict["servers"][0].get("address")

            raw_port = settings_dict.get("port") or settings_dict.get("server_port") or settings_dict.get("server_ports")
            if not raw_port and "servers" in settings_dict and settings_dict["servers"]:
                raw_port = settings_dict["servers"][0].get("port")

            port_str = str(raw_port or 443).strip()
            first_port = port_str.split("-")[0].split(":")[0].split(",")[0].strip()
            try:
                port_int = int(first_port)
            except ValueError:
                port_int = 443

            pwd = (
                settings_dict.get("password")
                or settings_dict.get("auth_str")
                or settings_dict.get("auth")
                or (settings_dict.get("servers", [{}])[0].get("password") if settings_dict.get("servers") else "")
            )

            if "server_ports" in settings_dict:
                del settings_dict["server_ports"]
            if "server_port" in settings_dict:
                del settings_dict["server_port"]

            settings_dict["server"] = str(addr or "").strip()
            settings_dict["port"] = port_int
            settings_dict["auth"] = str(pwd or "")
            settings_dict["servers"] = [
                {
                    "address": str(addr or "").strip(),
                    "port": port_int,
                    "password": str(pwd or "")
                }
            ]
            settings_dict["version"] = 2

        if ob["protocol"] == "vless":
            vnext = settings_dict.get("vnext", [])
            for server in vnext:
                for user in server.get("users", []):
                    if "encryption" not in user or not user["encryption"]:
                        user["encryption"] = "none"

        proto_name = "hysteria" if ob["protocol"] in ("hysteria", "hysteria2") else ob["protocol"]
        ob_dict = {
            "protocol": proto_name,
            "settings": settings_dict
        }
        if stream_settings_dict:
            ob_dict["streamSettings"] = clean_stream_settings(stream_settings_dict)
            
        if ob["tag"]:
            ob_dict["tag"] = ob["tag"]
            
        xray_outbounds.append(ob_dict)
        
    xray_outbounds.sort(key=lambda x: 0 if x.get("tag") == "direct" else (1 if x.get("tag") == "blocked" else 2))
        
    if not xray_outbounds:
        xray_outbounds = [
            {"protocol": "freedom", "settings": {}, "tag": "direct"},
            {"protocol": "blackhole", "settings": {}, "tag": "blocked"}
        ]
        
    rules = []
    
    # 1. API rule first
    rules.append({
        "type": "field",
        "inboundTag": ["api"],
        "outboundTag": "api"
    })
    
    # 2. System Quick Block Rules
    if get_setting("block_bittorrent") == "true":
        rules.append({
            "type": "field",
            "outboundTag": "blocked",
            "protocol": ["bittorrent"]
        })
        rules.append({
            "type": "field",
            "outboundTag": "blocked",
            "domain": ["domain:torrent", "domain:tracker", "domain:peerexchange", "keyword:torrent"]
        })
        
    if get_setting("block_ads") == "true":
        rules.append({
            "type": "field",
            "outboundTag": "blocked",
            "domain": ["geosite:category-ads-all"]
        })
        
    blocked_countries = []
    if get_setting("block_cn") == "true":
        blocked_countries.append("cn")
    if get_setting("block_ru") == "true":
        blocked_countries.append("ru")
    if get_setting("block_us") == "true":
        blocked_countries.append("us")
        
    if blocked_countries:
        geo_domains = []
        for c in blocked_countries:
            if c.lower() == "cn":
                geo_domains.append("geosite:cn")
            else:
                geo_domains.append(f"regexp:.*\\.{c}$")
        rules.append({
            "type": "field",
            "outboundTag": "blocked",
            "ip": [f"geoip:{c}" for c in blocked_countries],
            "domain": geo_domains
        })

    # 3. User Routing Rules from DB
    hysteria_outbound_tags = {
        ob["tag"] for ob in db_outbounds 
        if ob["enable"] == 1 and ob.get("protocol") in ("hysteria", "hysteria2")
    }
    active_non_socks_inbound_tags = [
        f"inbound-{ib['id']}" for ib in inbounds 
        if ib["enable"] and ib.get("protocol") != "hysteria2"
    ]

    db_rules = get_all_routing_rules()
    for r in db_rules:
        if r["enable"] != 1:
            continue
            
        rule_dict = {
            "type": "field",
            "outboundTag": r["outbound_tag"]
        }
        
        if r["inbound_tags"]:
            inbound_tags_list = r["inbound_tags"]
            active_xray_tags = {ib["tag"] for ib in xray_inbounds}
            if not any(t in active_xray_tags for t in inbound_tags_list):
                continue
            if r["outbound_tag"] in hysteria_outbound_tags:
                inbound_tags_list = [
                    t for t in inbound_tags_list 
                    if not (t.startswith("inbound-") and t.endswith("-socks"))
                ]
            if inbound_tags_list:
                rule_dict["inboundTag"] = inbound_tags_list
        else:
            if r["outbound_tag"] in hysteria_outbound_tags:
                if active_non_socks_inbound_tags:
                    rule_dict["inboundTag"] = active_non_socks_inbound_tags
                else:
                    continue
        if r.get("users"):
            rule_dict["user"] = r["users"]
        if r["domains"]:
            rule_dict["domain"] = r["domains"]
        if r["ips"]:
            rule_dict["ip"] = r["ips"]
        if r["protocols"]:
            protocols_list = r["protocols"]
            networks = [p.lower() for p in protocols_list if p.lower() in ("tcp", "udp")]
            app_protocols = [p for p in protocols_list if p.lower() not in ("tcp", "udp")]
            
            if networks:
                rule_dict["network"] = ",".join(networks)
            if app_protocols:
                rule_dict["protocol"] = app_protocols
            
        if len(rule_dict) > 2:
            rules.append(rule_dict)

    # 4. Проверяем настройки резервирования для outbounds
    active_outbound_tags = {ob.get("tag") for ob in xray_outbounds if ob.get("tag")}
    balancers = []
    observatory_subjects = set()

    for ob in db_outbounds:
        if ob["enable"] != 1:
            continue
        try:
            s_dict = json.loads(ob["settings"] or "{}")
        except Exception:
            s_dict = {}
        
        main_tag = ob["tag"]
        backups = s_dict.get("backup_outbounds")
        if isinstance(backups, list):
            valid_backups = [b for b in backups if b in active_outbound_tags and b != main_tag]
            if valid_backups and main_tag in active_outbound_tags:
                balancer_tag = f"balancer-{main_tag}"
                fallback_strategy = s_dict.get("fallback_strategy", "priority")
                
                balancer_entry = {"tag": balancer_tag}
                
                if fallback_strategy == "priority":
                    balancer_entry["selector"] = [main_tag]
                    balancer_entry["fallbackTag"] = valid_backups[0]
                    balancer_entry["strategy"] = {"type": "leastPing"}
                elif fallback_strategy == "round_robin":
                    balancer_entry["selector"] = [main_tag] + valid_backups
                    balancer_entry["strategy"] = {"type": "random"}
                else:  # least_ping
                    balancer_entry["selector"] = [main_tag] + valid_backups
                    balancer_entry["strategy"] = {"type": "leastPing"}
                
                balancers.append(balancer_entry)
                observatory_subjects.update([main_tag] + valid_backups)
                
                has_balancer_rule = False
                for rule in rules:
                    if rule.get("outboundTag") == main_tag:
                        del rule["outboundTag"]
                        rule["balancerTag"] = balancer_tag
                        has_balancer_rule = True

                if not has_balancer_rule:
                    rules.append({
                        "type": "field",
                        "network": "tcp,udp",
                        "balancerTag": balancer_tag
                    })

    used_outbound_tags = {"direct", "blocked", "api"}
    for rule in rules:
        if "outboundTag" in rule:
            used_outbound_tags.add(rule["outboundTag"])
    for b in balancers:
        for tag in b["selector"]:
            used_outbound_tags.add(tag)

    filtered_xray_outbounds = [
        ob for ob in xray_outbounds
        if ob.get("tag") in used_outbound_tags
    ]

    routing_dict = {
        "rules": rules
    }
    if balancers:
        routing_dict["balancers"] = balancers

    config = {
        "log": {
            "access": str(backend.config.XRAY_LOG_PATH),
            "error": str(backend.config.XRAY_LOG_PATH),
            "loglevel": "info"
        },
        "api": {
            "tag": "api",
            "services": [
                "HandlerService",
                "StatsService"
            ]
        },
        "stats": {},
        "policy": {
            "levels": {
                "0": {
                    "statsUserUplink": True,
                    "statsUserDownlink": True
                }
            },
            "system": {
                "statsInboundUplink": True,
                "statsInboundDownlink": True,
                "statsOutboundUplink": True,
                "statsOutboundDownlink": True
            }
        },
        "inbounds": xray_inbounds,
        "outbounds": filtered_xray_outbounds,
        "routing": routing_dict
    }

    if observatory_subjects:
        config["observatory"] = {
            "subjectSelector": list(observatory_subjects),
            "probeUrl": "https://www.gstatic.com/generate_204",
            "probeInterval": "15s"
        }
    
    return config
