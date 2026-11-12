from typing import Any, Dict, List

from .params import (
    extract_common_outbound_params,
    extract_fingerprint,
    extract_reality_creds,
    parse_alpn_list,
    parse_json_or_dict,
)


def _extract_host_from_transport(transport_cfg: Dict[str, Any]) -> str:
    ws_headers = transport_cfg.get("headers") or {}
    header_host = ws_headers.get("Host") if isinstance(ws_headers, dict) else ""
    return transport_cfg.get("host") or header_host or ""


def _build_host_path_settings(raw_stream: Dict[str, Any], ws_fallback: Dict[str, Any], key: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
    cfg = raw_stream.get(key) or ws_fallback
    out: Dict[str, Any] = {"path": cfg.get("path") or "/"}
    if extra:
        out.update(extra)
    host_val = _extract_host_from_transport(cfg)
    if host_val:
        out["host"] = host_val
    return out


def _build_xray_stream_settings(params: dict) -> dict:
    """Строит streamSettings для Xray (транспорт, TLS, Reality) для VLESS, VMess и Trojan."""
    raw_stream = params["raw_stream_settings"]
    network = params["network"] or "tcp"
    security = params["security"] or "none"

    stream_settings_out: Dict[str, Any] = {
        "network": network,
        "security": security,
    }

    if security == "reality":
        pbk, sid, spx = extract_reality_creds(params["reality_settings"])
        stream_settings_out["realitySettings"] = {
            "serverName": params["sni"],
            "fingerprint": extract_fingerprint(params, default="chrome"),
            "show": False,
            "publicKey": pbk,
            "shortId": sid,
            "spiderX": spx,
        }
    elif security == "tls":
        tls_set = params["tls_settings"]
        fp = tls_set.get("fingerprint") or tls_set.get("fp") or "chrome"
        tls_out: Dict[str, Any] = {
            "serverName": params["sni"],
            "fingerprint": fp,
        }
        alpn_list = parse_alpn_list(tls_set.get("alpn"))
        if alpn_list:
            tls_out["alpn"] = alpn_list
        stream_settings_out["tlsSettings"] = tls_out

    if network == "tcp":
        tcp_set = raw_stream.get("tcpSettings") or raw_stream.get("tcp_settings")
        if isinstance(tcp_set, dict) and tcp_set:
            stream_settings_out["tcpSettings"] = tcp_set
    elif network == "ws":
        ws_set = params["ws_settings"]
        stream_settings_out["wsSettings"] = {
            "path": ws_set.get("path") or "/",
            "headers": ws_set.get("headers") or {},
        }
    elif network == "httpupgrade":
        stream_settings_out["httpupgradeSettings"] = _build_host_path_settings(
            raw_stream, params["ws_settings"], "httpupgradeSettings"
        )
    elif network in ("xhttp", "splithttp"):
        xh_set = raw_stream.get("xhttpSettings") or params["ws_settings"]
        stream_settings_out["xhttpSettings"] = _build_host_path_settings(
            raw_stream, params["ws_settings"], "xhttpSettings", {"mode": xh_set.get("mode") or "auto"}
        )
    elif network in ("h2", "http"):
        h2_set = raw_stream.get("httpSettings") or params["ws_settings"]
        h2_host: Any = h2_set.get("host")
        if isinstance(h2_host, str) and h2_host:
            h2_host = [h2_host]
        elif not h2_host:
            header_host = _extract_host_from_transport(h2_set)
            if header_host:
                h2_host = [header_host]
        http_out: Dict[str, Any] = {"path": h2_set.get("path") or "/"}
        if h2_host:
            http_out["host"] = h2_host
        stream_settings_out["httpSettings"] = http_out
    elif network == "grpc":
        grpc_set = params["grpc_settings"]
        grpc_out: Dict[str, Any] = {
            "serviceName": grpc_set.get("serviceName") or grpc_set.get("service_name") or "grpc"
        }
        if grpc_set.get("multiMode") or grpc_set.get("multi_mode"):
            grpc_out["multiMode"] = True
        stream_settings_out["grpcSettings"] = grpc_out

    return stream_settings_out


def build_xray_outbound(protocol: str, settings: dict, stream_settings: dict = None, tag: str = "test-out") -> dict:
    """Строит структуру исходящего подключения для ядра Xray."""
    params = extract_common_outbound_params(settings, stream_settings or {})
    proto = (protocol or "").strip().lower()

    if proto in ("hysteria", "hysteria2"):
        return {
            "protocol": "hysteria",
            "settings": {
                "version": 2,
                "servers": [
                    {
                        "address": params["address"],
                        "port": params["port"],
                        "password": params["password"],
                    }
                ],
            },
            "tag": tag,
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
                            "flow": params["flow"],
                        }
                    ],
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

        return {
            "protocol": "vless",
            "settings": xray_settings,
            "streamSettings": clean_stream_settings(_build_xray_stream_settings(params)),
            "tag": tag,
        }

    if proto == "vmess":
        return {
            "protocol": "vmess",
            "settings": {
                "vnext": [
                    {
                        "address": params["address"],
                        "port": params["port"],
                        "users": [{"id": params["uuid"] or params["password"], "security": "auto"}],
                    }
                ]
            },
            "streamSettings": clean_stream_settings(_build_xray_stream_settings(params)),
            "tag": tag,
        }

    if proto == "trojan":
        return {
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": params["address"],
                        "port": params["port"],
                        "password": params["password"] or params["uuid"],
                    }
                ]
            },
            "streamSettings": clean_stream_settings(_build_xray_stream_settings(params)),
            "tag": tag,
        }

    if proto in ("shadowsocks", "ss"):
        return {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [
                    {
                        "address": params["address"],
                        "port": params["port"],
                        "password": params["password"],
                        "method": params["raw_settings"].get("method") or "2022-blake3-aes-128-gcm",
                    }
                ]
            },
            "tag": tag,
        }

    if proto in ("socks", "http"):
        users: List[Dict[str, str]] = []
        if params["username"] or params["password"]:
            users.append({"user": params["username"], "pass": params["password"]})
        return {
            "protocol": proto,
            "settings": {
                "servers": [
                    {
                        "address": params["address"],
                        "port": params["port"],
                        "users": users,
                    }
                ]
            },
            "tag": tag,
        }

    if proto in ("freedom", "direct"):
        return {"protocol": "freedom", "settings": {"domainStrategy": "AsIs"}, "tag": tag}

    if proto in ("blackhole", "block"):
        return {"protocol": "blackhole", "settings": {"response": {"type": "none"}}, "tag": tag}

    # Для остальных протоколов Xray используем сырые настройки с очисткой
    outbound: Dict[str, Any] = {
        "protocol": proto,
        "settings": parse_json_or_dict(settings),
        "tag": tag,
    }
    if stream_settings:
        outbound["streamSettings"] = clean_stream_settings(parse_json_or_dict(stream_settings))
    return outbound
