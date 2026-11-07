import base64
import json
import ipaddress
import pytest
from unittest.mock import patch, MagicMock

from backend.links.protocols.utils import format_endpoint
from backend.links.protocols.vless import build_vless_link
from backend.links.protocols.hysteria2 import build_hysteria2_link
from backend.links.protocols.trojan import build_trojan_link
from backend.links.protocols.shadowsocks import build_shadowsocks_link
from backend.links.protocols.vmess import build_vmess_link
from backend.proxy_rotator import parse_vpn_uri
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


def test_vmess_link_generation_ipv6():
    inbound = {"protocol": "vmess", "port": 443}
    client = {"id": "00000000-0000-0000-0000-000000000042", "email": "vmess_user@example.test"}
    stream_settings = {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {"serverName": "node.example.test"},
        "wsSettings": {"path": "/vmess-ws"}
    }
    
    link = build_vmess_link(
        inbound=inbound,
        client=client,
        host="2001:db8:1000::1",
        port=443,
        display_name="IPv6-VMess-Test",
        settings={},
        stream_settings=stream_settings,
        network="ws",
        security="tls",
        security_cipher="auto",
        alter_id=0
    )
    
    assert link.startswith("vmess://")
    b64_payload = link.replace("vmess://", "")
    decoded_json = json.loads(base64.b64decode(b64_payload + "==").decode("utf-8"))
    assert decoded_json["add"] == "2001:db8:1000::1"
    assert decoded_json["port"] == 443
    assert decoded_json["tls"] == "tls"
    assert decoded_json["net"] == "ws"


def test_parse_vpn_uri_all_ipv6_protocols():
    # 1. VLESS IPv6
    vless_uri = "vless://10000000-0000-4000-8000-000000000111@[2001:db8:1000::1]:443?type=tcp&security=reality&sni=node.example.test&pbk=key123&sid=ab12#VLESS6"
    res = parse_vpn_uri(vless_uri)
    assert res is not None
    assert res.get("protocol") == "vless"
    assert res.get("address") == "2001:db8:1000::1"
    assert res.get("port") == 443

    # 2. Hysteria 2 IPv6
    hy2_uri = "hysteria2://mock_pass@[2001:db8:cafe::42]:8443?sni=node.example.test#Hy2_6"
    res = parse_vpn_uri(hy2_uri)
    assert res is not None
    assert res.get("protocol") in ("hysteria2", "hy2")
    assert res.get("address") == "2001:db8:cafe::42"
    assert res.get("port") == 8443

    # 3. Trojan IPv6
    trojan_uri = "trojan://mock_pass@[2001:db8:beef::99]:443?security=tls#Trojan6"
    res = parse_vpn_uri(trojan_uri)
    assert res is not None
    assert res.get("protocol") == "trojan"
    assert res.get("address") == "2001:db8:beef::99"
    assert res.get("port") == 443

    # 4. Shadowsocks IPv6 (ULA)
    ss_uri = "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@[fd00::1]:8388#SS6"
    res = parse_vpn_uri(ss_uri)
    assert res is not None
    assert res.get("protocol") == "shadowsocks"
    assert res.get("address") == "fd00::1"
    assert res.get("port") == 8388

    # 5. TUIC IPv6
    tuic_uri = "tuic://10000000-0000-4000-8000-000000000111:pass@[2001:db8:2000::5]:8443?sni=node.example.test#TUIC6"
    res = parse_vpn_uri(tuic_uri)
    assert res is not None
    assert res.get("protocol") == "tuic"
    assert res.get("address") == "2001:db8:2000::5"
    assert res.get("port") == 8443

    # 6. WireGuard IPv6
    wg_uri = "wireguard://aGVsbG9fd2lyZWd1YXJkX3ByaXZhdGVfa2V5XzEyMw==@[2001:db8:3000::8]:51820?publickey=pubkey&ip=fd00::2/64#WG6"
    res = parse_vpn_uri(wg_uri)
    assert res is not None
    assert res.get("protocol") == "wireguard"
    assert res.get("address") == "2001:db8:3000::8"
    assert res.get("port") == 51820


def test_parse_vpn_uri_unbracketed_tolerance():
    # Verify unbracketed user link is normalized and parsed cleanly
    raw_unbracketed = "vless://10000000-0000-4000-8000-000000000111@2001:db8:1000::1:443?type=tcp&security=reality#Unbracketed"
    res = parse_vpn_uri(raw_unbracketed)
    assert res is not None
    assert res.get("address") == "2001:db8:1000::1"
    assert res.get("port") == 443


@pytest.mark.asyncio
async def test_firewall_bans_ip6tables_command():
    from backend.routes.security_routes.firewall import block_ip_api, _is_valid_ip_or_cidr
    from backend.routes.security_routes.bans import unban_ip

    assert _is_valid_ip_or_cidr("2001:db8:bad:c0de::99") is True
    assert _is_valid_ip_or_cidr("fd00::/8") is True
    assert _is_valid_ip_or_cidr("not-an-ip") is False

    mock_req = MagicMock()
    mock_req.headers = {}
    mock_req.cookies = {}
    mock_req.json = MagicMock()

    with patch("backend.routes.security_routes.firewall.check_auth", return_value=True), \
         patch("backend.routes.security_routes.bans.check_auth", return_value=True), \
         patch("os.name", "posix"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        # 1. Block IPv6
        await block_ip_api(mock_req, payload={"ip": "2001:db8:bad:c0de::99", "email": "test@example.test"})
        assert mock_run.called
        cmd_block = mock_run.call_args[0][0]
        assert cmd_block[0] == "ip6tables"
        assert "-s" in cmd_block
        assert "2001:db8:bad:c0de::99/128" in cmd_block or "2001:db8:bad:c0de::99" in cmd_block
        assert "DROP" in cmd_block

        # 2. Unban IPv6
        with patch("backend.database.get_setting", return_value="2001:db8:bad:c0de::99"), \
             patch("backend.database.set_setting"):
            await unban_ip(mock_req, ip="2001:db8:bad:c0de::99")
            cmd_unban = mock_run.call_args[0][0]
            assert cmd_unban[0] == "ip6tables"
            assert "-D" in cmd_unban
            assert "2001:db8:bad:c0de::99/128" in cmd_unban or "2001:db8:bad:c0de::99" in cmd_unban

