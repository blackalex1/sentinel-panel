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


def get_capabilities_schema(lang: str = "ru") -> Dict[str, Any]:
    """Returns dynamic capabilities matrix schema for UI forms."""
    try:
        res = _ffi_call_json("SentinelGetConfigurationSchema", lang)
        if isinstance(res, dict) and ("engines" in res or "protocols" in res):
            return res
    except Exception as e:
        logger.debug("FFI get_capabilities_schema error: %s", e)

    res = run_core_command(["schema", "--lang", lang])
    if isinstance(res, dict) and "error" in res:
        logger.warning("Error fetching schema from sentinel-core: %s", res["error"])
    return res if isinstance(res, dict) else {}


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
    return res if isinstance(res, dict) else {}


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


def parse_subscription(content_or_url: str) -> Optional[List[Dict[str, Any]]]:
    """Parses a Base64 subscription or multi-URI list using Go sentinel-core engine."""
    if not content_or_url:
        return None

    try:
        res = _ffi_call_json("SentinelParseSubscription", content_or_url)
        if isinstance(res, list):
            return res
    except Exception as e:
        logger.debug("FFI SentinelParseSubscription error: %s", e)

    try:
        res = run_core_command(["parse"], input_data=content_or_url)
        if isinstance(res, list):
            return res
        if isinstance(res, dict) and "profiles" in res:
            return res["profiles"]
    except Exception as e:
        logger.debug("CLI parse error: %s", e)

    # Line by line fallback using parse_proxy_uri
    profiles = []
    for line in content_or_url.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = parse_proxy_uri(line)
        if isinstance(p, dict) and "protocol" in p:
            profiles.append(p)
    return profiles if profiles else None


def test_profiles(profiles: List[Dict[str, Any]], ping_count: int = 3, timeout_ms: int = 2000) -> Optional[List[Dict[str, Any]]]:
    """Tests connectivity and latency of multiple VPN profiles via Go sentinel-core engine."""
    if not profiles:
        return None

    profiles_json = json.dumps(profiles)
    try:
        res = _ffi_call_json("SentinelTestProfiles", profiles_json, int(ping_count), int(timeout_ms))
        if isinstance(res, list):
            return res
    except Exception as e:
        logger.debug("FFI SentinelTestProfiles error: %s", e)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(profiles_json)
        tmp_name = f.name

    try:
        args = ["test-profiles", "--file", tmp_name, "--count", str(ping_count), "--timeout", str(timeout_ms)]
        res = run_core_command(args)
        if isinstance(res, list):
            return res
    finally:
        try:
            os.remove(tmp_name)
        except Exception:
            pass

    return None


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


def set_core_language(lang: str) -> bool:
    """Sets language locale in Go sentinel-core ('ru' or 'en')."""
    try:
        res = _ffi_call_json("SentinelSetLanguage", lang)
        return isinstance(res, dict) and res.get("success") is True
    except Exception:
        return False
