import sys
import os
import json
import re
import socket
import time
import subprocess
import requests
import asyncio
from fastapi import APIRouter, Request
from backend.auth_utils import check_auth, decoy_response
from backend.database import get_outbound_by_id
from backend.xray import XRAY_BIN_PATH, BIN_DIR, clean_stream_settings
from backend.i18n import t, get_lang

router = APIRouter()

def extract_address_port(protocol: str, settings: dict, stream_settings: dict = None) -> tuple:
    from backend.adapters import extract_common_outbound_params
    params = extract_common_outbound_params(settings, stream_settings or {})
    return params.get("address"), params.get("port")

def system_ping(host: str, timeout: float = 3.0, lang: str = "ru") -> dict:
    if not host:
        return {"success": False, "msg": t("testing_address_not_specified", lang=lang, category="backend")}
        
    try:
        if sys.platform == "win32":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), host]
            
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
            
        start_time = time.perf_counter()
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout + 1.0,
            creationflags=creationflags
        )
        latency = (time.perf_counter() - start_time) * 1000
        
        if res.returncode == 0:
            match = re.search(r"(?:time|время)[=<]([\d\.]+)\s*(?:ms|мс)?", res.stdout, re.IGNORECASE)
            if match:
                try:
                    parsed_latency = float(match.group(1))
                    return {"success": True, "ping": round(parsed_latency, 2)}
                except ValueError:
                    pass
            return {"success": True, "ping": round(latency, 2)}
        else:
            err_msg = res.stderr.strip() if res.stderr else res.stdout.strip()
            if "not found" in err_msg or "not recognized" in err_msg or "не является внутренней" in err_msg:
                return {"success": False, "msg": t("testing_ping_not_installed", lang=lang, category="backend", error=err_msg)}
            return {"success": False, "msg": t("testing_host_unreachable", lang=lang, category="backend")}
    except subprocess.TimeoutExpired:
        return {"success": False, "msg": t("testing_timeout", lang=lang, category="backend")}
    except Exception as e:
        return {"success": False, "msg": t("testing_ping_error", lang=lang, category="backend", error=str(e))}

def tcp_ping(host: str, port: int, timeout: float = 4.0, lang: str = "ru") -> dict:
    if not host or port is None:
        return {"success": False, "msg": t("testing_address_or_port_not_specified", lang=lang, category="backend")}
    
    try:
        from backend.sentinel_core_bridge import ping_host
        res = ping_host(host, int(port), int(timeout * 1000))
        if res.get("success"):
            return {"success": True, "ping": round(float(res.get("latencyMs", 0.0)), 2)}
        elif res.get("error"):
            return {"success": False, "msg": t("testing_connection_error", lang=lang, category="backend", error=res.get("error"))}
    except Exception:
        pass

    start_time = time.perf_counter()
    try:
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror as e:
            return {"success": False, "msg": t("testing_dns_resolution_error", lang=lang, category="backend", error=str(e))}
            
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, int(port)))
        sock.close()
        
        latency = (time.perf_counter() - start_time) * 1000
        return {"success": True, "ping": round(latency, 2)}
    except socket.timeout:
        return {"success": False, "msg": t("testing_timeout", lang=lang, category="backend")}
    except Exception as e:
        return {"success": False, "msg": t("testing_connection_error", lang=lang, category="backend", error=str(e))}

def test_outbound_transit(protocol: str, settings: dict, stream_settings: dict = None, core: str = "auto", lang: str = "ru", **kwargs) -> dict:
    def get_free_port():
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def wait_for_port(port, timeout=2.0):
        start = time.time()
        while time.time() - start < timeout:
            try:
                s = socket.create_connection(('127.0.0.1', port), timeout=0.1)
                s.close()
                return True
            except Exception:
                time.sleep(0.05)
        return False

    free_port = get_free_port()
    temp_config_path = BIN_DIR / f"temp_test_config_{free_port}.json"
    
    from backend.adapters import detect_best_engine, build_outbound_config
    target_engine = detect_best_engine(protocol, core)
    use_singbox = (target_engine == "sing-box")
    if use_singbox:
        from backend.config import SINGBOX_BIN_PATH
        from backend.singbox import ensure_singbox_installed
        try:
            ensure_singbox_installed()
        except Exception:
            pass

        singbox_outbound = build_outbound_config("sing-box", protocol, settings, stream_settings, tag="test-out")

        config = {
            "log": {
                "level": "warn"
            },
            "inbounds": [
                {
                    "type": "http",
                    "tag": "http-in",
                    "listen": "127.0.0.1",
                    "listen_port": free_port
                }
            ],
            "outbounds": [
                singbox_outbound,
                {
                    "type": "direct",
                    "tag": "direct"
                }
            ],
            "route": {
                "rules": [
                    {
                        "inbound": ["http-in"],
                        "outbound": "test-out"
                    }
                ]
            }
        }
        cmd = [str(SINGBOX_BIN_PATH), "run", "-c", str(temp_config_path)]
        core_name = "Sing-box"
    else:
        xray_outbound = build_outbound_config("xray", protocol, settings, stream_settings, tag="test-out")
        config = {
            "log": {"loglevel": "warning"},
            "inbounds": [{
                "listen": "127.0.0.1",
                "port": free_port,
                "protocol": "http",
                "settings": {"timeout": 10},
                "tag": "http-in"
            }],
            "outbounds": [
                xray_outbound,
                {"protocol": "freedom", "tag": "direct"}
            ],
            "routing": {
                "rules": [{
                    "type": "field",
                    "inboundTag": ["http-in"],
                    "outboundTag": "test-out"
                }]
            }
        }
        core_name = "Xray"
    
    try:
        with open(temp_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        return {"success": False, "msg": t("testing_create_test_file_error", lang=lang, category="backend", error=str(e))}
        
    try:
        from backend.sentinel_core_bridge import start_core, stop_core
        bin_path = str(SINGBOX_BIN_PATH) if use_singbox else str(XRAY_BIN_PATH)
        core_type = "sing-box" if use_singbox else "xray"

        start_core(core_type, bin_path, str(temp_config_path))
        
        if not wait_for_port(free_port, timeout=3.0):
            stop_core(core_type)
            return {"success": False, "msg": t("testing_launch_core_failed", lang=lang, category="backend", core=core_name)}
            
        proxies = {
            "http": f"http://127.0.0.1:{free_port}",
            "https": f"http://127.0.0.1:{free_port}"
        }
        
        test_urls = [
            "https://www.gstatic.com/generate_204",
            "https://cp.cloudflare.com/generate_204",
            "http://connectivitycheck.gstatic.com/generate_204"
        ]

        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        session = requests.Session()
        session.proxies.update(proxies)
        
        last_error = None
        last_status = None
        for target_url in test_urls:
            try:
                # 1. Initial warm-up request to initialize proxy tunnel & SSL handshake
                warmup_ok = False
                try:
                    w_resp = session.get(target_url, timeout=3.0, verify=False)
                    if w_resp.status_code in (200, 204):
                        warmup_ok = True
                    else:
                        last_status = w_resp.status_code
                except requests.exceptions.RequestException as we:
                    last_error = str(we)

                if not warmup_ok:
                    continue

                # 2. Precise measurement over active warm tunnel
                start_time = time.perf_counter()
                resp = session.get(target_url, timeout=3.0, verify=False)
                latency = (time.perf_counter() - start_time) * 1000

                if resp.status_code in (200, 204):
                    return {
                        "success": True,
                        "ping": round(latency, 2),
                        "msg": t("testing_transit_working", lang=lang, category="backend", core=core_name, latency=round(latency, 1)),
                        "core": core_name
                    }
                else:
                    last_status = resp.status_code
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                
        detail_msg = ""
        try:
            from backend.sentinel_core_bridge import get_in_memory_core_logs
            logs = get_in_memory_core_logs(core_type, limit=5)
            err_lines = [line for line in logs if any(w in line.lower() for w in ("error", "fail", "refused", "timeout", "bad certificate", "auth", "rejected"))]
            if err_lines:
                clean_err = re.sub(r'(\x1b\[[0-9;]*[a-zA-Z]|\[\d+m|\[\d+;\d+;\d+m)', '', err_lines[-1]).strip()
                detail_msg = f": {clean_err}"
        except Exception:
            pass

        if last_status == 502:
            return {"success": False, "msg": f"{t('testing_gateway_error_502', lang=lang, category='backend', core=core_name)}{detail_msg}"}
        elif last_status == 504:
            return {"success": False, "msg": f"{t('testing_gateway_timeout_504', lang=lang, category='backend', core=core_name)}{detail_msg}"}
        elif last_status:
            return {"success": False, "msg": f"{t('testing_unexpected_status', lang=lang, category='backend', status=last_status, core=core_name)}{detail_msg}"}
        else:
            return {"success": False, "msg": f"{t('testing_transit_check_error', lang=lang, category='backend', error=last_error or 'Connection timeout', core=core_name)}{detail_msg}"}
            
    finally:
        try:
            from backend.sentinel_core_bridge import stop_core
            core_type = "sing-box" if use_singbox else "xray"
            stop_core(core_type)
        except Exception:
            pass
        if temp_config_path.exists():
            try:
                os.remove(temp_config_path)
            except Exception:
                pass

@router.post("/api/routing/outbounds/test")
async def test_outbound_api(request: Request, payload: dict):
    """Tests an outbound connectivity without saving it (TCP ping or HTTP transit proxy check)."""
    if not check_auth(request):
        return decoy_response()
        
    lang = get_lang(request)
    protocol = payload.get("protocol", "").strip()
    settings = payload.get("settings", {})
    stream_settings = payload.get("streamSettings", {})
    test_type = payload.get("test_type", "tcp").strip().lower()
    core = payload.get("core") or payload.get("engine") or "auto"
    
    if protocol == "blackhole":
        return {"success": True, "ping": 0, "msg": t("testing_blackhole_active", lang=lang, category="backend")}
        
    import backend.routes.routing as routing_facade
    
    if test_type == "http":
        if protocol == "freedom":
            start_time = time.perf_counter()
            try:
                resp = requests.get("https://www.gstatic.com/generate_204", timeout=3.0, verify=False)
                latency = (time.perf_counter() - start_time) * 1000
                if resp.status_code in (200, 204):
                    return {"success": True, "ping": round(latency, 2), "msg": t("testing_direct_working", lang=lang, category="backend")}
                else:
                    return {"success": False, "msg": t("testing_unexpected_status_simple", lang=lang, category="backend", status=resp.status_code)}
            except Exception as e:
                return {"success": False, "msg": t("testing_connection_exception", lang=lang, category="backend", error=str(e))}
                
        if core and core != "auto":
            return routing_facade.test_outbound_transit(protocol, settings, stream_settings, core=core)
        return routing_facade.test_outbound_transit(protocol, settings, stream_settings)
        
    else:  # TCP Ping
        if protocol == "freedom":
            res = routing_facade.tcp_ping("8.8.8.8", 53, 3.0)
            if res["success"]:
                return {"success": True, "ping": res["ping"], "msg": t("testing_direct_available", lang=lang, category="backend")}
            else:
                return {"success": False, "msg": t("testing_direct_unavailable", lang=lang, category="backend", error=res['msg'])}
                
        if protocol.lower() in ("hysteria", "hysteria2", "hy2", "tuic", "wireguard"):
            host, port = extract_address_port(protocol, settings, stream_settings)
            if not host:
                return {"success": False, "msg": t("testing_cannot_determine_address_proto", lang=lang, category="backend")}
            return routing_facade.system_ping(host)
            
        host, port = extract_address_port(protocol, settings, stream_settings)
        if not host or not port:
            return {"success": False, "msg": t("testing_cannot_determine_address_port_proto", lang=lang, category="backend")}
            
        res = routing_facade.tcp_ping(host, port)
        return res

@router.post("/api/routing/outbounds/test/{id}")
async def test_outbound_by_id_api(request: Request, id: int, test_type: str = "tcp", core: str = "auto"):
    """Tests a saved outbound connectivity by database configuration ID."""
    if not check_auth(request):
        return decoy_response()
        
    lang = get_lang(request)
    ob = get_outbound_by_id(id)
    if not ob:
        return {"success": False, "msg": t("testing_outbound_not_found", lang=lang, category="backend")}
        
    protocol = ob.get("protocol", "")
    ob_core = ob.get("core") or ob.get("engine")
    if core == "auto" and ob_core:
        core = ob_core

    try:
        settings = json.loads(ob.get("settings") or "{}")
    except Exception:
        settings = {}
    try:
        stream_settings = json.loads(ob.get("stream_settings") or "{}")
    except Exception:
        stream_settings = {}
        
    test_type = test_type.strip().lower()
    
    if protocol == "blackhole":
        return {"success": True, "ping": 0, "msg": t("testing_blackhole_active", lang=lang, category="backend")}
        
    import backend.routes.routing as routing_facade
    
    if test_type == "http":
        if protocol == "freedom":
            start_time = time.perf_counter()
            try:
                resp = requests.get("https://www.gstatic.com/generate_204", timeout=3.0, verify=False)
                latency = (time.perf_counter() - start_time) * 1000
                if resp.status_code in (200, 204):
                    return {"success": True, "ping": round(latency, 2), "msg": t("testing_direct_working", lang=lang, category="backend")}
                else:
                    return {"success": False, "msg": t("testing_unexpected_status_simple", lang=lang, category="backend", status=resp.status_code)}
            except Exception as e:
                return {"success": False, "msg": t("testing_connection_exception", lang=lang, category="backend", error=str(e))}
                
        if core and core != "auto":
            return routing_facade.test_outbound_transit(protocol, settings, stream_settings, core=core)
        return routing_facade.test_outbound_transit(protocol, settings, stream_settings)
        
    else:  # TCP/ICMP Ping
        if protocol == "freedom":
            res = routing_facade.tcp_ping("8.8.8.8", 53, 3.0)
            if res["success"]:
                return {"success": True, "ping": res["ping"], "msg": t("testing_direct_available", lang=lang, category="backend")}
            else:
                return {"success": False, "msg": t("testing_direct_unavailable", lang=lang, category="backend", error=res['msg'])}
                
        if protocol.lower() in ("hysteria", "hysteria2", "hy2", "tuic", "wireguard"):
            host, port = extract_address_port(protocol, settings, stream_settings)
            if not host:
                return {"success": False, "msg": t("testing_cannot_determine_address", lang=lang, category="backend")}
            return routing_facade.system_ping(host)
            
        host, port = extract_address_port(protocol, settings, stream_settings)
        if not host or not port:
            return {"success": False, "msg": t("testing_cannot_determine_address_port", lang=lang, category="backend")}
            
        res = routing_facade.tcp_ping(host, port)
        return res

@router.post("/api/routing/outbounds/generate-warp")
async def generate_warp_api(request: Request):
    """Registers and generates a Cloudflare WARP account profile config."""
    if not check_auth(request):
        return decoy_response()
        
    lang = get_lang(request)
    from backend.utils.warp import register_warp
    
    warp_data = await asyncio.to_thread(register_warp)
    if not warp_data:
        return {"success": False, "msg": t("testing_warp_register_failed", lang=lang, category="backend")}
        
    return {"success": True, "obj": warp_data}
