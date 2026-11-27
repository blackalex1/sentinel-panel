"""Protocol link and Mihomo proxy dispatch facade."""

import inspect

from backend.links.protocols.hysteria2 import build_hysteria2_link, build_hysteria2_mihomo_proxy
from backend.links.protocols.shadowsocks import build_shadowsocks_link, build_shadowsocks_mihomo_proxy
from backend.links.protocols.trojan import build_trojan_link, build_trojan_mihomo_proxy
from backend.links.protocols.utils import get_cert_sha256_fingerprint
from backend.links.protocols.vless import build_vless_link, build_vless_mihomo_proxy
from backend.links.protocols.vmess import build_vmess_link, build_vmess_mihomo_proxy

_LINK_BUILDERS = {
    "vless": build_vless_link,
    "vmess": build_vmess_link,
    "trojan": build_trojan_link,
    "shadowsocks": build_shadowsocks_link,
    "ss": build_shadowsocks_link,
    "hysteria2": build_hysteria2_link,
}

_MIHOMO_BUILDERS = {
    "vless": build_vless_mihomo_proxy,
    "vmess": build_vmess_mihomo_proxy,
    "trojan": build_trojan_mihomo_proxy,
    "shadowsocks": build_shadowsocks_mihomo_proxy,
    "ss": build_shadowsocks_mihomo_proxy,
    "hysteria2": build_hysteria2_mihomo_proxy,
}


def _call_builder(fn, context: dict):
    accepted = inspect.signature(fn).parameters
    kwargs = {k: v for k, v in context.items() if k in accepted}
    return fn(**kwargs)


def build_link(protocol: str, **context) -> str | None:
    """Builds a share URI link for the given inbound protocol."""
    if protocol in ("socks", "socks5"):
        username = context.get("client_email") or ""
        password = (context.get("client") or {}).get("client_uuid_or_pwd") or username
        return f"socks5://{username}:{password}@{context['host']}:{context['port']}#{context['display_name']}"
    if protocol == "http":
        username = context.get("client_email") or ""
        password = (context.get("client") or {}).get("client_uuid_or_pwd") or username
        return f"http://{username}:{password}@{context['host']}:{context['port']}#{context['display_name']}"
    builder = _LINK_BUILDERS.get(protocol)
    return _call_builder(builder, context) if builder else None


def build_mihomo_proxy(protocol: str, **context) -> dict:
    """Builds a Mihomo (Clash Meta) proxy entry dictionary for the given protocol."""
    if protocol in ("socks", "socks5", "http"):
        proxy_type = "socks5" if protocol in ("socks", "socks5") else "http"
        username = context.get("client_email") or ""
        password = (context.get("client") or {}).get("client_uuid_or_pwd") or username
        return {
            "name": context["display_name"],
            "type": proxy_type,
            "server": context["host"],
            "port": context["port"],
            "username": username,
            "password": password,
        }
    builder = _MIHOMO_BUILDERS.get(protocol)
    return _call_builder(builder, context) if builder else {}


__all__ = [
    "build_link",
    "build_mihomo_proxy",
    "get_cert_sha256_fingerprint",
]
