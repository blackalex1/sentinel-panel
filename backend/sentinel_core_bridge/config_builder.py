import json
import logging
import os
import tempfile
from typing import Dict, Any, List, Optional

from backend.sentinel_core_bridge.ffi import (
    _ffi_call_json,
    run_core_command,
)

logger = logging.getLogger(__name__)


def build_server_config(
    target_core: str,
    server_inbounds: List[Dict[str, Any]],
    routing: Optional[Dict[str, Any]] = None,
    clash_api: str = "",
    log_path: str = "",
    log_level: str = "",
    access_log: str = "",
    error_log: str = ""
) -> Dict[str, Any]:
    """Compiles complete core configuration (Xray, Sing-box, Hysteria 2) via sentinel-core AST engine."""
    spec = {
        "targetCore": target_core,
        "serverInbounds": server_inbounds,
        "routing": routing or {},
        "clashApiAddress": clash_api,
        "logPath": log_path,
        "logLevel": log_level,
        "accessLog": access_log,
        "errorLog": error_log
    }
    input_json = json.dumps(spec)

    try:
        res = _ffi_call_json("SentinelBuildServerConfig", input_json)
        if isinstance(res, dict):
            if "error" in res:
                return {"error": res["error"]}
            if "config" in res:
                cfg_str = res["config"]
                try:
                    return json.loads(cfg_str)
                except (json.JSONDecodeError, TypeError):
                    return {"raw": cfg_str}
    except Exception as e:
        logger.debug("FFI build_server_config error: %s", e)

    return run_core_command(["compile-server"], input_data=input_json)


def compile_node_server_config(target_core: str) -> Dict[str, Any]:
    """Compiles complete server config for any core (xray, sing-box, hysteria2) from DB via sentinel-core AST."""
    try:
        from backend.database import get_all_inbounds, get_clients_for_inbound, get_all_outbounds, get_all_routing_rules
        
        if target_core == "xray":
            import backend.xray.config as xray_cfg_mod
            get_inbounds_fn = getattr(xray_cfg_mod, "get_all_inbounds", None) or get_all_inbounds
            get_clients_fn = getattr(xray_cfg_mod, "get_clients_for_inbound", None) or get_clients_for_inbound
            get_outbounds_fn = getattr(xray_cfg_mod, "get_all_outbounds", None) or get_all_outbounds
            get_rules_fn = getattr(xray_cfg_mod, "get_all_routing_rules", None) or get_all_routing_rules
        elif target_core in ("singbox", "sing-box"):
            import backend.singbox.config as sb_cfg_mod
            get_inbounds_fn = getattr(sb_cfg_mod, "get_all_inbounds", None) or get_all_inbounds
            get_clients_fn = getattr(sb_cfg_mod, "get_clients_for_inbound", None) or get_clients_for_inbound
            get_outbounds_fn = getattr(sb_cfg_mod, "get_all_outbounds", None) or get_all_outbounds
            get_rules_fn = getattr(sb_cfg_mod, "get_all_routing_rules", None) or get_all_routing_rules
        else:
            get_inbounds_fn = get_all_inbounds
            get_clients_fn = get_clients_for_inbound
            get_outbounds_fn = get_all_outbounds
            get_rules_fn = get_all_routing_rules

        inbounds = get_inbounds_fn()
        outbounds = get_outbounds_fn()
        rules = get_rules_fn()
        
        hysteria_outbound_tags = {
            ob.get("tag") for ob in outbounds
            if ob.get("protocol") in ("hysteria", "hysteria2") and ob.get("tag")
        }
        standard_inbound_tags = [
            ib.get("tag") or f"inbound-{ib['id']}"
            for ib in inbounds
            if ib.get("protocol") != "hysteria2" and ib.get("enable", 1)
        ]

        server_inbounds = []
        for ib in inbounds:
            if not ib.get("enable", 1):
                continue
            
            ib_core = ib.get("core") or ("hysteria" if ib["protocol"] == "hysteria2" else "xray")
            
            # Isolation check
            if target_core == "xray":
                if ib_core == "singbox" or ib_core == "sing-box":
                    continue
                if ib.get("protocol") == "hysteria2":
                    str_settings = ib.get("stream_settings")
                    if isinstance(str_settings, str):
                        try:
                            str_settings = json.loads(str_settings)
                        except Exception:
                            str_settings = {}
                    elif not isinstance(str_settings, dict):
                        str_settings = {}
                    hys_conf = str_settings.get("hysteria", {})
                    if hys_conf.get("routingViaXray") or str_settings.get("routing_via_xray"):
                        socks_user = hys_conf.get("socksUsername", "")
                        socks_pass = hys_conf.get("socksPassword", "")
                        server_inbounds.append({
                            "id": ib["id"],
                            "port": 20000 + ib["id"],
                            "protocol": "socks",
                            "tag": f"inbound-{ib['id']}-socks",
                            "listenAddress": "127.0.0.1",
                            "core": "xray",
                            "sniffing": {
                                "enabled": True,
                                "destOverride": ["http", "tls", "quic"],
                                "routeOnly": False
                            },
                            "settings": {
                                "udp": True,
                                "auth": "password" if socks_user else "noauth",
                                "accounts": [{"user": socks_user, "pass": socks_pass}] if socks_user else []
                            }
                        })
                    continue
            elif target_core in ("singbox", "sing-box"):
                if ib_core == "xray" or ib_core == "hysteria":
                    continue
            
            ib_tag = ib.get("tag") or f"inbound-{ib['id']}"
            clients = get_clients_fn(ib["id"]) if get_clients_fn else []
            
            ib_spec = {
                "id": ib["id"],
                "port": ib["port"],
                "protocol": ib["protocol"],
                "tag": ib_tag,
                "core": ib_core
            }
            try:
                ib_spec["settings"] = json.loads(ib.get("settings") or "{}") if isinstance(ib.get("settings"), str) else (ib.get("settings") or {})
            except Exception:
                ib_spec["settings"] = {}
            try:
                ib_spec["streamSettings"] = json.loads(ib.get("stream_settings") or "{}") if isinstance(ib.get("stream_settings"), str) else (ib.get("stream_settings") or {})
            except Exception:
                ib_spec["streamSettings"] = {}
            try:
                ib_spec["sniffing"] = json.loads(ib.get("sniffing") or "{}") if isinstance(ib.get("sniffing"), str) else (ib.get("sniffing") or {})
            except Exception:
                ib_spec["sniffing"] = {}
                
            if ib.get("protocol") == "vless":
                if isinstance(ib_spec.get("settings"), dict):
                    dec = ib_spec["settings"].get("decryption", "none")
                    if not (isinstance(dec, str) and dec.startswith("mlkem768x25519plus.")):
                        ib_spec["settings"]["decryption"] = "none"
                    ib_spec["settings"].pop("encryption", None)

            if "fallbacks" in ib_spec["settings"]:
                ib_spec["fallbacks"] = ib_spec["settings"]["fallbacks"]
            elif ib.get("protocol") == "vless" and ib_spec.get("streamSettings", {}).get("security") == "tls":
                from backend.config import settings as app_settings
                p_port = getattr(app_settings, "PANEL_PORT", 8000)
                from backend.database import get_setting
                if get_setting("decoy_type"):
                    ib_spec["settings"]["fallbacks"] = [{"dest": p_port}]
                
            if clients:
                raw_clients_map = {}
                if isinstance(ib_spec.get("settings"), dict):
                    for rc in ib_spec["settings"].get("clients", []):
                        if isinstance(rc, dict):
                            if rc.get("email"):
                                raw_clients_map[rc["email"]] = rc
                            if rc.get("id"):
                                raw_clients_map[rc["id"]] = rc

                client_list = []
                for c in clients:
                    if not c.get("enable", 1):
                        continue
                    email = c.get("email", "")
                    uid = c.get("client_uuid_or_pwd", "")
                    raw_c = raw_clients_map.get(email) or raw_clients_map.get(uid) or {}
                    
                    flow = c.get("flow") or raw_c.get("flow") or (ib_spec.get("settings", {}) if isinstance(ib_spec.get("settings"), dict) else {}).get("flow", "")
                    
                    client_entry = {
                        "id": uid,
                        "uuid": uid,
                        "password": uid,
                        "email": email,
                        "enable": True
                    }
                    if flow:
                        client_entry["flow"] = flow
                    if raw_c.get("alterId") is not None:
                        client_entry["alterId"] = raw_c["alterId"]
                    if raw_c.get("security"):
                        client_entry["security"] = raw_c["security"]
                        
                    client_list.append(client_entry)

                ib_spec["clients"] = client_list
                ib_spec["settings"]["clients"] = client_list

                if ib.get("protocol") == "shadowsocks" and client_list:
                    ss_pwd = client_list[0].get("password") or client_list[0].get("id") or client_list[0].get("uuid")
                    if ss_pwd:
                        ib_spec["settings"]["password"] = ss_pwd
                    method = str(ib_spec["settings"].get("method", ""))
                    if target_core == "xray" and not method.startswith("2022-"):
                        ib_spec["settings"].pop("clients", None)
            server_inbounds.append(ib_spec)
            
        compiled_rules = []
        for r in rules:
            r_inbound_tags = json.loads(r.get("inbound_tags") or "[]") if isinstance(r.get("inbound_tags"), str) else (r.get("inbound_tags") or [])
            if target_core == "xray" and r.get("outbound_tag") in hysteria_outbound_tags and not r_inbound_tags:
                r_inbound_tags = standard_inbound_tags

            outbound_tag = r.get("outbound_tag", "direct")
            if target_core in ("singbox", "sing-box") and outbound_tag == "blocked":
                outbound_tag = "block"
            elif target_core == "xray" and outbound_tag == "block":
                outbound_tag = "blocked"
            
            compiled_rules.append({
                "id": r.get("id"),
                "remark": r.get("remark", ""),
                "outboundTag": outbound_tag,
                "domains": json.loads(r.get("domains") or "[]") if isinstance(r.get("domains"), str) else (r.get("domains") or []),
                "ips": json.loads(r.get("ips") or r.get("ip") or "[]") if isinstance(r.get("ips") or r.get("ip"), str) else (r.get("ips") or r.get("ip") or []),
                "protocols": json.loads(r.get("protocols") or "[]") if isinstance(r.get("protocols"), str) else (r.get("protocols") or []),
                "users": json.loads(r.get("users") or "[]") if isinstance(r.get("users"), str) else (r.get("users") or []),
                "inboundTags": r_inbound_tags,
                "enable": bool(r.get("enable", 1)),
                "sortOrder": r.get("sort_order", 0)
            })

        referenced_outbounds = {r.get("outboundTag") for r in compiled_rules if r.get("enable", True)}
        
        added_new = True
        while added_new:
            added_new = False
            for ob in outbounds:
                if not ob.get("enable", 1):
                    continue
                tag = ob.get("tag", "")
                if tag in referenced_outbounds:
                    ob_settings = ob.get("settings", {})
                    if isinstance(ob_settings, str):
                        try:
                            ob_settings = json.loads(ob_settings or "{}")
                        except Exception:
                            ob_settings = {}
                    if isinstance(ob_settings, dict):
                        backups = ob_settings.get("backup_outbounds") or []
                        if isinstance(backups, str):
                            backups = [backups]
                        fallback_single = ob_settings.get("fallback_outbound")
                        if fallback_single and fallback_single not in backups:
                            backups = list(backups) + [fallback_single]
                        for b in backups:
                            if b and b not in referenced_outbounds:
                                referenced_outbounds.add(b)
                                added_new = True
        
        direct_ob = None
        block_ob = None
        custom_obs = []
        
        for ob in outbounds:
            if not ob.get("enable", 1):
                continue
            tag = ob.get("tag", "")
            proto = (ob.get("protocol") or "").lower()
            if tag == "direct" or proto in ("freedom", "direct"):
                if not direct_ob:
                    direct_ob = {"tag": "direct", "protocol": "freedom", "settings": {}, "stream_settings": {}, "streamSettings": {}}
            elif tag in ("blocked", "block") or proto in ("blackhole", "block"):
                if not block_ob:
                    tag_name = "block" if target_core in ("singbox", "sing-box") else "blocked"
                    proto_name = "block" if target_core in ("singbox", "sing-box") else "blackhole"
                    block_ob = {"tag": tag_name, "protocol": proto_name, "settings": {}, "stream_settings": {}, "streamSettings": {}}
            else:
                if tag in referenced_outbounds:
                    ob_dict = dict(ob)
                    ob_settings = ob_dict.get("settings", {})
                    if isinstance(ob_settings, str):
                        try:
                            ob_settings = json.loads(ob_settings or "{}")
                        except Exception:
                            ob_settings = {}
                    ob_dict["settings"] = ob_settings

                    ob_stream = ob_dict.get("stream_settings", {})
                    if isinstance(ob_stream, str):
                        try:
                            ob_stream = json.loads(ob_stream or "{}")
                        except Exception:
                            ob_stream = {}
                    ob_dict["streamSettings"] = ob_stream
                    ob_dict["stream_settings"] = ob_stream
                    custom_obs.append(ob_dict)
                    
        sorted_outbounds = []
        if not direct_ob:
            direct_ob = {"tag": "direct", "protocol": "freedom", "settings": {}, "streamSettings": {}}
        if not block_ob:
            tag_name = "block" if target_core in ("singbox", "sing-box") else "blocked"
            proto_name = "block" if target_core in ("singbox", "sing-box") else "blackhole"
            block_ob = {"tag": tag_name, "protocol": proto_name, "settings": {}, "streamSettings": {}}
            
        sorted_outbounds.append(direct_ob)
        sorted_outbounds.append(block_ob)
        sorted_outbounds.extend(custom_obs)

        routing_spec = {
            "rules": compiled_rules,
            "outbounds": sorted_outbounds
        }
        
        clash_api = "127.0.0.1:9090" if target_core in ("singbox", "sing-box") else ""
        from backend.database import get_setting
        log_path = ""
        
        setting_key = "xray_loglevel" if target_core == "xray" else ("singbox_loglevel" if target_core in ("singbox", "sing-box") else "hysteria_loglevel")
        db_lvl = (get_setting(setting_key) or "").lower()
        if db_lvl not in ("trace", "debug", "info", "warn", "warning", "error"):
            db_lvl = "info"
        log_level = db_lvl
        
        access_log = get_setting("xray_access_log") or ""
        error_log = get_setting("xray_error_log") or ""
        
        return build_server_config(
            target_core,
            server_inbounds,
            routing_spec,
            clash_api,
            log_path=log_path,
            log_level=log_level,
            access_log=access_log,
            error_log=error_log
        )
    except Exception as e:
        logger.exception("Error compiling server config via sentinel-core: %s", e)
        return {}


def build_failover_client_config(
    profiles: List[Dict[str, Any]],
    socks_port: int = 10808,
    http_port: int = 10809,
    health_url: str = "https://api.telegram.org"
) -> Optional[str]:
    """Generates complete Sing-box client JSON config with SOCKS5/HTTP inbound and multi-node failover."""
    if not profiles:
        return None

    profiles_json = json.dumps(profiles)
    try:
        res = _ffi_call_json(
            "SentinelBuildFailoverClientConfig",
            profiles_json,
            "singbox",
            int(socks_port),
            int(http_port),
            health_url
        )
        if isinstance(res, dict) and res.get("configJson"):
            return res["configJson"]
    except Exception as e:
        logger.debug("FFI SentinelBuildFailoverClientConfig error: %s", e)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(profiles_json)
        tmp_name = f.name

    try:
        args = [
            "build-failover",
            "--file", tmp_name,
            "--core", "singbox",
            "--socks", str(socks_port),
            "--http", str(http_port),
            "--url", health_url
        ]
        res = run_core_command(args, parse_json=False)
        if res and isinstance(res, str) and ("inbounds" in res or "outbounds" in res):
            return res
    finally:
        try:
            os.remove(tmp_name)
        except Exception:
            pass
    return None
