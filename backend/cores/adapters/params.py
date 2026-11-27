import json
from typing import Any, Dict, List, Optional, Tuple


def parse_json_or_dict(val: Any) -> Any:
    """Преобразует JSON-строку в словарь/список или возвращает исходный контейнер."""
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
    if proto_norm in ("hysteria", "hysteria2", "wireguard", "tuic", "shadowtls"):
        return "sing-box"

    return "xray"


def parse_alpn_list(alpn: Any) -> List[str]:
    """Нормализует ALPN из строки (через запятую) или списка в непустой список строк."""
    if isinstance(alpn, str):
        return [x.strip() for x in alpn.split(",") if x.strip()]
    if isinstance(alpn, list):
        return [str(x).strip() for x in alpn if str(x).strip()]
    return []


def extract_fingerprint(params: Dict[str, Any], default: str = "chrome") -> str:
    """Извлекает uTLS fingerprint из realitySettings или tlsSettings."""
    real_set = params.get("reality_settings") or {}
    tls_set = params.get("tls_settings") or {}
    return (
        real_set.get("fingerprint")
        or real_set.get("fp")
        or tls_set.get("fingerprint")
        or tls_set.get("fp")
        or default
    )


def extract_reality_creds(reality_settings: Dict[str, Any]) -> Tuple[str, str, str]:
    """Возвращает (publicKey, shortId, spiderX) из realitySettings с учётом алиасов."""
    pbk = (
        reality_settings.get("publicKey")
        or reality_settings.get("public_key")
        or reality_settings.get("pbk")
        or ""
    )
    sid = (
        reality_settings.get("shortId")
        or reality_settings.get("short_id")
        or reality_settings.get("sid")
        or ""
    )
    spx = (
        reality_settings.get("spiderX")
        or reality_settings.get("spider_x")
        or reality_settings.get("spx")
        or "/"
    )
    return pbk, sid, spx


def _parse_port(raw_port: Any) -> int:
    port_str = str(raw_port or 443).strip()
    first_port = port_str.split("-")[0].split(",")[0].strip()
    try:
        return int(first_port)
    except ValueError:
        return 443


def _first_vnext_user(settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    vnext = settings.get("vnext")
    if isinstance(vnext, list) and vnext:
        users = vnext[0].get("users") or []
        if users:
            return users[0]
    return None


def _first_server_entry(settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    servers = settings.get("servers")
    if isinstance(servers, list) and servers:
        return servers[0]
    return None


def _extract_first_sni(reality_settings: Dict[str, Any], tls_settings: Dict[str, Any]) -> Optional[str]:
    raw_sns = reality_settings.get("serverNames") or tls_settings.get("serverNames")
    if isinstance(raw_sns, list) and raw_sns:
        return raw_sns[0]
    if isinstance(raw_sns, str):
        return raw_sns.split(",")[0].strip()
    return None


def extract_common_outbound_params(settings: dict, stream_settings: dict) -> dict:
    """Извлекает и нормализует универсальные параметры исходящего соединения из любых разновидностей входных словарей."""
    settings = parse_json_or_dict(settings)
    stream_settings = parse_json_or_dict(stream_settings)

    tls_settings = stream_settings.get("tlsSettings") or stream_settings.get("tls_settings") or {}
    reality_settings = stream_settings.get("realitySettings") or stream_settings.get("reality_settings") or {}
    ws_settings = stream_settings.get("wsSettings") or stream_settings.get("ws_settings") or {}
    grpc_settings = stream_settings.get("grpcSettings") or stream_settings.get("grpc_settings") or {}
    hyst_settings = stream_settings.get("hysteria") or {}

    vnext = settings.get("vnext")
    srv = _first_server_entry(settings)
    vnext_user = _first_vnext_user(settings)

    addr = settings.get("address") or settings.get("server") or settings.get("host")
    if not addr and isinstance(vnext, list) and vnext:
        addr = vnext[0].get("address")
    elif not addr and srv:
        addr = srv.get("address")

    raw_port = settings.get("port") or settings.get("server_port")
    if not raw_port and isinstance(vnext, list) and vnext:
        raw_port = vnext[0].get("port")
    elif not raw_port and srv:
        raw_port = srv.get("port")
    port_int = _parse_port(raw_port)

    uuid_val = settings.get("uuid") or settings.get("id")
    if not uuid_val and vnext_user:
        uuid_val = vnext_user.get("id") or vnext_user.get("uuid")

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
    if not password_val and srv:
        password_val = srv.get("password") or srv.get("pass") or srv.get("auth") or srv.get("auth_str")
        if not password_val:
            users = srv.get("users") or []
            if users:
                password_val = users[0].get("pass") or users[0].get("password") or users[0].get("auth")

    username_val = settings.get("user") or settings.get("username")
    if not username_val and srv:
        username_val = srv.get("username") or srv.get("user")
        if not username_val:
            users = srv.get("users") or []
            if users:
                username_val = users[0].get("user") or users[0].get("username")

    network_val = stream_settings.get("network") or settings.get("network") or "tcp"
    security_val = stream_settings.get("security") or settings.get("security") or "none"

    first_sn = _extract_first_sni(reality_settings, tls_settings)
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
    if not flow_val and vnext_user:
        flow_val = vnext_user.get("flow")

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
        "raw_stream_settings": stream_settings,
    }
