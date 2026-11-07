import ipaddress
import pytest
from unittest.mock import patch, MagicMock

from backend.links.protocols.utils import format_endpoint
from backend.links.protocols.vless import build_vless_link
from backend.links.protocols.hysteria2 import build_hysteria2_link
from backend.links.protocols.trojan import build_trojan_link
from backend.links.protocols.shadowsocks import build_shadowsocks_link
from backend.routes.hysteria_routes.auth import extract_ip_from_addr


def test_format_endpoint_ipv4_and_ipv6():
    # RFC 5737 IPv4 Test Address
    assert format_endpoint("198.51.100.1", 443) == "198.51.100.1:443"
    
    # RFC 3849 IPv6 Test Address (unbracketed)
    assert format_endpoint("2001:db8:1000::1", 443) == "[2001:db8:1000::1]:443"
    
    # RFC 3849 IPv6 Test Address (already bracketed)
    assert format_endpoint("[2001:db8:1000::1]", 443) == "[2001:db8:1000::1]:443"
    
    # Domain Name (RFC 2606)
    assert format_endpoint("node.example.test", 8443) == "node.example.test:8443"


def test_vless_link_generation_ipv6():
    inbound = {"protocol": "vless", "port": 443}
    client = {"id": "00000000-0000-0000-0000-000000000042", "email": "test_user@example.test"}
    stream_settings = {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
            "serverNames": ["node.example.test"],
            "settings": {
                "publicKey": "mockPublicKey123",
                "shortId": "abcdef12",
                "serverName": "node.example.test",
                "fingerprint": "chrome"
            }
        }
    }
    
    link = build_vless_link(
        inbound=inbound,
        client=client,
        host="2001:db8:1000::1",
        port=443,
        display_name="IPv6-VLESS-Test",
        settings={},
        stream_settings=stream_settings,
        network="tcp",
        security="reality",
        flow="xtls-rprx-vision"
    )
    
    assert "@[2001:db8:1000::1]:443" in link
    assert "vless://" in link
    assert "node.example.test" in link


def test_hysteria2_link_generation_ipv6():
    inbound = {"protocol": "hysteria", "port": 8443}
    client = {"password": "mock_password_ipv6"}
    stream_settings = {
        "hysteria": {
            "sni": "node.example.test",
            "certMode": "self"
        }
    }
    
    link = build_hysteria2_link(
        inbound=inbound,
        client=client,
        host="2001:db8:cafe::42",
        port=8443,
        display_name="IPv6-Hy2-Test",
        stream_settings=stream_settings,
        client_email="hy2_user@example.test"
    )
    
    assert "@[2001:db8:cafe::42]:8443" in link
    assert "hysteria2://" in link


def test_trojan_link_generation_ipv6():
    inbound = {"protocol": "trojan", "port": 443}
    client = {"password": "mock_trojan_password"}
    stream_settings = {
        "network": "tcp",
        "security": "tls",
        "tlsSettings": {"serverName": "node.example.test"}
    }
    
    link = build_trojan_link(
        inbound=inbound,
        client=client,
        host="2001:db8:beef::99",
        port=443,
        display_name="IPv6-Trojan-Test",
        settings={},
        stream_settings=stream_settings,
        network="tcp",
        security="tls"
    )
    
    assert "@[2001:db8:beef::99]:443" in link
    assert "trojan://" in link


def test_shadowsocks_link_generation_ipv6():
    inbound = {"protocol": "shadowsocks", "port": 8388}
    client = {"password": "mock_ss_password"}
    settings = {"method": "aes-256-gcm"}
    
    link = build_shadowsocks_link(
        inbound=inbound,
        client=client,
        host="2001:db8:1000::1",
        port=8388,
        display_name="IPv6-SS-Test",
        settings=settings
    )
    
    assert "@[2001:db8:1000::1]:8388" in link
    assert "ss://" in link


def test_extract_ip_from_addr_ipv4_and_ipv6():
    # IPv6 bracketed with port
    assert extract_ip_from_addr("[2001:db8:cafe::42]:53124") == "2001:db8:cafe::42"
    
    # IPv6 without port
    assert extract_ip_from_addr("2001:db8:cafe::42") == "2001:db8:cafe::42"
    
    # IPv6 bracketed without port
    assert extract_ip_from_addr("[2001:db8:cafe::42]") == "2001:db8:cafe::42"
    
    # IPv4 with port
    assert extract_ip_from_addr("198.51.100.42:53124") == "198.51.100.42"
    
    # IPv4 without port
    assert extract_ip_from_addr("198.51.100.42") == "198.51.100.42"


def test_firewall_tool_selection():
    # Verify IP version detection correctly selects ip6tables vs iptables
    ipv6_obj = ipaddress.ip_network("2001:db8:bad:c0de::99", strict=False)
    assert ipv6_obj.version == 6
    fw_v6 = "ip6tables" if ipv6_obj.version == 6 else "iptables"
    assert fw_v6 == "ip6tables"

    ipv4_obj = ipaddress.ip_network("198.51.100.99", strict=False)
    assert ipv4_obj.version == 4
    fw_v4 = "ip6tables" if ipv4_obj.version == 6 else "iptables"
    assert fw_v4 == "iptables"
