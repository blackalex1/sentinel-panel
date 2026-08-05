import pytest
from backend.adapters import detect_best_engine, build_outbound_config, extract_common_outbound_params

def test_detect_best_engine():
    assert detect_best_engine("hysteria2", "auto") == "sing-box"
    assert detect_best_engine("hysteria", "auto") == "sing-box"
    assert detect_best_engine("vless", "auto") == "xray"
    assert detect_best_engine("vless", "sing-box") == "sing-box"
    assert detect_best_engine("hysteria2", "xray") == "xray"

def test_extract_common_outbound_params():
    settings = {
        "server": "my.server.com",
        "port": 443,
        "password": "secret_password"
    }
    stream_settings = {
        "sni": "my.server.com"
    }
    params = extract_common_outbound_params(settings, stream_settings)
    assert params["address"] == "my.server.com"
    assert params["port"] == 443
    assert params["password"] == "secret_password"
    assert params["sni"] == "my.server.com"

def test_build_singbox_outbound_hysteria2():
    settings = {"server": "1.2.3.4", "port": 60000, "password": "pass"}
    stream_settings = {"sni": "h2.domain.com"}
    sb = build_outbound_config("sing-box", "hysteria2", settings, stream_settings)
    assert sb["type"] == "hysteria2"
    assert sb["server"] == "1.2.3.4"
    assert sb["server_port"] == 60000
    assert sb["password"] == "pass"
    assert sb["tls"]["server_name"] == "h2.domain.com"

def test_build_xray_outbound_vless():
    settings = {"vnext": [{"address": "1.2.3.4", "port": 443, "users": [{"id": "uuid-123"}]}]}
    ob = build_outbound_config("xray", "vless", settings, {})
    assert ob["protocol"] == "vless"
    assert ob["settings"]["vnext"][0]["address"] == "1.2.3.4"
