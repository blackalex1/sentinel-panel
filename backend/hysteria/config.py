import logging
import backend.hysteria

def generate_hysteria_config(inbound_id: int, port: int, clients: list, stream_settings: dict = None) -> dict:
    """Генерирует JSON конфигурации для Hysteria 2"""
    auth_userpass = {}
    for c in clients:
        if c["enable"]:
            auth_userpass[c["email"]] = c["client_uuid_or_pwd"]
            
    import sys
    if "pytest" in sys.modules:
        from tests.core_verifier import get_free_port
        admin_port = get_free_port()
    else:
        admin_port = 10100 + inbound_id

    hysteria_opts = stream_settings.get("hysteria", {}) if stream_settings else {}
    obfs_password = hysteria_opts.get("obfsPassword", "")
    up_mbps = hysteria_opts.get("upMbps", 0)
    down_mbps = hysteria_opts.get("downMbps", 0)
    
    cert_mode = hysteria_opts.get("certMode", "self")
    cert_path = hysteria_opts.get("certPath", "")
    key_path = hysteria_opts.get("keyPath", "")
    masq_type = hysteria_opts.get("masqType", "proxy")
    masq_value = hysteria_opts.get("masqValue", "https://yahoo.com")
    hop = hysteria_opts.get("hop", "")

    # Настройка TLS
    sni = hysteria_opts.get("sni", "").strip()
    if cert_mode == "custom" and cert_path and key_path:
        tls_config = {
            "cert": cert_path,
            "key": key_path
        }
    else:
        from backend.ssl_utils import SSL_CERT_PATH, SSL_KEY_PATH, cert_matches_domain, generate_custom_self_signed_cert
        from backend.config import CONFIG_DIR

        if sni:
            if SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists() and cert_matches_domain(SSL_CERT_PATH, sni):
                tls_config = {
                    "cert": str(SSL_CERT_PATH),
                    "key": str(SSL_KEY_PATH)
                }
            else:
                custom_cert = CONFIG_DIR / f"hysteria_{inbound_id}.crt"
                custom_key = CONFIG_DIR / f"hysteria_{inbound_id}.key"
                generate_custom_self_signed_cert(custom_cert, custom_key, sni)
                tls_config = {
                    "cert": str(custom_cert),
                    "key": str(custom_key)
                }
        else:
            if SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists():
                tls_config = {
                    "cert": str(SSL_CERT_PATH),
                    "key": str(SSL_KEY_PATH)
                }
            else:
                tls_config = {
                    "cert": str(backend.hysteria.HYSTERIA_CERT_PATH),
                    "key": str(backend.hysteria.HYSTERIA_KEY_PATH)
                }
    if sni:
        tls_config["sni"] = sni

    # Настройка Masquerade
    from backend.database import get_setting
    central_decoy_type = get_setting("decoy_type", "none")
    central_decoy_value = get_setting("decoy_value", "company_landing")

    if hysteria_opts and "masqType" in hysteria_opts:
        if masq_type == "file":
            masq_config = {
                "type": "file",
                "file": {
                    "dir": masq_value
                }
            }
        elif masq_type == "status":
            try:
                status_code = int(masq_value)
            except ValueError:
                status_code = 404
            masq_config = {
                "type": "string",
                "string": {
                    "content": str(status_code),
                    "headers": {
                        "Content-Type": "text/plain"
                    },
                    "statusCode": status_code
                }
            }
        else:  # proxy
            masq_config = {
                "type": "proxy",
                "proxy": {
                    "url": masq_value or "https://yahoo.com",
                    "rewriteHost": True
                }
            }
    else:
        # Централизованный Decoy панели для Hysteria 2
        if central_decoy_type == "drop":
            masq_config = {
                "type": "string",
                "string": {
                    "content": "",
                    "headers": {},
                    "statusCode": 444
                }
            }
        elif central_decoy_type == "none":
            masq_config = {
                "type": "string",
                "string": {
                    "content": "404 Not Found",
                    "headers": {
                        "Content-Type": "text/html"
                    },
                    "statusCode": 404
                }
            }
        elif central_decoy_type in ("proxy", "redirect") and central_decoy_value.startswith("http"):
            masq_config = {
                "type": "proxy",
                "proxy": {
                    "url": central_decoy_value,
                    "rewriteHost": True
                }
            }
        else:
            from backend.config import settings
            from backend.ssl_utils import SSL_CERT_PATH, SSL_KEY_PATH
            use_https = SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists()
            panel_proto = "https" if use_https else "http"
            masq_config = {
                "type": "proxy",
                "proxy": {
                    "url": f"{panel_proto}://127.0.0.1:{settings.PANEL_PORT}",
                    "rewriteHost": True,
                    "insecure": True
                }
            }

    # Настройка listen (с поддержкой Port Hopping)
    listen_str = f":{port}"
    if hop:
        if "-" in hop:
            try:
                start_port, end_port = hop.split("-", 1)
                start_port = int(start_port.strip())
                end_port = int(end_port.strip())
                if start_port == port:
                    listen_str = f":{hop}"
                else:
                    logging.warning(
                        f"Hysteria 2: Primary port {port} does not match start of hop range {hop}. "
                        f"Listening on primary port {port} only. Please configure firewall DNAT manually."
                    )
            except ValueError:
                logging.warning(f"Hysteria 2: Invalid hop range format '{hop}'. Listening on port {port} only.")
        else:
            logging.warning(
                f"Hysteria 2: Hop '{hop}' is not a range. Hysteria 2 requires a range for automatic port hopping. "
                f"Listening on port {port} only."
            )

    from backend.config import settings
    from backend.ssl_utils import SSL_CERT_PATH, SSL_KEY_PATH
    use_https = SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists()
    panel_proto = "https" if use_https else "http"
    auth_url = f"{panel_proto}://127.0.0.1:{settings.PANEL_PORT}/api/hysteria/auth?secret={settings.API_TOKEN}"

    config = {
        "listen": listen_str,
        "auth": {
            "type": "http",
            "http": {
                "url": auth_url,
                "insecure": True
            }
        },
        "tls": tls_config,
        "trafficStats": {
            "listen": f"127.0.0.1:{admin_port}"
        },
        "quic": {
            "initStreamReceiveWindow": 8388608,
            "maxStreamReceiveWindow": 8388608,
            "initConnReceiveWindow": 20971520,
            "maxConnReceiveWindow": 20971520,
            "maxIdleTimeout": "60s",
            "keepAliveInterval": "5s",
            "maxIncomingStreams": 1024,
            "disablePathMTUDiscovery": False
        }
    }

    if not obfs_password:
        config["masquerade"] = masq_config

    try:
        up_mbps = int(up_mbps) if up_mbps else 0
    except ValueError:
        up_mbps = 0

    try:
        down_mbps = int(down_mbps) if down_mbps else 0
    except ValueError:
        down_mbps = 0

    if obfs_password:
        config["obfs"] = {
            "type": "salamander",
            "salamander": {
                "password": obfs_password
            }
        }

    ignore_bw = hysteria_opts.get("ignoreClientBandwidth", False)
    
    if ignore_bw or (not up_mbps and not down_mbps and "ignoreClientBandwidth" not in hysteria_opts):
        config["ignoreClientBandwidth"] = True
    elif up_mbps > 0 or down_mbps > 0:
        config["bandwidth"] = {}
        if up_mbps > 0:
            config["bandwidth"]["up"] = f"{up_mbps} mbps"
        if down_mbps > 0:
            config["bandwidth"]["down"] = f"{down_mbps} mbps"
            
    if hysteria_opts.get("routingViaXray"):
        socks_username = hysteria_opts.get("socksUsername", "default_user")
        socks_password = hysteria_opts.get("socksPassword", "default_pass")
        config["outbounds"] = [
            {
                "name": "xray-socks",
                "type": "socks5",
                "socks5": {
                    "addr": f"127.0.0.1:{20000 + inbound_id}",
                    "username": socks_username,
                    "password": socks_password
                }
            }
        ]
    return ensure_hysteria_quic_and_log(config)

def ensure_hysteria_quic_and_log(config: dict) -> dict:
    if not isinstance(config, dict):
        return config
    if "quic" not in config or not isinstance(config["quic"], dict):
        config["quic"] = {
            "initStreamReceiveWindow": 8388608,
            "maxStreamReceiveWindow": 8388608,
            "initConnReceiveWindow": 20971520,
            "maxConnReceiveWindow": 20971520,
            "maxIdleTimeout": "60s",
            "keepAliveInterval": "5s",
            "maxIncomingStreams": 1024,
            "disablePathMTUDiscovery": False
        }
    else:
        q = config["quic"]
        if "initStreamReceiveWindow" not in q: q["initStreamReceiveWindow"] = 8388608
        if "maxStreamReceiveWindow" not in q: q["maxStreamReceiveWindow"] = 8388608
        if "initConnReceiveWindow" not in q: q["initConnReceiveWindow"] = 20971520
        if "maxConnReceiveWindow" not in q: q["maxConnReceiveWindow"] = 20971520
        if "maxIdleTimeout" not in q: q["maxIdleTimeout"] = "60s"
        if "keepAliveInterval" not in q: q["keepAliveInterval"] = "5s"
        if "maxIncomingStreams" not in q: q["maxIncomingStreams"] = 1024
        if "disablePathMTUDiscovery" not in q: q["disablePathMTUDiscovery"] = False

    if "udpIdleTimeout" not in config:
        config["udpIdleTimeout"] = "60s"

    if "resolver" not in config or not isinstance(config["resolver"], dict):
        config["resolver"] = {
            "type": "tls",
            "tcp": {
                "addr": "8.8.8.8:53",
                "timeout": "4s"
            },
            "udp": {
                "addr": "8.8.4.4:53",
                "timeout": "4s"
            },
            "tls": {
                "addr": "1.1.1.1:853",
                "timeout": "10s",
                "sni": "cloudflare-dns.com",
                "insecure": False
            },
            "https": {
                "addr": "1.1.1.1:443",
                "timeout": "10s",
                "sni": "cloudflare-dns.com",
                "insecure": False
            }
        }

    if "log" not in config or not isinstance(config["log"], dict):
        from backend.database import get_setting
        hy_loglevel = get_setting("hysteria_loglevel")
        if hy_loglevel not in ("debug", "info", "warn", "error"):
            hy_loglevel = "info"
        config["log"] = {
            "level": hy_loglevel
        }
    return config

def read_hysteria_config(inbound_id: int) -> dict:
    """Считывает имеющийся конфигурационный файл Hysteria 2 с диска"""
    config_path = backend.hysteria.BIN_DIR / f"hysteria_{inbound_id}.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return ensure_hysteria_quic_and_log(cfg)
    except Exception as e:
        logging.error(f"Failed to read Hysteria 2 config from {config_path}: {e}")
        return {}

def parse_hysteria_config(raw_input) -> dict:
    """Парсит и валидирует строку или словарь конфигурации Hysteria 2"""
    if isinstance(raw_input, dict):
        config_dict = raw_input
    elif isinstance(raw_input, str):
        try:
            config_dict = json.loads(raw_input)
        except Exception as e:
            raise ValueError(f"Невалидный JSON конфигурации Hysteria 2: {e}")
    else:
        raise ValueError("Входные данные должны быть строкой JSON или словарем.")

    if not isinstance(config_dict, dict):
        raise ValueError("Конфигурация Hysteria 2 должна быть JSON-объектом (dict).")

    return config_dict
