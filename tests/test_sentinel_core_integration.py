import ctypes
import json
import os
import pytest
from backend.sentinel_core_bridge import (
    get_capabilities_schema,
    get_routing_presets,
    get_preset_details,
    parse_proxy_uri,
    generate_proxy_uri,
    build_server_config,
    generate_x25519_keypair,
    generate_vlessenc_keypair,
    ping_host,
    encrypt_payload,
    decrypt_payload,
    get_cores_status,
    get_unified_traffic,
    kick_client,
    get_core_logs,
    pop_core_log_line,
    get_in_memory_core_logs,
    clear_in_memory_core_logs,
    start_core,
    stop_core,
    restart_core,
    validate_core_config,
    get_core_version,
    set_sentinel_lib,
    get_sentinel_lib,
    _find_sentinel_core_lib_path,
    _init_sentinel_lib,
)


def test_sentinel_core_bridge_direct():
    """Tests baseline bridge operations (CLI or library)."""
    # 1. Capabilities schema from core
    schema_ru = get_capabilities_schema("ru")
    assert "engines" in schema_ru
    assert "protocols" in schema_ru
    assert "vless" in schema_ru["protocols"]
    assert "hysteria2" in schema_ru["protocols"]
    
    schema_en = get_capabilities_schema("en")
    assert schema_en.get("language") == "en"

    # 2. Dynamic presets list from core
    presets = get_routing_presets()
    assert isinstance(presets, list)
    assert len(presets) > 0
    preset_ids = [p["id"] for p in presets]
    assert "ru" in preset_ids
    assert "bittorrent" in preset_ids
    assert "ads" in preset_ids

    # 3. Preset details
    preset_ru = get_preset_details("ru")
    assert isinstance(preset_ru, dict)
    assert "domains" in preset_ru or "id" in preset_ru

    # 4. URI parsing & generation
    uri = "vless://a6c8e874-5182-4916-9ea6-f7723933c091@1.2.3.4:443?security=reality&sni=icloud.com&pbk=xPubTest#TestNode"
    parsed = parse_proxy_uri(uri)
    assert parsed.get("protocol") == "vless"
    assert parsed.get("address") == "1.2.3.4"
    assert parsed.get("port") == 443
    assert parsed.get("name") == "TestNode"

    gen_uri = generate_proxy_uri(parsed)
    assert isinstance(gen_uri, str)
    assert gen_uri.startswith("vless://")


def test_api_schema_capabilities_endpoint(client):
    headers = {"Authorization": "Bearer test_bearer_token"}
    res = client.get("/api/v1/schema/capabilities?lang=ru", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    obj = data["obj"]
    assert "engines" in obj
    assert "protocols" in obj
    assert "vless" in obj["protocols"]
    assert "sniffingOptions" in obj


def test_api_routing_presets_endpoint(client):
    headers = {"Authorization": "Bearer test_bearer_token"}
    res = client.get("/api/v1/routing/presets", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    presets = data["obj"]
    assert isinstance(presets, list)
    preset_ids = [p["id"] for p in presets]
    assert "ru" in preset_ids
    assert "bittorrent" in preset_ids
    assert "ads" in preset_ids


def test_sentinel_core_supervisor_bridge():
    # 1. Test Keypair generation
    kp = generate_x25519_keypair()
    assert isinstance(kp, dict)
    assert len(kp.get("privateKey", "")) > 10
    assert len(kp.get("publicKey", "")) > 10

    # 2. Test Cores Status from supervisor
    status = get_cores_status()
    assert isinstance(status, dict)
    assert "sing-box" in status
    assert "hysteria2" in status
    assert "xray" in status

    # 3. Test Unified Traffic from supervisor
    traffic = get_unified_traffic()
    assert isinstance(traffic, dict)

    # 4. Test Kick Client from supervisor
    kicked = kick_client("test_client@mail.com")
    assert isinstance(kicked, bool)

    # 5. Test Server Config Builder for all 3 cores
    inbounds = [
        {
            "id": 1,
            "port": 443,
            "protocol": "vless",
            "tag": "inbound-vless",
            "security": "reality",
            "settings": {"clients": [{"email": "user@test.com", "uuid": "uuid-1234"}]}
        }
    ]
    xray_cfg = build_server_config("xray", inbounds)
    assert isinstance(xray_cfg, dict)

    sb_cfg = build_server_config("sing-box", inbounds)
    assert isinstance(sb_cfg, dict)

    hy_inbounds = [
        {
            "id": 2,
            "port": 8443,
            "protocol": "hysteria2",
            "tag": "inbound-hy2",
            "settings": {"clients": [{"email": "user@test.com", "password": "hy2-password"}]}
        }
    ]
    hy_cfg = build_server_config("hysteria2", hy_inbounds)
    assert isinstance(hy_cfg, dict)


def test_sentinel_core_diagnostics_and_crypto():
    # 1. Test ping
    ping_res = ping_host("1.1.1.1", 443, 3000)
    assert isinstance(ping_res, dict)
    assert "success" in ping_res

    # 2. Test authenticated AEAD encrypt/decrypt
    secret = "my-super-secret-password-123"
    plain_text = "Sentinel panel secret data to backup"
    encrypted = encrypt_payload(plain_text, secret)
    assert encrypted != ""
    assert encrypted.startswith("enc:")

    decrypted = decrypt_payload(encrypted, secret)
    assert decrypted == plain_text


def test_sentinel_core_vlessenc_and_process_lifecycle():
    # 1. Test VLESS Encryption PQ keypair generation
    vlessenc = generate_vlessenc_keypair()
    assert vlessenc.get("success") is True
    assert "x25519" in vlessenc
    assert "mlkem768" in vlessenc
    assert len(vlessenc["x25519"]["decryption"]) > 0
    assert len(vlessenc["x25519"]["encryption"]) > 0
    assert len(vlessenc["mlkem768"]["decryption"]) > 0
    assert len(vlessenc["mlkem768"]["encryption"]) > 0

    # 2. Test stop_core on non-running core
    res = stop_core("xray")
    assert isinstance(res, bool)

    # 3. Test version detection via sentinel-core
    from backend.config import XRAY_BIN_PATH
    if XRAY_BIN_PATH.exists():
        ver = get_core_version("xray", str(XRAY_BIN_PATH))
        assert isinstance(ver, str)
        assert len(ver) > 0


def test_sentinel_core_cffi_dynamic_loading_discovery():
    """Tests library discovery and initialization helpers."""
    lib_path = _find_sentinel_core_lib_path()
    # It returns None or a valid path
    if lib_path:
        assert isinstance(lib_path, str)

    # Test prototype initialization on a dummy library object
    class DummyLib:
        pass

    dummy = DummyLib()
    initialized = _init_sentinel_lib(dummy)
    assert initialized is dummy


def test_sentinel_core_cffi_real_ctypes_function_prototypes():
    """Tests that _init_sentinel_lib configures argtypes and restype on genuine ctypes CFUNCTYPE objects."""
    PROTO_STR = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)
    PROTO_INT = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int)
    PROTO_FREE = ctypes.CFUNCTYPE(None, ctypes.c_void_p)

    class DummyCDLL:
        def __init__(self):
            self.SentinelFreeString = PROTO_FREE(lambda ptr: None)
            self.SentinelParseURI = PROTO_STR(lambda uri: 0)
            self.SentinelGetCoreLogs = PROTO_INT(lambda path, lines: 0)

    lib = DummyCDLL()
    _init_sentinel_lib(lib)
    assert lib.SentinelFreeString.argtypes == [ctypes.c_void_p]
    assert lib.SentinelFreeString.restype is None
    assert lib.SentinelParseURI.argtypes == [ctypes.c_char_p]
    assert lib.SentinelParseURI.restype == ctypes.c_void_p
    assert lib.SentinelGetCoreLogs.argtypes == [ctypes.c_char_p, ctypes.c_int]
    assert lib.SentinelGetCoreLogs.restype == ctypes.c_void_p


class MockGoSentinelLib:
    """Mock simulating Go C-FFI exported functions with ctypes memory allocation and tracking."""
    def __init__(self):
        self.freed_pointers = []
        self._alive_buffers = []

    def _alloc_str(self, text: str) -> int:
        buf = ctypes.create_string_buffer(text.encode("utf-8"))
        self._alive_buffers.append(buf)
        return ctypes.addressof(buf)

    def SentinelFreeString(self, ptr):
        val = ptr.value if isinstance(ptr, ctypes.c_void_p) else ptr
        self.freed_pointers.append(val)

    def SentinelGetConfigurationSchema(self, lang):
        return self._alloc_str(json.dumps({
            "engines": ["sing-box", "xray", "hysteria2"],
            "protocols": ["vless", "hysteria2"],
            "language": "ru"
        }))

    def SentinelListPresets(self):
        return self._alloc_str(json.dumps([
            {"id": "ru", "name": "Russia"},
            {"id": "bittorrent", "name": "P2P"}
        ]))

    def SentinelGetPreset(self, preset_id):
        return self._alloc_str(json.dumps({
            "id": "ru",
            "name": "Russia",
            "rules": [{"domains": ["ru"]}]
        }))

    def SentinelParseURI(self, uri):
        return self._alloc_str(json.dumps({
            "protocol": "vless",
            "address": "10.0.0.1",
            "port": 443,
            "name": "MockFFINode"
        }))

    def SentinelGenerateURI(self, profile_json):
        return self._alloc_str(json.dumps({
            "uri": "vless://mock-uuid@10.0.0.1:443?security=reality#MockFFINode"
        }))

    def SentinelBuildServerConfig(self, spec_json):
        return self._alloc_str(json.dumps({
            "config": json.dumps({"inbounds": [{"port": 443}], "outbounds": []})
        }))

    def SentinelGenerateX25519Keys(self):
        return self._alloc_str(json.dumps({
            "privateKey": "mock_cffi_private_key",
            "publicKey": "mock_cffi_public_key"
        }))

    def SentinelGenerateVlessEncKeys(self):
        return self._alloc_str(json.dumps({
            "success": True,
            "x25519": {"decryption": "x_priv", "encryption": "x_pub"},
            "mlkem768": {"decryption": "ml_priv", "encryption": "ml_pub"}
        }))

    def SentinelPing(self, host, port, timeout_ms):
        return self._alloc_str(json.dumps({
            "success": True,
            "latencyMs": 12,
            "address": "1.1.1.1"
        }))

    def SentinelEncrypt(self, data, secret):
        return self._alloc_str(json.dumps({
            "payload": "enc:mock_cffi_encrypted"
        }))

    def SentinelDecrypt(self, payload, secret):
        return self._alloc_str(json.dumps({
            "plaintext": "mock_cffi_decrypted"
        }))

    def SentinelGetCoresStatus(self):
        return self._alloc_str(json.dumps({
            "xray": {"running": True, "pid": 111},
            "sing-box": {"running": False, "pid": 0},
            "hysteria2": {"running": True, "pid": 222}
        }))

    def SentinelGetUnifiedTraffic(self):
        return self._alloc_str(json.dumps({
            "totalUp": 1024,
            "totalDown": 2048,
            "activeClients": 5
        }))

    def SentinelKickClient(self, email):
        return self._alloc_str(json.dumps({"success": True}))

    def SentinelGetCoreLogs(self, path, lines):
        return self._alloc_str(json.dumps(["log line 1", "log line 2"]))

    def SentinelStartCore(self, core, bin_path, config):
        return self._alloc_str(json.dumps({"success": True}))

    def SentinelStopCore(self, core):
        return self._alloc_str(json.dumps({"success": True}))

    def SentinelRestartCore(self, core, bin_path, config):
        return self._alloc_str(json.dumps({"success": True}))

    def SentinelValidateCore(self, core, bin_path, config):
        return self._alloc_str(json.dumps({"valid": True, "output": "config is valid"}))

    def SentinelGetCoreVersion(self, core, bin_path):
        return self._alloc_str("Xray 1.8.24 (Mock FFI)")


def test_sentinel_core_cffi_mock_full_coverage(tmp_path):
    """Tests that when C-FFI CDLL is loaded, all 20 functions invoke FFI directly in memory and free strings."""
    mock_lib = MockGoSentinelLib()
    set_sentinel_lib(mock_lib)

    try:
        # 1. Capabilities Schema
        schema = get_capabilities_schema("ru")
        assert "engines" in schema
        engine_ids = [e.get("id", e) if isinstance(e, dict) else e for e in schema["engines"]]
        assert "sing-box" in engine_ids or "sing-box" in schema["engines"]

        # 2. Presets
        presets = get_routing_presets()
        assert len(presets) >= 2
        assert any(pr["id"] == "ru" for pr in presets)

        # 3. Preset details
        p = get_preset_details("ru")
        assert p.get("id") == "ru"
        assert "rules" in p or "name" in p

        # 4. URI parse
        parsed = parse_proxy_uri("vless://...")
        assert parsed["name"] == "MockFFINode"
        assert parsed["port"] == 443

        # 5. URI generate
        uri = generate_proxy_uri({"protocol": "vless"})
        assert uri == "vless://mock-uuid@10.0.0.1:443?security=reality#MockFFINode"

        # 6. Build server config
        cfg = build_server_config("xray", [{"port": 443}])
        assert isinstance(cfg, dict)
        assert "inbounds" in cfg

        # 7. Keypair X25519
        kp = generate_x25519_keypair()
        assert kp["privateKey"] == "mock_cffi_private_key"
        assert kp["publicKey"] == "mock_cffi_public_key"

        # 8. Keypair VLESS Encryption
        vlessenc = generate_vlessenc_keypair()
        assert vlessenc["success"] is True
        assert vlessenc["x25519"]["decryption"] == "x_priv"

        # 9. Ping
        ping_res = ping_host("1.1.1.1", 443, 3000)
        assert ping_res["success"] is True
        assert ping_res["latencyMs"] == 12

        # 10. Encrypt
        enc = encrypt_payload("hello", "secret")
        assert enc == "enc:mock_cffi_encrypted"

        # 11. Decrypt
        dec = decrypt_payload("enc:mock_cffi_encrypted", "secret")
        assert dec == "mock_cffi_decrypted"

        # 12. Cores Status
        st = get_cores_status()
        assert st["xray"]["running"] is True
        assert st["sing-box"]["running"] is False

        # 13. Unified Traffic
        tr = get_unified_traffic()
        assert tr["totalUp"] == 1024
        assert tr["activeClients"] == 5

        # 14. Kick Client
        kicked = kick_client("user@test.com")
        assert kicked is True

        # 15. Core logs
        logs = get_core_logs("/var/log/xray.log", 10)
        assert len(logs) == 2
        assert logs[0] == "log line 1"

        # 16. Start core
        started = start_core("xray", "/usr/bin/xray", "/etc/xray.json")
        assert started is True

        # 17. Stop core
        stopped = stop_core("xray")
        assert stopped is True

        # 18. Restart core
        restarted = restart_core("xray", "/usr/bin/xray", "/etc/xray.json")
        assert restarted is True

        # 19. Validate core config
        valid, out = validate_core_config("xray", "/usr/bin/xray", "/etc/xray.json")
        assert valid is True
        assert "valid" in out

        # 20. Version detection (create a temp file for bin_path)
        dummy_bin = tmp_path / "xray_bin"
        dummy_bin.write_text("binary")
        ver = get_core_version("xray", str(dummy_bin))
        assert "Mock FFI" in ver

        # VERIFY MEMORY FREEING:
        # Every single call allocated a C-string pointer and freed it via SentinelFreeString!
        assert len(mock_lib.freed_pointers) >= 20
        assert len(mock_lib.freed_pointers) == len(mock_lib._alive_buffers)
    finally:
        set_sentinel_lib(None)


def test_sentinel_core_cffi_error_fallback_to_cli():
    """Tests that when C-FFI raises an exception or returns null, bridge seamlessly falls back to CLI."""
    class BrokenSentinelLib:
        def SentinelFreeString(self, ptr):
            pass

        def SentinelGetConfigurationSchema(self, lang):
            raise RuntimeError("FFI crashed")

        def SentinelListPresets(self):
            return 0  # NULL pointer

        def SentinelParseURI(self, uri):
            raise ValueError("FFI parse error")

        def SentinelGenerateX25519Keys(self):
            raise Exception("FFI crypto failed")

        def SentinelEncrypt(self, data, secret):
            raise Exception("FFI encrypt failed")

    set_sentinel_lib(BrokenSentinelLib())

    try:
        # Should gracefully fall back to CLI without raising an uncaught exception
        schema = get_capabilities_schema("ru")
        assert isinstance(schema, dict)
        assert "engines" in schema

        presets = get_routing_presets()
        assert isinstance(presets, list)
        assert len(presets) > 0

        parsed = parse_proxy_uri("vless://a6c8e874-5182-4916-9ea6-f7723933c091@1.2.3.4:443?security=reality&sni=icloud.com&pbk=xPubTest#TestNode")
        assert parsed.get("protocol") == "vless"

        kp = generate_x25519_keypair()
        assert isinstance(kp, dict)
        assert "privateKey" in kp

        enc = encrypt_payload("plain text", "secret-key")
        assert enc.startswith("enc:")
    finally:
        set_sentinel_lib(None)


def test_sentinel_core_in_memory_log_stream():
    """Tests in-memory C-FFI streaming and buffer operations."""
    # 1. Clear in-memory logs
    res = clear_in_memory_core_logs("xray")
    assert res is True

    # 2. Get in-memory logs (empty or list)
    logs = get_in_memory_core_logs("xray", limit=50)
    assert isinstance(logs, list)

    # 3. Pop log line with short timeout
    line = pop_core_log_line("xray", timeout_ms=10)
    # Returns None or string without crashing
    assert line is None or isinstance(line, str)

