from typing import Any, Dict

from .params import (
    extract_common_outbound_params,
    extract_fingerprint,
    extract_reality_creds,
    parse_alpn_list,
)


def _build_hysteria2(params: Dict[str, Any], raw_stream: Dict[str, Any], tag: str) -> Dict[str, Any]:
    raw_settings = params["raw_settings"]
    sb_ob: Dict[str, Any] = {
        "type": "hysteria2",
        "tag": tag,
        "server": params["address"],
        "password": params["password"],
        "tls": {
            "enabled": True,
            "insecure": True,
        },
    }

    port_hop = (
        raw_settings.get("port_hopping")
        or raw_settings.get("portHopping")
        or params["hysteria_settings"].get("hop")
        or ""
    )
    hop_str = str(port_hop).strip() if port_hop else ""
    if hop_str and any(ch in hop_str for ch in ("-", ",", ":")):
        sb_ob["server_ports"] = [p.strip().replace("-", ":") for p in hop_str.split(",") if p.strip()]
        sb_ob["hop_interval"] = "300s"
    else:
        sb_ob["server_port"] = params["port"]

    if params["sni"]:
        sb_ob["tls"]["server_name"] = params["sni"]

    obfs_val = (
        raw_settings.get("obfs")
        or raw_stream.get("obfs")
        or params["hysteria_settings"].get("obfs")
    )
    if obfs_val:
        if isinstance(obfs_val, str):
            sb_ob["obfs"] = {"type": "salamander", "password": obfs_val}
        elif isinstance(obfs_val, dict):
            sb_ob["obfs"] = obfs_val
    return sb_ob


def _build_vless(params: Dict[str, Any], tag: str) -> Dict[str, Any]:
    sb_ob: Dict[str, Any] = {
        "type": "vless",
        "tag": tag,
        "server": params["address"],
        "server_port": params["port"],
        "uuid": params["uuid"],
    }
    if params["flow"]:
        sb_ob["flow"] = params["flow"]

    if params["security"] in ("tls", "reality"):
        sb_ob["tls"] = {
            "enabled": True,
            "insecure": True,
            "server_name": params["sni"],
            "utls": {
                "enabled": True,
                "fingerprint": extract_fingerprint(params, default="chrome"),
            },
        }
        if params["security"] == "reality":
            pbk, sid, _ = extract_reality_creds(params["reality_settings"])
            sb_ob["tls"]["reality"] = {
                "enabled": True,
                "public_key": pbk,
                "short_id": sid,
            }
    return sb_ob


def _build_vmess(params: Dict[str, Any], tag: str) -> Dict[str, Any]:
    sb_ob: Dict[str, Any] = {
        "type": "vmess",
        "tag": tag,
        "server": params["address"],
        "server_port": params["port"],
        "uuid": params["uuid"],
        "security": "auto",
    }
    if params["security"] == "tls":
        sb_ob["tls"] = {
            "enabled": True,
            "insecure": True,
            "server_name": params["sni"],
        }
    return sb_ob


def _build_shadowsocks(params: Dict[str, Any], tag: str) -> Dict[str, Any]:
    return {
        "type": "shadowsocks",
        "tag": tag,
        "server": params["address"],
        "server_port": params["port"],
        "method": params["raw_settings"].get("method") or "aes-256-gcm",
        "password": params["password"],
    }


def _build_tuic(params: Dict[str, Any], tag: str) -> Dict[str, Any]:
    raw_settings = params["raw_settings"]
    tls_settings = params["tls_settings"]
    alpn = parse_alpn_list(tls_settings.get("alpn")) or ["h3"]
    return {
        "type": "tuic",
        "tag": tag,
        "server": params["address"],
        "server_port": params["port"],
        "uuid": params["uuid"],
        "password": params["password"],
        "congestion_control": raw_settings.get("congestionControl") or raw_settings.get("congestion_control") or "bbr",
        "udp_relay_mode": raw_settings.get("udpRelayMode") or raw_settings.get("udp_relay_mode") or "native",
        "zero_rtt_handshake": bool(
            raw_settings.get("zeroRttHandshake") or raw_settings.get("zero_rtt_handshake") or False
        ),
        "tls": {
            "enabled": True,
            "server_name": params["sni"],
            "insecure": bool(tls_settings.get("allowInsecure", False)),
            "alpn": alpn,
        },
    }


def _build_shadowtls(params: Dict[str, Any], tag: str) -> Dict[str, Any]:
    raw_settings = params["raw_settings"]
    version = int(raw_settings.get("shadowTlsVersion") or raw_settings.get("version") or 3)
    fp = raw_settings.get("fingerprint") or params["tls_settings"].get("fingerprint") or "chrome"
    return {
        "type": "shadowtls",
        "tag": tag,
        "server": params["address"],
        "server_port": params["port"],
        "version": version,
        "password": params["password"],
        "tls": {
            "enabled": True,
            "server_name": params["sni"] or raw_settings.get("sni") or "",
            "utls": {
                "enabled": True,
                "fingerprint": fp,
            },
        },
    }


def build_singbox_outbound(protocol: str, settings: dict, stream_settings: dict = None, tag: str = "test-out") -> dict:
    """Строит структуру исходящего подключения для ядра Sing-box."""
    raw_stream = stream_settings or {}
    params = extract_common_outbound_params(settings, raw_stream)
    proto = (protocol or "").strip().lower()

    if proto in ("hysteria", "hysteria2", "hy2"):
        return _build_hysteria2(params, raw_stream, tag)
    if proto in ("socks", "http"):
        return {
            "type": proto,
            "tag": tag,
            "server": params["address"],
            "server_port": params["port"],
            "username": params["username"],
            "password": params["password"],
        }
    if proto == "vless":
        return _build_vless(params, tag)
    if proto == "vmess":
        return _build_vmess(params, tag)
    if proto == "shadowsocks":
        return _build_shadowsocks(params, tag)
    if proto == "tuic":
        return _build_tuic(params, tag)
    if proto == "shadowtls":
        return _build_shadowtls(params, tag)

    # По умолчанию фоллбэк на direct
    return {"type": "direct", "tag": tag}
