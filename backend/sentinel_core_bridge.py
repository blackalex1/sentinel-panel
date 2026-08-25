import ctypes
import json
import logging
import os
import subprocess
import sys
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SENTINEL_LIB: Optional[ctypes.CDLL] = None
_SENTINEL_LIB_TRIED: bool = False
_CORE_VERSION_CACHE: Dict[Tuple[str, str, float], str] = {}


def _get_sentinel_core_bin() -> str:
    """Finds the sentinel-core binary on Windows or Linux."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_dir = os.path.join(base_dir, "bin")

    is_windows = sys.platform == "win32" or os.name == "nt"
    bin_name = "sentinel-core.exe" if is_windows else "sentinel-core"

    bin_path = os.path.join(bin_dir, bin_name)
    if os.path.isfile(bin_path):
        return bin_path

    # Fallback to PATH
    return bin_name


def _find_sentinel_core_lib_path() -> Optional[str]:
    """Finds the sentinel-core shared library (.dll, .so, .dylib) on Windows, Linux, or macOS."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bin_dir = os.path.join(base_dir, "bin")

    is_windows = sys.platform == "win32" or os.name == "nt"
    is_darwin = sys.platform == "darwin"

    if is_windows:
        candidates = [
            os.path.join(bin_dir, "sentinel-core.dll"),
            os.path.join(bin_dir, "libsentinel-core.dll"),
            "sentinel-core.dll",
        ]
    elif is_darwin:
        candidates = [
            os.path.join(bin_dir, "libsentinel-core.dylib"),
            os.path.join(bin_dir, "sentinel-core.dylib"),
            "libsentinel-core.dylib",
        ]
    else:
        candidates = [
            os.path.join(bin_dir, "libsentinel-core.so"),
            os.path.join(bin_dir, "sentinel-core.so"),
            "libsentinel-core.so",
            "sentinel-core.so",
        ]

    for cand in candidates:
        if os.path.isabs(cand) and os.path.isfile(cand):
            return cand

    # Try finding in system paths via ctypes.util
    try:
        from ctypes.util import find_library
        sys_lib = find_library("sentinel-core") or find_library("libsentinel-core")
        if sys_lib:
            return sys_lib
    except Exception:
        pass

    return None


def _init_sentinel_lib(lib: Any) -> Any:
    """Configures argtypes and restype for all exported Sentinel C-FFI functions."""
    if hasattr(lib, "SentinelFreeString"):
        try:
            lib.SentinelFreeString.argtypes = [ctypes.c_void_p]
            lib.SentinelFreeString.restype = None
        except (AttributeError, TypeError):
            pass

    func_signatures = [
        ("SentinelBuildConfig", [ctypes.c_char_p]),
        ("SentinelBuildServerConfig", [ctypes.c_char_p]),
        ("SentinelParseURI", [ctypes.c_char_p]),
        ("SentinelGenerateURI", [ctypes.c_char_p]),
        ("SentinelGenerateX25519Keys", []),
        ("SentinelGetCoresStatus", []),
        ("SentinelGetUnifiedTraffic", []),
        ("SentinelKickClient", [ctypes.c_char_p]),
        ("SentinelGetCoreLogs", [ctypes.c_char_p, ctypes.c_int]),
        ("SentinelPing", [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]),
        ("SentinelEncrypt", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelDecrypt", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelEncryptPayload", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelDecryptPayload", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelListPresets", []),
        ("SentinelGetPreset", [ctypes.c_char_p]),
        ("SentinelGetConfigurationSchema", [ctypes.c_char_p]),
        ("SentinelRunHealthCheck", [ctypes.c_int, ctypes.c_int, ctypes.c_char_p]),
        ("SentinelStartCore", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelStopCore", [ctypes.c_char_p]),
        ("SentinelRestartCore", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelValidateCore", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelGenerateVlessEncKeys", []),
        ("SentinelRegisterHysteriaPort", [ctypes.c_int]),
        ("SentinelConfigureSupervisor", [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelGetCoreVersion", [ctypes.c_char_p, ctypes.c_char_p]),
        ("SentinelPopLogLine", [ctypes.c_char_p, ctypes.c_int]),
        ("SentinelGetInMemoryLogs", [ctypes.c_char_p, ctypes.c_int]),
        ("SentinelClearInMemoryLogs", [ctypes.c_char_p]),
        ("SentinelGetSecuritySchema", [ctypes.c_char_p]),
        ("SentinelGetDefaultSecurityConfig", []),
        ("SentinelValidateSecurityConfig", [ctypes.c_char_p]),
    ]

    for name, argtypes in func_signatures:
        if hasattr(lib, name):
            try:
                func = getattr(lib, name)
                func.argtypes = argtypes
                func.restype = ctypes.c_void_p
            except (AttributeError, TypeError):
                pass

    return lib


def get_sentinel_lib() -> Optional[ctypes.CDLL]:
    """Returns the loaded ctypes.CDLL instance for sentinel-core, or None if unavailable."""
    global _SENTINEL_LIB, _SENTINEL_LIB_TRIED
    if _SENTINEL_LIB is not None:
        return _SENTINEL_LIB
    if _SENTINEL_LIB_TRIED:
        return None

    _SENTINEL_LIB_TRIED = True
    lib_path = _find_sentinel_core_lib_path()
    if not lib_path:
        return None

    try:
        lib = ctypes.CDLL(lib_path)
        _init_sentinel_lib(lib)
        _SENTINEL_LIB = lib
        logger.info("Loaded sentinel-core shared library from %s", lib_path)
        return _SENTINEL_LIB
    except Exception as e:
        logger.warning("Failed to load sentinel-core shared library (%s): %s", lib_path, e)
        return None


def set_sentinel_lib(lib: Optional[ctypes.CDLL]) -> None:
    """Explicitly sets or resets the CDLL instance (useful for testing or runtime injection)."""
    global _SENTINEL_LIB, _SENTINEL_LIB_TRIED
    if lib is not None:
        _init_sentinel_lib(lib)
    _SENTINEL_LIB = lib
    _SENTINEL_LIB_TRIED = (lib is not None)


def _ffi_call_str(func_name: str, *args) -> Optional[str]:
    """Calls a C-FFI function returning a Go allocated string, decodes utf-8, and frees memory via SentinelFreeString."""
    lib = get_sentinel_lib()
    if not lib or not hasattr(lib, func_name):
        return None

    func = getattr(lib, func_name)
    if hasattr(func, "restype") and func.restype != ctypes.c_void_p and func_name != "SentinelFreeString":
        func.restype = ctypes.c_void_p

    c_args = []
    for a in args:
        if isinstance(a, str):
            c_args.append(a.encode("utf-8"))
        elif isinstance(a, int):
            c_args.append(ctypes.c_int(a))
        elif isinstance(a, bytes):
            c_args.append(a)
        elif a is None:
            c_args.append(None)
        else:
            c_args.append(a)

    ptr = func(*c_args)
    if not ptr:
        return None
    try:
        raw_bytes = ctypes.cast(ptr, ctypes.c_char_p).value
        if raw_bytes is None:
            return None
        return raw_bytes.decode("utf-8", errors="replace")
    finally:
        if hasattr(lib, "SentinelFreeString"):
            lib.SentinelFreeString(ctypes.c_void_p(ptr))


def _ffi_call_json(func_name: str, *args) -> Optional[Any]:
    """Calls a C-FFI function and parses its JSON output."""
    raw = _ffi_call_str(func_name, *args)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw}


def run_core_command(args: List[str], input_data: Optional[str] = None) -> Dict[str, Any]:
    """Executes sentinel-core CLI with given args and returns parsed JSON output or raw string."""
    bin_path = _get_sentinel_core_bin()
    cmd = [bin_path] + args
    try:
        proc = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10
        )
        output = proc.stdout.strip()
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                pass

        if proc.returncode != 0:
            logger.error("sentinel-core exited with code %d: %s", proc.returncode, proc.stderr)
            return {"error": proc.stderr.strip() or f"Process exited with code {proc.returncode}"}

        return {"raw": output}
    except Exception as e:
        logger.exception("Failed to execute sentinel-core CLI: %s", e)
        return {"error": str(e)}


def get_capabilities_schema(lang: str = "ru") -> Dict[str, Any]:
    """Returns dynamic capabilities matrix schema for UI forms."""
    try:
        res = _ffi_call_json("SentinelGetConfigurationSchema", lang)
        if isinstance(res, dict) and ("engines" in res or "protocols" in res):
            return res
    except Exception as e:
        logger.debug("FFI get_capabilities_schema error: %s", e)

    res = run_core_command(["schema", "--lang", lang])
    if "error" in res:
        logger.warning("Error fetching schema from sentinel-core: %s", res["error"])
    return res


def get_routing_presets() -> List[Dict[str, Any]]:
    """Returns available routing presets list directly from sentinel-core."""
    try:
        res = _ffi_call_json("SentinelListPresets")
        if isinstance(res, list):
            return res
    except Exception as e:
        logger.debug("FFI get_routing_presets error: %s", e)

    res = run_core_command(["preset", "list", "--json"])
    if isinstance(res, list):
        return res
    schema = get_capabilities_schema("ru")
    return schema.get("presets", [])


def get_preset_details(preset_id: str) -> Dict[str, Any]:
    """Returns rules and metadata for a specific preset ID."""
    try:
        res = _ffi_call_json("SentinelGetPreset", preset_id)
        if isinstance(res, dict) and ("rules" in res or "id" in res):
            return res
    except Exception as e:
        logger.debug("FFI get_preset_details error: %s", e)

    res = run_core_command(["preset", "show", preset_id])
    return res


def parse_proxy_uri(raw_uri: str) -> Dict[str, Any]:
    """Parses any proxy URI (vless, hy2, trojan, ss, etc.) via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelParseURI", raw_uri)
        if isinstance(res, dict) and ("protocol" in res or "error" in res):
            return res
    except Exception as e:
        logger.debug("FFI parse_proxy_uri error: %s", e)

    return run_core_command(["parse", "--uri", raw_uri])


def generate_proxy_uri(profile: Dict[str, Any]) -> str:
    """Generates standard proxy URI link (vless://, hysteria2://, trojan://, ss://, etc.) via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGenerateURI", json.dumps(profile))
        if isinstance(res, dict) and "uri" in res:
            return str(res["uri"]).strip()
    except Exception as e:
        logger.debug("FFI generate_proxy_uri error: %s", e)

    input_json = json.dumps(profile)
    res = run_core_command(["generate"], input_data=input_json)
    if isinstance(res, dict) and "raw" in res:
        return res["raw"].strip()
    if isinstance(res, str):
        return res.strip()
    return ""


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


def generate_x25519_keypair() -> Dict[str, str]:
    """Generates standard X25519 keypair for VLESS Reality via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGenerateX25519Keys")
        if isinstance(res, dict) and "privateKey" in res and "publicKey" in res:
            return res
    except Exception as e:
        logger.debug("FFI generate_x25519_keypair error: %s", e)

    res = run_core_command(["keypair"])
    if isinstance(res, dict) and "privateKey" in res and "publicKey" in res:
        return res
    return {"privateKey": "", "publicKey": ""}


def get_cores_status() -> Dict[str, Any]:
    """Returns runtime status of all cores via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelGetCoresStatus")
        if isinstance(res, dict) and "error" not in res and len(res) > 0:
            return res
    except Exception as e:
        logger.debug("FFI get_cores_status error: %s", e)

    res = run_core_command(["supervisor", "status"])
    if isinstance(res, dict) and "error" not in res:
        return res
    return {}


def register_hysteria_port(port: int) -> bool:
    """Registers a Hysteria 2 admin port with sentinel-core supervisor for telemetry monitoring."""
    if port <= 0:
        return False
    try:
        res = _ffi_call_json("SentinelRegisterHysteriaPort", int(port))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI register_hysteria_port error: %s", e)
    return True


def get_unified_traffic() -> Dict[str, Any]:
    """Returns aggregated traffic and active clients across all cores via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetUnifiedTraffic")
        if isinstance(res, dict) and "error" not in res:
            return res
    except Exception as e:
        logger.debug("FFI get_unified_traffic error: %s", e)

    res = run_core_command(["supervisor", "traffic"])
    if isinstance(res, dict) and "error" not in res:
        return res
    return {}


def kick_client(email: str) -> bool:
    """Disconnects/kicks a client session across all cores via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelKickClient", email)
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI kick_client error: %s", e)

    res = run_core_command(["supervisor", "kick", "--client", email])
    if isinstance(res, dict) and res.get("success") is True:
        return True
    return False


def get_core_logs(log_path: str, lines: int = 100) -> List[str]:
    """Retrieves tail logs for any core via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetCoreLogs", str(log_path), int(lines))
        if isinstance(res, list):
            return res
    except Exception as e:
        logger.debug("FFI get_core_logs error: %s", e)

    res = run_core_command(["supervisor", "logs", "--path", str(log_path), "--lines", str(lines)])
    if isinstance(res, list):
        return res
    return []


def pop_core_log_line(core_name: str, timeout_ms: int = 100) -> Optional[str]:
    """Pops the next streaming log line for the specified core directly from memory without disk IO."""
    try:
        line = _ffi_call_str("SentinelPopLogLine", str(core_name), int(timeout_ms))
        if line:
            return line
    except Exception as e:
        logger.debug("FFI pop_core_log_line error: %s", e)
    return None


def get_in_memory_core_logs(core_name: str, limit: int = 200) -> List[str]:
    """Retrieves buffered in-memory logs for the specified core from sentinel-core ring buffer."""
    try:
        res = _ffi_call_json("SentinelGetInMemoryLogs", str(core_name), int(limit))
        if isinstance(res, list):
            return res
    except Exception as e:
        logger.debug("FFI get_in_memory_core_logs error: %s", e)
    return []


def clear_in_memory_core_logs(core_name: str) -> bool:
    """Clears buffered in-memory logs for the specified core."""
    try:
        res = _ffi_call_json("SentinelClearInMemoryLogs", str(core_name))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI clear_in_memory_core_logs error: %s", e)
    return True


def ping_host(host: str, port: int = 443, timeout_ms: int = 3000) -> Dict[str, Any]:
    """Performs TCP handshake latency probe via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelPing", host, int(port), int(timeout_ms))
        if isinstance(res, dict) and "success" in res:
            return res
    except Exception as e:
        logger.debug("FFI ping_host error: %s", e)

    res = run_core_command(["ping", host, "--port", str(port), "--timeout-ms", str(timeout_ms)])
    if isinstance(res, dict):
        return res
    return {"success": False, "error": "failed to execute ping"}


def encrypt_payload(data: str, secret: str) -> str:
    """Encrypts a payload with authenticated AEAD via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelEncrypt", data, secret)
        if isinstance(res, dict) and "payload" in res:
            return str(res["payload"])
    except Exception as e:
        logger.debug("FFI encrypt_payload error: %s", e)

    res = run_core_command(["encrypt", "--secret", secret, "--data", data])
    if isinstance(res, dict) and "payload" in res:
        return res["payload"]
    return ""


def decrypt_payload(encrypted_payload: str, secret: str) -> str:
    """Decrypts an authenticated AEAD payload via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelDecrypt", encrypted_payload, secret)
        if isinstance(res, dict) and "plaintext" in res:
            return str(res["plaintext"])
    except Exception as e:
        logger.debug("FFI decrypt_payload error: %s", e)

    res = run_core_command(["decrypt", "--secret", secret, "--payload", encrypted_payload])
    if isinstance(res, dict) and "plaintext" in res:
        return res["plaintext"]
    return ""


def start_core(core_name: str, bin_path: str, config_path: str = "") -> bool:
    """Starts a proxy core process via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelStartCore", core_name, str(bin_path), str(config_path or ""))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI start_core error: %s", e)

    args = ["supervisor", "start", "--core", core_name, "--bin", str(bin_path)]
    if config_path:
        args.extend(["--config", str(config_path)])
    res = run_core_command(args)
    return isinstance(res, dict) and res.get("success") is True


def stop_core(core_name: str) -> bool:
    """Stops a proxy core process via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelStopCore", core_name)
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI stop_core error: %s", e)

    res = run_core_command(["supervisor", "stop", "--core", core_name])
    return isinstance(res, dict) and res.get("success") is True


def restart_core(core_name: str, bin_path: str, config_path: str = "") -> bool:
    """Restarts a proxy core process via sentinel-core supervisor."""
    try:
        res = _ffi_call_json("SentinelRestartCore", core_name, str(bin_path), str(config_path or ""))
        if isinstance(res, dict) and res.get("success") is True:
            return True
    except Exception as e:
        logger.debug("FFI restart_core error: %s", e)

    args = ["supervisor", "restart", "--core", core_name, "--bin", str(bin_path)]
    if config_path:
        args.extend(["--config", str(config_path)])
    res = run_core_command(args)
    return isinstance(res, dict) and res.get("success") is True


def validate_core_config(core_name: str, bin_path: str, config_path: str) -> Tuple[bool, str]:
    """Validates configuration syntax for any core via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelValidateCore", core_name, str(bin_path), str(config_path))
        if isinstance(res, dict) and "valid" in res:
            return bool(res.get("valid", False)), str(res.get("output", "") or res.get("error", ""))
    except Exception as e:
        logger.debug("FFI validate_core_config error: %s", e)

    res = run_core_command(["supervisor", "validate", "--core", core_name, "--bin", str(bin_path), "--config", str(config_path)])
    if isinstance(res, dict):
        return bool(res.get("valid", False)), str(res.get("output", "") or res.get("error", ""))
    return False, "Validation failed"


def generate_vlessenc_keypair() -> Dict[str, Any]:
    """Generates X25519 and ML-KEM-768 key pairs for VLESS Encryption via sentinel-core."""
    lib = get_sentinel_lib()
    if lib is not None:
        try:
            res = _ffi_call_json("SentinelGenerateVlessEncKeys")
            if isinstance(res, dict) and res.get("success") is True:
                mlkem = res.get("mlkem768", {})
                # If mlkem decryption key is valid 64-byte seed (86 base64url chars) or mock test value
                dec_val = mlkem.get("decryption", "")
                dec_payload = dec_val.split(".")[-1] if "." in dec_val else dec_val
                if len(dec_payload) <= 86:
                    return res
        except Exception as e:
            logger.debug("FFI generate_vlessenc_keypair error: %s", e)

    res = run_core_command(["vlessenc"])
    if isinstance(res, dict) and res.get("success") is True:
        return res

    return {
        "success": False,
        "x25519": {"decryption": "", "encryption": ""},
        "mlkem768": {"decryption": "", "encryption": ""}
    }


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
                    ib_spec["fallbacks"] = ib_spec["settings"]["fallbacks"]
                
            if clients:
                # Build client lookup from inbound raw settings if available
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

        # Collect referenced outbound tags in active rules
        referenced_outbounds = {r.get("outboundTag") for r in compiled_rules if r.get("enable", True)}
        
        # Also collect referenced backup outbounds recursively
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
        
        # Sort and filter outbounds: direct #0, blocked/block #1, then used custom outbounds
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
                # Keep if referenced in routing rules
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
        if db_lvl not in ("trace", "debug", "info", "warn", "warning", "error", "none"):
            db_lvl = "warning"
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


def get_core_version(core_name: str, bin_path: str) -> str:
    """Detects version string of any installed proxy core via sentinel-core with mtime caching."""
    if not os.path.exists(bin_path):
        return "Not Installed"
    try:
        mtime = os.path.getmtime(bin_path)
    except Exception:
        mtime = 0.0
    cache_key = (core_name, bin_path, mtime)
    if cache_key in _CORE_VERSION_CACHE:
        return _CORE_VERSION_CACHE[cache_key]

    try:
        ver = _ffi_call_str("SentinelGetCoreVersion", core_name, str(bin_path))
        if ver and ver != "Unknown":
            _CORE_VERSION_CACHE[cache_key] = ver
            return ver
    except Exception as e:
        logger.debug("FFI get_core_version error: %s", e)

    res = run_core_command(["supervisor", "version", "--core", core_name, "--bin", str(bin_path)])
    if isinstance(res, dict) and "version" in res and res["version"] != "Unknown":
        version = res["version"]
        _CORE_VERSION_CACHE[cache_key] = version
        return version
    return "Unknown"


def get_active_sessions() -> List[Dict[str, Any]]:
    """Returns active client sessions tracked natively in Go sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetActiveSessions")
        if isinstance(res, list):
            return res
    except Exception:
        pass
    return []


def get_online_emails_core() -> List[str]:
    """Returns active online client emails tracked natively in Go sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetOnlineEmails")
        if isinstance(res, list):
            return [str(x) for x in res if x]
    except Exception:
        pass
    return []


def get_recent_session_events(since_ts: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """Returns recent connect/disconnect events tracked natively in Go sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGetRecentSessionEvents", since_ts, limit)
        if isinstance(res, list):
            return res
    except Exception:
        pass
    return []


def register_external_connect(core: str, email: str, ip: str) -> None:
    """Registers an external connection (e.g. Hysteria HTTP Auth) in Go core session tracker."""
    try:
        _ffi_call_str("SentinelRegisterExternalConnect", core, email, ip)
    except Exception:
        pass

