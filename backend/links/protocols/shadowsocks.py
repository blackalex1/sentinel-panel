from backend.links.protocols.utils import format_endpoint
import base64
from urllib.parse import quote

def build_shadowsocks_link(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict) -> str:
    method = settings.get('method', 'aes-256-gcm')
    password = client.get('client_uuid_or_pwd') or client.get('password')
    credentials = f"{method}:{password}"
    b64_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    endpoint = format_endpoint(host, port)
    return f"ss://{b64_credentials}@{endpoint}#{quote(display_name)}"


def build_shadowsocks_mihomo_proxy(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict) -> dict:
    method = settings.get('method', 'aes-256-gcm')
    password = client.get('client_uuid_or_pwd') or client.get('password') or ""
    
    return {
        "name": display_name,
        "type": "ss",
        "server": host,
        "port": int(port),
        "cipher": method,
        "password": password,
        "udp": True
    }

