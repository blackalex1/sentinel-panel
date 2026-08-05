import json
import pytest
from backend.links_generator import get_client_links


def test_links_generator():
    """Test generated connection link strings formatting."""
    # VLESS Reality
    vless_inbound = {
        "protocol": "vless",
        "port": 443,
        "remark": "TestReality",
        "settings": json.dumps({
            "clients": [{"email": "alice", "flow": "xtls-rprx-vision"}]
        }),
        "stream_settings": json.dumps({
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "serverName": "google.com",
                "publicKey": "pubkey123",
                "shortIds": ["abc12345"]
            }
        })
    }
    vless_client = {"client_uuid_or_pwd": "user-uuid-1", "email": "alice"}
    links = get_client_links(vless_inbound, vless_client, "my-vpn-domain.com")
    
    assert len(links) == 1
    assert "vless://user-uuid-1@my-vpn-domain.com:443" in links[0]
    assert "security=reality" in links[0]
    assert "pbk=pubkey123" in links[0]
    assert "sni=google.com" in links[0]
    assert "sid=abc12345" in links[0]
    assert "flow=xtls-rprx-vision" in links[0]

    # VLESS gRPC
    vless_grpc_inbound = {
        "protocol": "vless",
        "port": 443,
        "remark": "TestgRPC",
        "settings": json.dumps({"clients": []}),
        "stream_settings": json.dumps({
            "network": "grpc",
            "security": "none",
            "grpcSettings": {"serviceName": "my-grpc-service"}
        })
    }
    vless_grpc_client = {"client_uuid_or_pwd": "user-uuid-grpc", "email": "bob"}
    grpc_links = get_client_links(vless_grpc_inbound, vless_grpc_client, "my-vpn-domain.com")
    assert "serviceName=my-grpc-service" in grpc_links[0]
    assert "type=grpc" in grpc_links[0]

    # Hysteria 2
    hyst_inbound = {
        "protocol": "hysteria2",
        "port": 8443,
        "remark": "TestHysteria",
        "settings": "{}",
        "stream_settings": json.dumps({
            "hysteria": {
                "obfsPassword": "obfs_link_pwd",
                "hop": "20000-30000"
            }
        })
    }
    hyst_client = {"client_uuid_or_pwd": "clientpass123", "email": "bob"}
    links = get_client_links(hyst_inbound, hyst_client, "1.2.3.4")
    
    assert len(links) == 1
    assert "hysteria2://bob:clientpass123@1.2.3.4:8443" in links[0]
    assert ("insecure=1" in links[0]) or ("pinSHA256=" in links[0])
    assert "sni=1.2.3.4" not in links[0]
    assert "obfs=salamander" in links[0]
    assert "obfs-password=obfs_link_pwd" in links[0]
    assert "hop=20000-30000" in links[0]


def test_advanced_links_generator():
    """Test link generator outputting advanced transports and VMess client alterId/security."""
    import base64
    # 1. VMess Client settings extraction
    vmess_inbound = {
        "protocol": "vmess",
        "port": 5001,
        "remark": "VMessLink",
        "settings": json.dumps({
            "clients": [{"email": "user1", "alterId": 64, "security": "aes-128-gcm"}]
        }),
        "stream_settings": json.dumps({
            "network": "h2",
            "security": "tls",
            "tlsSettings": {"serverName": "mysni.com"},
            "httpSettings": {"path": "/mypath", "host": ["myhost.com"]}
        })
    }
    client_stat = {"client_uuid_or_pwd": "my-uuid-xyz", "email": "user1"}
    
    links = get_client_links(vmess_inbound, client_stat, "myvpn.com")
    assert len(links) == 1
    
    # Decrypt base64 vmess link
    link = links[0]
    assert link.startswith("vmess://")
    b64_part = link.split("vmess://")[1]
    decoded = json.loads(base64.b64decode(b64_part.encode('utf-8')).decode('utf-8'))
    
    assert decoded["aid"] == 64
    assert decoded["scy"] == "aes-128-gcm"
    assert decoded["net"] == "h2"
    assert decoded["path"] == "/mypath"
    assert decoded["host"] == "myhost.com"
    assert decoded["sni"] == "mysni.com"

    # 2. Hysteria 2 Port Hopping link
    hyst_inbound = {
        "protocol": "hysteria2",
        "port": 6002,
        "remark": "HystLink",
        "settings": "{}",
        "stream_settings": json.dumps({
            "hysteria": {
                "obfsPassword": "obfspass",
                "hop": "10000-20000"
            }
        })
    }
    hyst_client = {"client_uuid_or_pwd": "pass", "email": "user1"}
    
    links = get_client_links(hyst_inbound, hyst_client, "1.1.1.1")
    assert "hop=10000-20000" in links[0]


def test_vless_encryption_link():
    """Test generated connection link containing VLESS Encryption key."""
    vless_inbound = {
        "protocol": "vless",
        "port": 443,
        "remark": "VlessEncLink",
        "settings": json.dumps({
            "clients": [{"email": "alice", "flow": "xtls-rprx-vision"}],
            "encryption": "mlkem768x25519plus.native.0rtt.myclientenckey"
        }),
        "stream_settings": json.dumps({
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "serverName": "google.com",
                "publicKey": "pubkey123",
                "shortIds": ["abc12345"]
            }
        })
    }
    vless_client = {"client_uuid_or_pwd": "user-uuid-1", "email": "alice"}
    links = get_client_links(vless_inbound, vless_client, "my-vpn-domain.com")
    
    assert len(links) == 1
    assert "encryption=mlkem768x25519plus.native.0rtt.myclientenckey" in links[0]


def test_vless_tls_fingerprint_alpn():
    """Test VLESS TLS link includes fp and alpn parameters."""
    vless_inbound = {
        "protocol": "vless",
        "port": 443,
        "remark": "VlessTLS",
        "settings": json.dumps({
            "clients": [{"email": "alice", "flow": ""}]
        }),
        "stream_settings": json.dumps({
            "network": "ws",
            "security": "tls",
            "tlsSettings": {
                "serverName": "mydomain.com",
                "alpn": ["h2", "http/1.1"],
                "fingerprint": "chrome"
            },
            "wsSettings": {"path": "/ws", "headers": {"Host": "mydomain.com"}}
        })
    }
    client = {"client_uuid_or_pwd": "uuid-tls-1", "email": "alice"}
    links = get_client_links(vless_inbound, client, "mydomain.com")
    
    assert len(links) == 1
    assert "fp=chrome" in links[0]
    assert "alpn=" in links[0]
    assert "sni=mydomain.com" in links[0]
    assert "type=ws" in links[0]


def test_trojan_tcp_type_and_tls_params():
    """Test Trojan link includes type=tcp and TLS fp/alpn."""
    trojan_inbound = {
        "protocol": "trojan",
        "port": 443,
        "remark": "TrojanTCP",
        "settings": json.dumps({"clients": []}),
        "stream_settings": json.dumps({
            "network": "tcp",
            "security": "tls",
            "tlsSettings": {
                "serverName": "example.com",
                "alpn": ["h2", "http/1.1"],
                "fingerprint": "firefox"
            },
            "tcpSettings": {"header": {"type": "none"}}
        })
    }
    client = {"client_uuid_or_pwd": "trojan-pass-1", "email": "bob"}
    links = get_client_links(trojan_inbound, client, "example.com")
    
    assert len(links) == 1
    assert "type=tcp" in links[0]
    assert "fp=firefox" in links[0]
    assert "alpn=" in links[0]
    assert "sni=example.com" in links[0]


def test_vmess_tls_alpn_fp():
    """Test VMess TLS link JSON includes alpn and fp fields."""
    import base64
    vmess_inbound = {
        "protocol": "vmess",
        "port": 443,
        "remark": "VMessTLS",
        "settings": json.dumps({
            "clients": [{"email": "user1", "alterId": 0, "security": "auto"}]
        }),
        "stream_settings": json.dumps({
            "network": "ws",
            "security": "tls",
            "tlsSettings": {
                "serverName": "ws.example.com",
                "alpn": ["h2", "http/1.1"],
                "fingerprint": "safari"
            },
            "wsSettings": {"path": "/vmess"}
        })
    }
    client = {"client_uuid_or_pwd": "vmess-uuid-1", "email": "user1"}
    links = get_client_links(vmess_inbound, client, "ws.example.com")
    
    assert len(links) == 1
    b64_part = links[0].split("vmess://")[1]
    decoded = json.loads(base64.b64decode(b64_part).decode('utf-8'))
    
    assert decoded["alpn"] == "h2,http/1.1"
    assert decoded["fp"] == "safari"
    assert decoded["sni"] == "ws.example.com"


def test_hysteria2_password_url_encoded():
    """Test Hysteria2 link correctly URL-encodes passwords with special chars."""
    hyst_inbound = {
        "protocol": "hysteria2",
        "port": 443,
        "remark": "HystSpecial",
        "settings": "{}",
        "stream_settings": json.dumps({
            "hysteria": {}
        })
    }
    client = {"client_uuid_or_pwd": "p@ss:word/test#123", "email": "user1"}
    links = get_client_links(hyst_inbound, client, "1.2.3.4")
    
    assert len(links) == 1
    # Password should be URL-encoded, not contain raw @ : / #
    assert "p%40ss%3Aword%2Ftest%23123" in links[0]
    assert "p@ss:word" not in links[0]


def test_hysteria2_custom_sni():
    """Test Hysteria2 link uses custom SNI from hysteria opts."""
    hyst_inbound = {
        "protocol": "hysteria2",
        "port": 443,
        "remark": "HystSNI",
        "settings": "{}",
        "stream_settings": json.dumps({
            "hysteria": {
                "sni": "custom-sni.example.com"
            }
        })
    }
    client = {"client_uuid_or_pwd": "pass123", "email": "user1"}
    links = get_client_links(hyst_inbound, client, "1.2.3.4")
    
    assert "sni=custom-sni.example.com" in links[0]


def test_vless_httpupgrade_link():
    """Test VLESS HTTPUpgrade transport link generation."""
    inbound = {
        "protocol": "vless",
        "port": 443,
        "remark": "VlessHTTPUp",
        "settings": json.dumps({"clients": [{"email": "alice", "flow": ""}]}),
        "stream_settings": json.dumps({
            "network": "httpupgrade",
            "security": "tls",
            "tlsSettings": {"serverName": "hu.example.com", "fingerprint": "chrome"},
            "httpupgradeSettings": {"path": "/upgrade", "host": "hu.example.com"}
        })
    }
    client = {"client_uuid_or_pwd": "uuid-hu", "email": "alice"}
    links = get_client_links(inbound, client, "hu.example.com")
    
    assert len(links) == 1
    assert "type=httpupgrade" in links[0]
    assert "path=%2Fupgrade" in links[0]
    assert "host=hu.example.com" in links[0]


def test_vless_xhttp_link():
    """Test VLESS XHTTP (SplitHTTP) transport link generation."""
    inbound = {
        "protocol": "vless",
        "port": 443,
        "remark": "VlessXHTTP",
        "settings": json.dumps({"clients": [{"email": "alice", "flow": ""}]}),
        "stream_settings": json.dumps({
            "network": "xhttp",
            "security": "reality",
            "realitySettings": {
                "serverName": "yahoo.com",
                "publicKey": "xhttpkey123",
                "shortIds": ["aabb"]
            },
            "xhttpSettings": {"path": "/xhttp", "host": "yahoo.com", "mode": "packet-up"}
        })
    }
    client = {"client_uuid_or_pwd": "uuid-xh", "email": "alice"}
    links = get_client_links(inbound, client, "myserver.com")
    
    assert len(links) == 1
    assert "type=xhttp" in links[0]
    assert "path=%2Fxhttp" in links[0]
    assert "mode=packet-up" in links[0]
    assert "pbk=xhttpkey123" in links[0]


def test_trojan_httpupgrade_link():
    """Test Trojan HTTPUpgrade transport link generation."""
    inbound = {
        "protocol": "trojan",
        "port": 443,
        "remark": "TrojanHTTPUp",
        "settings": json.dumps({"clients": []}),
        "stream_settings": json.dumps({
            "network": "httpupgrade",
            "security": "tls",
            "tlsSettings": {"serverName": "t.example.com"},
            "httpupgradeSettings": {"path": "/trojan-up"}
        })
    }
    client = {"client_uuid_or_pwd": "trojan-pass", "email": "bob"}
    links = get_client_links(inbound, client, "t.example.com")
    
    assert len(links) == 1
    assert "type=httpupgrade" in links[0]
    assert "path=%2Ftrojan-up" in links[0]


def test_mihomo_hysteria2_generator():
    """Test Mihomo proxy dict and YAML string generation for Hysteria 2."""
    import yaml
    from backend.links_generator import get_client_mihomo_proxy, get_client_mihomo_yaml

    hyst_inbound = {
        "protocol": "hysteria2",
        "port": 60000,
        "remark": "Germany",
        "settings": "{}",
        "stream_settings": json.dumps({
            "hysteria": {
                "obfsPassword": "obfs_secret_123",
                "hop": "60000-60999",
                "sni": "google.com"
            }
        })
    }
    hyst_client = {"client_uuid_or_pwd": "Jp56b19rOEhA70Yb", "email": "my_mihomo"}
    
    proxy_dict = get_client_mihomo_proxy(hyst_inbound, hyst_client, "203.0.113.14")
    assert proxy_dict["name"] == "Germany-my_mihomo"
    assert proxy_dict["type"] == "hysteria2"
    assert proxy_dict["server"] == "203.0.113.14"
    assert proxy_dict["port"] == 60000
    assert proxy_dict["ports"] == "60000-60999"
    assert proxy_dict["password"] == "my_mihomo:Jp56b19rOEhA70Yb"
    assert proxy_dict["sni"] == "google.com"
    assert proxy_dict["obfs"] == "salamander"
    assert proxy_dict["obfs-password"] == "obfs_secret_123"
    assert proxy_dict["skip-cert-verify"] is True

    yaml_str = get_client_mihomo_yaml(hyst_inbound, hyst_client, "203.0.113.14")
    assert "proxies:" in yaml_str
    assert "salamander" in yaml_str
    assert "60000-60999" in yaml_str

    # Validate that generated YAML parses correctly back to dict
    parsed = yaml.safe_load(yaml_str)
    assert len(parsed["proxies"]) == 1
    assert parsed["proxies"][0]["type"] == "hysteria2"


def test_mihomo_vless_reality_and_ss():
    """Test Mihomo proxy generation for VLESS REALITY and Shadowsocks."""
    from backend.links_generator import get_client_mihomo_proxy

    # VLESS Reality
    vless_inbound = {
        "protocol": "vless",
        "port": 443,
        "remark": "VlessRel",
        "settings": json.dumps({"clients": [{"email": "alice", "flow": "xtls-rprx-vision"}]}),
        "stream_settings": json.dumps({
            "network": "tcp",
            "security": "reality",
            "realitySettings": {
                "serverName": "apple.com",
                "publicKey": "pub123",
                "shortIds": ["sid1"]
            }
        })
    }
    client = {"client_uuid_or_pwd": "uuid-vless-1", "email": "alice"}
    proxy = get_client_mihomo_proxy(vless_inbound, client, "myvpn.com")
    assert proxy["type"] == "vless"
    assert proxy["uuid"] == "uuid-vless-1"
    assert proxy["flow"] == "xtls-rprx-vision"
    assert proxy["servername"] == "apple.com"
    assert proxy["reality-opts"]["public-key"] == "pub123"
    assert "cipher" not in proxy

    # Shadowsocks
    ss_inbound = {
        "protocol": "shadowsocks",
        "port": 8388,
        "remark": "SSNode",
        "settings": json.dumps({"method": "2022-blake3-aes-128-gcm"})
    }
    ss_client = {"client_uuid_or_pwd": "secretpassword", "email": "bob"}
    ss_proxy = get_client_mihomo_proxy(ss_inbound, ss_client, "myvpn.com")
    assert ss_proxy["type"] == "ss"
    assert ss_proxy["cipher"] == "2022-blake3-aes-128-gcm"
    assert ss_proxy["password"] == "secretpassword"


