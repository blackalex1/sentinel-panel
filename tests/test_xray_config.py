import io
import zipfile
import pytest
import subprocess
import requests
import importlib
from backend.database import add_inbound, add_client_db, delete_inbound
from backend.xray import generate_xray_config_json

def test_xray_config_generation():
    """Test VLESS Reality Inbound Config Generation."""
    vless_settings = {"clients": []}
    vless_stream_settings = {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "show": False,
            "dest": "google.com:443",
            "serverNames": ["google.com"],
            "privateKey": "private_key_xyz",
            "publicKey": "public_key_xyz",
            "shortIds": ["01234567"]
        }
    }
    
    ib_vless_id = add_inbound(
        remark="VLESS Reality Inbound",
        port=60002,
        protocol="vless",
        settings_dict=vless_settings,
        stream_settings_dict=vless_stream_settings
    )
    
    # Add client to VLESS inbound
    add_client_db(ib_vless_id, "client1@reality.com", "uuid-client-1")

    # Generate config and test
    try:
        xray_config = generate_xray_config_json()
        vless_config = next((ib for ib in xray_config["inbounds"] if ib["port"] == 60002), None)
        
        assert vless_config is not None
        assert vless_config["protocol"] == "vless"
        assert vless_config["streamSettings"]["security"] == "reality"
        assert vless_config["streamSettings"]["realitySettings"]["privateKey"] == "private_key_xyz"
        assert vless_config["settings"]["clients"][0]["id"] == "uuid-client-1"
    finally:
        # Cleanup test inbounds
        delete_inbound(ib_vless_id)


def test_advanced_xray_configs():
    """Test Xray config generator with advanced transports, TLS, sniffing, and fallbacks."""
    # 1. Create Inbound with mKCP, TLS Min/Max, Sniffing overrides & Fallbacks
    settings_dict = {
        "clients": [],
        "fallbacks": [
            {
                "dest": "127.0.0.1:8080",
                "path": "/masquerade",
                "xver": 2,
                "alpn": "h2"
            }
        ]
    }
    stream_settings_dict = {
        "network": "mkcp",
        "security": "tls",
        "tlsSettings": {
            "serverName": "domain.com",
            "allowInsecure": True,
            "alpn": ["h2"],
            "minVersion": "1.2",
            "maxVersion": "1.3"
        },
        "kcpSettings": {
            "header": {"type": "srtp"},
            "seed": "my_mkcp_obfs_seed",
            "congestion": True
        }
    }
    sniffing_dict = {
        "enabled": True,
        "destOverride": ["http", "quic"],
        "routeOnly": True
    }

    ib_id = add_inbound(
        remark="Advanced Xray Inbound",
        port=60010,
        protocol="vless",
        settings_dict=settings_dict,
        stream_settings_dict=stream_settings_dict,
        sniffing_dict=sniffing_dict
    )

    try:
        xray_config = generate_xray_config_json()
        inbound = next((ib for ib in xray_config["inbounds"] if ib["port"] == 60010), None)

        assert inbound is not None
        assert inbound["protocol"] == "vless"
        assert inbound["settings"]["fallbacks"][0]["dest"] == "127.0.0.1:8080"
        assert inbound["settings"]["fallbacks"][0]["xver"] == 2
        
        # Test Transport settings
        assert inbound["streamSettings"]["network"] == "mkcp"
        assert inbound["streamSettings"]["kcpSettings"]["header"]["type"] == "srtp"
        assert inbound["streamSettings"]["kcpSettings"]["seed"] == "my_mkcp_obfs_seed"
        assert inbound["streamSettings"]["kcpSettings"]["congestion"] is True
        
        # Test TLS advanced settings
        assert inbound["streamSettings"]["tlsSettings"]["minVersion"] == "1.2"
        assert inbound["streamSettings"]["tlsSettings"]["maxVersion"] == "1.3"

        # Test Sniffing settings
        assert inbound["sniffing"]["enabled"] is True
        assert "http" in inbound["sniffing"]["destOverride"]
        assert "quic" in inbound["sniffing"]["destOverride"]
        assert inbound["sniffing"]["routeOnly"] is True

    finally:
        delete_inbound(ib_id)


def test_download_xray_core_verification_failure_actual(monkeypatch, tmp_path):
    import backend.xray
    
    # Reload to get real functions
    importlib.reload(backend.xray)
    
    # Set paths to temp path
    monkeypatch.setattr(backend.xray, "BIN_DIR", tmp_path)
    monkeypatch.setattr(backend.xray, "XRAY_BIN_PATH", tmp_path / "xray")
    
    # Mock get_latest_xray_version_info
    monkeypatch.setattr(backend.xray, "get_latest_xray_version_info", lambda: {
        "version": "v1.8.24",
        "download_url": "https://github.com/XTLS/Xray-core/releases/download/v1.8.24/xray.zip"
    })
    
    # Create a mock zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        # On Windows XRAY_BIN_NAME has .exe, on Linux it doesn't
        from backend.config import XRAY_BIN_NAME
        zip_file.writestr(XRAY_BIN_NAME, b"mock xray binary")
    zip_bytes = zip_buffer.getvalue()
    
    # Mock requests.get
    class MockResponse:
        status_code = 200
        def iter_content(self, chunk_size):
            return [zip_bytes]
        def raise_for_status(self):
            pass
            
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())
    
    # Mock subprocess.run to simulate verification failure
    class MockCompletedProcess:
        returncode = 1
        stdout = ""
        stderr = "Exec format error"
        
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: MockCompletedProcess())
    
    # Verify download_xray_core raises exception
    with pytest.raises(Exception) as excinfo:
        backend.xray.download_xray_core()
    assert "failed self-test verification" in str(excinfo.value)
    
    # Ensure cleanup
    assert not (tmp_path / "xray_temp.zip").exists()
    assert not (tmp_path / "xray_temp_extract").exists()
    assert not (tmp_path / "xray").exists()
    
    # Restore global mocks
    importlib.reload(backend.xray)
    backend.xray.start_xray = lambda: True
    backend.xray.stop_xray = lambda: None
    backend.xray.restart_xray = lambda: True
    backend.xray.is_xray_running = lambda: True


def test_vless_encryption_config():
    """Test VLESS inbound with Encryption/Decryption settings."""
    settings_dict = {
        "clients": [],
        "decryption": "mlkem768x25519plus.native.600s.mydecryptionkey",
        "encryption": "mlkem768x25519plus.native.0rtt.myencryptionkey"
    }
    
    ib_id = add_inbound(
        remark="VLESS Encryption Inbound",
        port=60020,
        protocol="vless",
        settings_dict=settings_dict
    )
    
    try:
        xray_config = generate_xray_config_json()
        inbound = next((ib for ib in xray_config["inbounds"] if ib["port"] == 60020), None)
        
        assert inbound is not None
        assert inbound["protocol"] == "vless"
        assert inbound["settings"]["decryption"] == "mlkem768x25519plus.native.600s.mydecryptionkey"
    finally:
        delete_inbound(ib_id)


def test_xray_routing_geoip_scenarios():
    """Test Xray routing rules with GeoIP, protocol blocking, and catch-all ranges."""
    from backend.database import add_routing_rule, delete_routing_rule
    
    # 1. Create a blocked rule for BitTorrent
    rule1_id = add_routing_rule(
        remark="Block BitTorrent",
        outbound_tag="blocked",
        inbound_tags=[],
        users=[],
        domains=[],
        ips=[],
        protocols=["bittorrent"],
        enable=1
    )
    
    # 2. Create a rule for geoip:ru to direct
    rule2_id = add_routing_rule(
        remark="RU Direct",
        outbound_tag="direct",
        inbound_tags=[],
        users=[],
        domains=[],
        ips=["geoip:ru"],
        protocols=[],
        enable=1
    )
    
    # 3. Create a rule for geoip:us to warp
    rule3_id = add_routing_rule(
        remark="US Warp",
        outbound_tag="warp",
        inbound_tags=[],
        users=[],
        domains=[],
        ips=["geoip:us"],
        protocols=[],
        enable=1
    )
    
    # 4. Create a catch-all rule (0.0.0.0/0, ::/0) to warp
    rule4_id = add_routing_rule(
        remark="Catch All to Warp",
        outbound_tag="warp",
        inbound_tags=[],
        users=[],
        domains=[],
        ips=["0.0.0.0/0", "::/0"],
        protocols=[],
        enable=1
    )
    
    try:
        xray_config = generate_xray_config_json()
        routing_rules = xray_config["routing"]["rules"]
        
        # Check rule 1: bittorrent
        rule_bt = next((r for r in routing_rules if "bittorrent" in r.get("protocol", [])), None)
        assert rule_bt is not None
        assert rule_bt["outboundTag"] == "blocked"
        
        # Check rule 2: geoip:ru
        rule_ru = next((r for r in routing_rules if "geoip:ru" in r.get("ip", [])), None)
        assert rule_ru is not None
        assert rule_ru["outboundTag"] == "direct"
        
        # Check rule 3: geoip:us
        rule_us = next((r for r in routing_rules if "geoip:us" in r.get("ip", [])), None)
        assert rule_us is not None
        assert rule_us["outboundTag"] == "warp"
        
        # Check rule 4: catch-all
        rule_ca = next((r for r in routing_rules if "0.0.0.0/0" in r.get("ip", [])), None)
        assert rule_ca is not None
        assert rule_ca["outboundTag"] == "warp"
        assert "::/0" in rule_ca["ip"]
        
    finally:
        # Cleanup rules
        delete_routing_rule(rule1_id)
        delete_routing_rule(rule2_id)
        delete_routing_rule(rule3_id)
        delete_routing_rule(rule4_id)


def test_xray_socks_inbound_for_hysteria():
    """Test that Xray config generator creates SOCKS5 inbounds when Hysteria 2 routing is enabled."""
    hysteria_stream_settings = {
        "hysteria": {
            "routingViaXray": True,
            "socksUsername": "socks_user_xyz",
            "socksPassword": "socks_password_xyz"
        }
    }
    
    ib_id = add_inbound(
        remark="Hysteria with Xray Routing",
        port=60030,
        protocol="hysteria2",
        settings_dict={},
        stream_settings_dict=hysteria_stream_settings
    )
    
    try:
        xray_config = generate_xray_config_json()
        
        # Check that Xray created a SOCKS inbound on port (20000 + ib_id)
        socks_port = 20000 + ib_id
        socks_inbound = next((ib for ib in xray_config["inbounds"] if ib["port"] == socks_port), None)
        
        assert socks_inbound is not None
        assert socks_inbound["protocol"] == "socks"
        assert socks_inbound["listen"] == "127.0.0.1"
        assert socks_inbound["settings"]["accounts"][0]["user"] == "socks_user_xyz"
        assert socks_inbound["settings"]["accounts"][0]["pass"] == "socks_password_xyz"
        assert socks_inbound["settings"]["udp"] is True
    finally:
        delete_inbound(ib_id)


def test_xray_routing_loop_prevention_for_hysteria():
    """Test that routing rules targeting Hysteria outbounds automatically exclude Hysteria internal SOCKS5 inbounds."""
    from backend.database import add_outbound, delete_outbound, add_routing_rule, delete_routing_rule
    
    # 1. Create a VLESS inbound (standard client inbound)
    vless_id = add_inbound(
        remark="VLESS User Inbound",
        port=60040,
        protocol="vless",
        settings_dict={},
        stream_settings_dict={"network": "tcp"}
    )
    
    # 2. Create a Hysteria 2 inbound with Xray routing
    hys_settings = {
        "hysteria": {
            "routingViaXray": True,
            "socksUsername": "socks_user_abc",
            "socksPassword": "socks_password_abc"
        }
    }
    hys_id = add_inbound(
        remark="Hysteria Inbound",
        port=60041,
        protocol="hysteria2",
        settings_dict={},
        stream_settings_dict=hys_settings
    )
    
    # 3. Create a Hysteria outbound
    ob_id = add_outbound(
        remark="Hysteria Outbound Connection",
        protocol="hysteria",
        tag="hysteria-out-tag",
        settings_dict={"address": "127.0.0.1", "port": 443},
        enable=1
    )
    
    # 4. Create a catch-all routing rule to Hysteria outbound
    rule_id = add_routing_rule(
        remark="Route All to Hysteria Outbound",
        outbound_tag="hysteria-out-tag",
        inbound_tags=[],  # Empty list means "All Inbounds"
        enable=1
    )
    
    try:
        xray_config = generate_xray_config_json()
        routing_rules = xray_config["routing"]["rules"]
        
        # Find the rule matching our Hysteria outbound tag
        rule = next((r for r in routing_rules if r.get("outboundTag") == "hysteria-out-tag"), None)
        
        assert rule is not None
        # Should NOT be catch-all anymore. Should explicitly define inboundTag
        assert "inboundTag" in rule
        
        inbound_tags = rule["inboundTag"]
        # Should include the active VLESS inbound tag
        assert f"inbound-{vless_id}" in inbound_tags
        # Should NOT include the Hysteria internal SOCKS5 inbound tag
        assert f"inbound-{hys_id}-socks" not in inbound_tags
        
    finally:
        # Cleanup
        delete_inbound(vless_id)
        delete_inbound(hys_id)
        delete_outbound(ob_id)
        delete_routing_rule(rule_id)




