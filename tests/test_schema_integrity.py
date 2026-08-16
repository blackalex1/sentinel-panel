"""
Strict Integrity Tests for Sentinel Capabilities Schema and Tab Generation
Ensures that Hysteria 2, Shadowsocks, TUIC, VLESS, etc. have 100% correct engines,
security options, transports, and tab definitions without cross-contamination.
"""
import pytest
from backend.sentinel_core_bridge import get_capabilities_schema

def test_schema_integrity_protocols_and_engines():
    schema = get_capabilities_schema(lang="ru")
    assert schema is not None, "Schema should not be None"
    
    protocols = schema.get("protocols", {})
    engines = schema.get("engines", [])
    
    engine_ids = [e.get("id") for e in engines]
    assert "xray-core" in engine_ids
    assert "sing-box" in engine_ids
    assert "hysteria2" in engine_ids

    # 1. Hysteria 2 Verification
    hy2 = protocols.get("hysteria2")
    assert hy2 is not None, "hysteria2 protocol must exist in schema"
    assert "xray-core" not in hy2.get("supportedEngines", []), "Hysteria 2 must NOT support xray-core"
    assert "hysteria2" in hy2.get("supportedEngines", []), "Hysteria 2 must support native hysteria2 engine"
    assert "sing-box" in hy2.get("supportedEngines", []), "Hysteria 2 must support sing-box engine"
    assert hy2.get("supportedTransports") == ["quic"], "Hysteria 2 must only use quic transport"
    assert "reality" not in hy2.get("supportedSecurity", []), "Hysteria 2 must NOT have reality security mode"
    assert "none" not in hy2.get("supportedSecurity", []), "Hysteria 2 must NOT have none security mode"
    assert "protocol" not in hy2.get("tabs", []), "Hysteria 2 must NOT have protocol tab"
    assert "security" not in hy2.get("tabs", []), "Hysteria 2 must NOT have security tab"
    
    # 2. VLESS Verification
    vless = protocols.get("vless")
    assert vless is not None, "vless protocol must exist in schema"
    assert "xray-core" in vless.get("supportedEngines", [])
    assert "reality" in vless.get("supportedSecurity", [])
    assert "tls" in vless.get("supportedSecurity", [])
    assert "protocol" in vless.get("tabs", [])
    assert "security" in vless.get("tabs", [])
    
    # 3. Shadowsocks Verification
    ss = protocols.get("shadowsocks")
    assert ss is not None, "shadowsocks protocol must exist in schema"
    assert "reality" not in ss.get("supportedSecurity", [])
    assert "tls" not in ss.get("supportedSecurity", [])
    assert "stream" not in ss.get("tabs", [])
    assert "security" not in ss.get("tabs", [])
    
    # 4. TUIC Verification
    tuic = protocols.get("tuic")
    assert tuic is not None, "tuic protocol must exist in schema"
    assert tuic.get("supportedEngines") == ["sing-box"], "TUIC must only support sing-box"
    assert "reality" not in tuic.get("supportedSecurity", [])
    assert "protocol" not in tuic.get("tabs", [])
    assert "security" not in tuic.get("tabs", [])

def test_schema_tab_definitions_fields_validity():
    schema = get_capabilities_schema(lang="ru")
    protocols = schema.get("protocols", {})
    
    hy2 = protocols.get("hysteria2", {})
    tab_defs = hy2.get("tabDefinitions", [])
    assert len(tab_defs) >= 3, "Hysteria 2 must have at least 3 tab definitions (basic, stream, sniffing/advanced)"
    
    # Verify no reality or decryption fields in hysteria2 tab definitions
    for tab in tab_defs:
        assert tab.get("id") not in ["protocol", "security"], f"Invalid tab {tab.get('id')} in Hysteria 2"
        for grp in tab.get("groups", []):
            for field in grp.get("fields", []):
                target = field.get("targetField", "")
                assert "realitySettings" not in target, f"Field {target} should not be in Hysteria 2"
                assert "decryption" not in target, f"Field {target} should not be in Hysteria 2"
