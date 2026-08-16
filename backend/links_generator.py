import json
import yaml
from urllib.parse import urlparse
from backend.links.protocols import (
    get_cert_sha256_fingerprint,
    build_vless_link,
    build_vless_mihomo_proxy,
    build_vmess_link,
    build_vmess_mihomo_proxy,
    build_trojan_link,
    build_trojan_mihomo_proxy,
    build_shadowsocks_link,
    build_shadowsocks_mihomo_proxy,
    build_hysteria2_link,
    build_hysteria2_mihomo_proxy,
)

import socket

def get_lan_ip() -> str:
    """Определяет локальный IP-адрес сетевой карты в локальной сети."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_base_host(host_url: str) -> str:
    """Извлекает IP или домен из URL. Если это localhost или 127.0.0.1, заменяет на реальный локальный IP."""
    if not host_url:
        return get_lan_ip()
    if "://" not in host_url:
        host_url = "http://" + host_url
    parsed = urlparse(host_url)
    h = parsed.hostname or ""
    if not h or h in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
        return get_lan_ip()
    return h

def get_client_links(inbound: dict, client: dict, host_url: str) -> list:
    """Генерирует ссылки для подключения (VLESS, VMess, Trojan, Shadowsocks)"""
    protocol = inbound.get('protocol')
    port = inbound.get('port')
    remark = inbound.get('remark', 'VPN')
    host = get_base_host(host_url)
    if not host:
        host = host_url  # фолбек если это просто IP
        
    client_email = client.get('email', 'client')
    display_name = f"{remark}-{client_email}"
    
    # Парсим настройки
    try:
        settings = json.loads(inbound.get('settings', '{}'))
        stream_settings = json.loads(inbound.get('stream_settings', '{}') or inbound.get('streamSettings', '{}') or '{}')
    except Exception:
        return []

    security = stream_settings.get('security', 'none')
    network = stream_settings.get('network', 'tcp')
    
    links = []

    # Находим конкретные параметры клиента
    flow = ""
    alter_id = 0
    security_cipher = "auto"
    for sc in settings.get("clients", []):
        if sc.get("email") == client_email:
            flow = sc.get("flow", "")
            alter_id = int(sc.get("alterId", 0))
            security_cipher = sc.get("security", "auto")
            break

    if protocol == 'vless':
        link = build_vless_link(
            inbound=inbound,
            client=client,
            host=host,
            port=port,
            display_name=display_name,
            settings=settings,
            stream_settings=stream_settings,
            network=network,
            security=security,
            flow=flow
        )
        links.append(link)

    elif protocol == 'vmess':
        link = build_vmess_link(
            inbound=inbound,
            client=client,
            host=host,
            port=port,
            display_name=display_name,
            settings=settings,
            stream_settings=stream_settings,
            network=network,
            security=security,
            security_cipher=security_cipher,
            alter_id=alter_id
        )
        links.append(link)

    elif protocol == 'trojan':
        link = build_trojan_link(
            inbound=inbound,
            client=client,
            host=host,
            port=port,
            display_name=display_name,
            settings=settings,
            stream_settings=stream_settings,
            network=network,
            security=security
        )
        links.append(link)

    elif protocol in ('shadowsocks', 'ss'):
        link = build_shadowsocks_link(
            inbound=inbound,
            client=client,
            host=host,
            port=port,
            display_name=display_name,
            settings=settings
        )
        links.append(link)

    elif protocol == 'hysteria2':
        link = build_hysteria2_link(
            inbound=inbound,
            client=client,
            host=host,
            port=port,
            display_name=display_name,
            stream_settings=stream_settings,
            client_email=client_email
        )
        links.append(link)

    elif protocol in ('socks', 'socks5'):
        username = client_email
        password = client.get('client_uuid_or_pwd') or username
        links.append(f"socks5://{username}:{password}@{host}:{port}#{display_name}")

    elif protocol == 'http':
        username = client_email
        password = client.get('client_uuid_or_pwd') or username
        links.append(f"http://{username}:{password}@{host}:{port}#{display_name}")

    return links


def get_client_mihomo_proxy(inbound: dict, client: dict, host_url: str) -> dict:
    """Генерирует словарь конфигурации узла для Mihomo (Clash Meta)"""
    protocol = inbound.get('protocol')
    port = inbound.get('port')
    remark = inbound.get('remark', 'VPN')
    host = get_base_host(host_url)
    if not host:
        host = host_url
        
    client_email = client.get('email', 'client')
    display_name = f"{remark}-{client_email}"
    
    try:
        settings = json.loads(inbound.get('settings', '{}'))
        stream_settings = json.loads(inbound.get('stream_settings', '{}') or inbound.get('streamSettings', '{}') or '{}')
    except Exception:
        settings = {}
        stream_settings = {}

    security = stream_settings.get('security', 'none')
    network = stream_settings.get('network', 'tcp')

    flow = ""
    alter_id = 0
    security_cipher = "auto"
    for sc in settings.get("clients", []):
        if sc.get("email") == client_email:
            flow = sc.get("flow", "")
            alter_id = int(sc.get("alterId", 0))
            security_cipher = sc.get("security", "auto")
            break

    if protocol == 'vless':
        return build_vless_mihomo_proxy(
            inbound=inbound, client=client, host=host, port=port,
            display_name=display_name, settings=settings, stream_settings=stream_settings,
            network=network, security=security, flow=flow
        )
    elif protocol == 'vmess':
        return build_vmess_mihomo_proxy(
            inbound=inbound, client=client, host=host, port=port,
            display_name=display_name, settings=settings, stream_settings=stream_settings,
            network=network, security=security, security_cipher=security_cipher, alter_id=alter_id
        )
    elif protocol == 'trojan':
        return build_trojan_mihomo_proxy(
            inbound=inbound, client=client, host=host, port=port,
            display_name=display_name, settings=settings, stream_settings=stream_settings,
            network=network, security=security
        )
    elif protocol in ('shadowsocks', 'ss'):
        return build_shadowsocks_mihomo_proxy(
            inbound=inbound, client=client, host=host, port=port,
            display_name=display_name, settings=settings
        )
    elif protocol == 'hysteria2':
        return build_hysteria2_mihomo_proxy(
            inbound=inbound, client=client, host=host, port=port,
            display_name=display_name, stream_settings=stream_settings, client_email=client_email
        )
    elif protocol in ('socks', 'socks5'):
        username = client_email
        password = client.get('client_uuid_or_pwd') or username
        return {
            "name": display_name,
            "type": "socks5",
            "server": host,
            "port": port,
            "username": username,
            "password": password
        }
    elif protocol == 'http':
        username = client_email
        password = client.get('client_uuid_or_pwd') or username
        return {
            "name": display_name,
            "type": "http",
            "server": host,
            "port": port,
            "username": username,
            "password": password
        }
    return {}



def get_client_mihomo_yaml(inbound: dict, client: dict, host_url: str) -> str:
    """Возвращает сгенерированный прокси-узел в формате YAML блоком proxies:"""
    proxy_dict = get_client_mihomo_proxy(inbound, client, host_url)
    if not proxy_dict:
        return ""
    data = {"proxies": [proxy_dict]}
    return yaml.dump(data, allow_unicode=True, sort_keys=False)

