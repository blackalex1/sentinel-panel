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

router = APIRouter()

def extract_address_port(protocol: str, settings: dict, stream_settings: dict = None) -> tuple:
    from backend.adapters import extract_common_outbound_params
    params = extract_common_outbound_params(settings, stream_settings or {})
    return params.get("address"), params.get("port")

def system_ping(host: str, timeout: float = 3.0) -> dict:
    if not host:
        return {"success": False, "msg": "Не указан адрес"}
        
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
                return {"success": False, "msg": f"Утилита ping не установлена в системе: {err_msg}"}
            return {"success": False, "msg": "Хост недоступен (Ping не прошел)"}
    except subprocess.TimeoutExpired:
        return {"success": False, "msg": "Превышено время ожидания (Timeout)"}
    except Exception as e:
        return {"success": False, "msg": f"Ошибка ping: {str(e)}"}

def tcp_ping(host: str, port: int, timeout: float = 4.0) -> dict:
    if not host or port is None:
        return {"success": False, "msg": "Не указан адрес или порт"}
    
    start_time = time.perf_counter()
    try:
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror as e:
            return {"success": False, "msg": f"Ошибка разрешения DNS: {e}"}
            
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, int(port)))
        sock.close()
        
        latency = (time.perf_counter() - start_time) * 1000
        return {"success": True, "ping": round(latency, 2)}
    except socket.timeout:
        return {"success": False, "msg": "Превышено время ожидания (Timeout)"}
    except Exception as e:
        return {"success": False, "msg": f"Ошибка подключения: {str(e)}"}

def test_outbound_transit(protocol: str, settings: dict, stream_settings: dict = None, core: str = "auto", **kwargs) -> dict:
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
    if target_engine == "sing-box":
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
            "log": {
                "loglevel": "warning"
            },
            "inbounds": [
                {
                    "listen": "127.0.0.1",
                    "port": free_port,
                    "protocol": "http",
                    "settings": {
                        "timeout": 10
                    },
                    "tag": "http-in"
                }
            ],
            "outbounds": [
                xray_outbound,
                {
                    "protocol": "freedom",
                    "tag": "direct"
                }
            ],
            "routing": {
                "rules": [
                    {
                        "type": "field",
                        "inboundTag": ["http-in"],
                        "outboundTag": "test-out"
                    }
                ]
            }
        }
        cmd = [str(XRAY_BIN_PATH), "-config", str(temp_config_path)]
        core_name = "Xray"
    
    try:
        with open(temp_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        return {"success": False, "msg": f"Не удалось создать файл теста: {e}"}
        
    process = None
    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
            
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=creationflags
        )
        
        if not wait_for_port(free_port, timeout=3.0):
            stderr_out = ""
            try:
                stdout, stderr = process.communicate(timeout=0.5)
                stderr_out = f"STDOUT:\n{stdout or ''}\nSTDERR:\n{stderr or ''}"
            except Exception:
                pass
            
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                pass
                
            error_details = f" ({stderr_out.strip()})" if stderr_out else ""
            return {"success": False, "msg": f"Не удалось запустить {core_name}{error_details}"}
            
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
        
        last_status = None
        last_error = None

        for test_url in test_urls:
            start_time = time.perf_counter()
            try:
                resp = requests.get(test_url, proxies=proxies, timeout=5.0, verify=False)
                latency = (time.perf_counter() - start_time) * 1000
                
                if resp.status_code in (204, 200):
                    return {"success": True, "ping": round(latency, 2), "engine": core_name}
                else:
                    last_status = resp.status_code
            except Exception as ex:
                last_error = str(ex)

        if last_status == 503:
            return {"success": False, "msg": f"Удаленный узел недоступен или сбросил соединение (503 Service Unavailable, {core_name})"}
        elif last_status == 502:
            return {"success": False, "msg": f"Ошибка шлюза при подключении (502 Bad Gateway, {core_name})"}
        elif last_status == 504:
            return {"success": False, "msg": f"Превышено время ожидания ответа от узла (504 Gateway Timeout, {core_name})"}
        elif last_status:
            return {"success": False, "msg": f"Неожиданный статус ответа: {last_status} ({core_name})"}
        else:
            return {"success": False, "msg": f"Ошибка проверки транзита: {last_error or 'Таймаут соединения'} ({core_name})"}
            
    finally:
        if process:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
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
        
    protocol = payload.get("protocol", "").strip()
    settings = payload.get("settings", {})
    stream_settings = payload.get("streamSettings", {})
    test_type = payload.get("test_type", "tcp").strip().lower()
    core = payload.get("core") or payload.get("engine") or "auto"
    
    if protocol == "blackhole":
        return {"success": True, "ping": 0, "msg": "Блокировка (Blackhole) активна"}
        
    import backend.routes.routing as routing_facade
    
    if test_type == "http":
        if protocol == "freedom":
            start_time = time.perf_counter()
            try:
                resp = requests.get("https://www.gstatic.com/generate_204", timeout=3.0, verify=False)
                latency = (time.perf_counter() - start_time) * 1000
                if resp.status_code in (200, 204):
                    return {"success": True, "ping": round(latency, 2), "msg": "Прямое соединение работает"}
                else:
                    return {"success": False, "msg": f"Неожиданный статус: {resp.status_code}"}
            except Exception as e:
                return {"success": False, "msg": f"Ошибка соединения: {str(e)}"}
                
        if core and core != "auto":
            return routing_facade.test_outbound_transit(protocol, settings, stream_settings, core=core)
        return routing_facade.test_outbound_transit(protocol, settings, stream_settings)
        
    else:  # TCP Ping
        if protocol == "freedom":
            res = routing_facade.tcp_ping("8.8.8.8", 53, timeout=3.0)
            if res["success"]:
                return {"success": True, "ping": res["ping"], "msg": "Прямое подключение доступно"}
            else:
                return {"success": False, "msg": f"Прямое подключение недоступно: {res['msg']}"}
                
        if protocol == "hysteria":
            host, port = extract_address_port(protocol, settings, stream_settings)
            if not host:
                return {"success": False, "msg": "Не удалось определить адрес для этого протокола"}
            return routing_facade.system_ping(host)
            
        host, port = extract_address_port(protocol, settings, stream_settings)
        if not host or not port:
            return {"success": False, "msg": "Не удалось определить адрес и порт для этого протокола"}
            
        res = routing_facade.tcp_ping(host, port)
        return res

@router.post("/api/routing/outbounds/test/{id}")
async def test_outbound_by_id_api(request: Request, id: int, test_type: str = "tcp", core: str = "auto"):
    """Tests a saved outbound connectivity by database configuration ID."""
    if not check_auth(request):
        return decoy_response()
        
    ob = get_outbound_by_id(id)
    if not ob:
        return {"success": False, "msg": "Исходящее подключение не найдено"}
        
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
        return {"success": True, "ping": 0, "msg": "Блокировка (Blackhole) активна"}
        
    import backend.routes.routing as routing_facade
    
    if test_type == "http":
        if protocol == "freedom":
            start_time = time.perf_counter()
            try:
                resp = requests.get("https://www.gstatic.com/generate_204", timeout=3.0, verify=False)
                latency = (time.perf_counter() - start_time) * 1000
                if resp.status_code in (200, 204):
                    return {"success": True, "ping": round(latency, 2), "msg": "Прямое соединение работает"}
                else:
                    return {"success": False, "msg": f"Неожиданный статус: {resp.status_code}"}
            except Exception as e:
                return {"success": False, "msg": f"Ошибка соединения: {str(e)}"}
                
        if core and core != "auto":
            return routing_facade.test_outbound_transit(protocol, settings, stream_settings, core=core)
        return routing_facade.test_outbound_transit(protocol, settings, stream_settings)
        
    else:  # TCP Ping
        if protocol == "freedom":
            res = routing_facade.tcp_ping("8.8.8.8", 53, timeout=3.0)
            if res["success"]:
                return {"success": True, "ping": res["ping"], "msg": "Прямое подключение доступно"}
            else:
                return {"success": False, "msg": f"Прямое подключение недоступно: {res['msg']}"}
                
        if protocol == "hysteria":
            host, port = extract_address_port(protocol, settings, stream_settings)
            if not host:
                return {"success": False, "msg": "Не удалось определить адрес"}
            return routing_facade.system_ping(host)
            
        host, port = extract_address_port(protocol, settings, stream_settings)
        if not host or not port:
            return {"success": False, "msg": "Не удалось определить адрес и порт"}
            
        res = routing_facade.tcp_ping(host, port)
        return res

@router.post("/api/routing/outbounds/generate-warp")
async def generate_warp_api(request: Request):
    """Registers and generates a Cloudflare WARP account profile config."""
    if not check_auth(request):
        return decoy_response()
        
    from backend.utils.warp import register_warp
    
    warp_data = await asyncio.to_thread(register_warp)
    if not warp_data:
        return {"success": False, "msg": "Не удалось зарегистрировать аккаунт Cloudflare WARP. Попробуйте еще раз."}
        
    return {"success": True, "obj": warp_data}
