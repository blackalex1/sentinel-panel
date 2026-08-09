"""Standalone tests for proxy link generation — no database needed.

Previously used a script-style runner with sys.exit(1) which would kill the
entire pytest process on any failure. Rewritten as standard pytest functions.
"""
import json
import base64
import pytest

from backend.links.protocols.vless import build_vless_link
from backend.links.protocols.vmess import build_vmess_link
from backend.links.protocols.trojan import build_trojan_link
from backend.links.protocols.hysteria2 import build_hysteria2_link
from backend.links.protocols.shadowsocks import build_shadowsocks_link


# ─── VLESS ────────────────────────────────────────────────────────────────────

def test_vless_reality_link():
    link = build_vless_link(
        inbound={}, client={"client_uuid_or_pwd": "uuid-1"}, host="1.2.3.4", port=443,
        display_name="test", settings={}, stream_settings={
            "realitySettings": {
                "publicKey": "pk123", "serverNames": ["google.com"],
                "shortIds": ["ab12"], "fingerprint": "chrome", "spiderX": "/"
            }
        }, network="tcp", security="reality", flow="xtls-rprx-vision"
    )
    assert "vless://uuid-1@1.2.3.4:443" in link
    assert "security=reality" in link
    assert "pbk=pk123" in link
    assert "sni=google.com" in link
    assert "sid=ab12" in link
    assert "flow=xtls-rprx-vision" in link
    assert "fp=chrome" in link


def test_vless_tls_ws_link():
    link = build_vless_link(
        inbound={}, client={"client_uuid_or_pwd": "uuid-tls"}, host="example.com", port=443,
        display_name="test-tls", settings={}, stream_settings={
            "tlsSettings": {"serverName": "example.com", "alpn": ["h2", "http/1.1"], "fingerprint": "firefox"}
        }, network="ws", security="tls", flow=""
    )
    assert "fp=firefox" in link
    assert "alpn=" in link
    assert "sni=example.com" in link
    assert "type=ws" in link


def test_vless_httpupgrade_link():
    link = build_vless_link(
        inbound={}, client={"client_uuid_or_pwd": "uuid-hu"}, host="hu.com", port=443,
        display_name="test-hu", settings={}, stream_settings={
            "httpupgradeSettings": {"path": "/upgrade", "host": "hu.com"}
        }, network="httpupgrade", security="none", flow=""
    )
    assert "type=httpupgrade" in link
    assert "path=%2Fupgrade" in link
    assert "host=hu.com" in link


def test_vless_xhttp_link():
    link = build_vless_link(
        inbound={}, client={"client_uuid_or_pwd": "uuid-xh"}, host="xh.com", port=443,
        display_name="test-xh", settings={}, stream_settings={
            "xhttpSettings": {"path": "/xhttp", "host": "xh.com", "mode": "packet-up"}
        }, network="xhttp", security="none", flow=""
    )
    assert "type=xhttp" in link
    assert "path=%2Fxhttp" in link
    assert "mode=packet-up" in link


# ─── VMess ────────────────────────────────────────────────────────────────────

def test_vmess_tls_link():
    link = build_vmess_link(
        inbound={}, client={"client_uuid_or_pwd": "vmess-uuid"}, host="vmess.com", port=443,
        display_name="test-vmess", settings={}, stream_settings={
            "tlsSettings": {"serverName": "vmess.com", "alpn": ["h2", "http/1.1"], "fingerprint": "safari"}
        }, network="ws", security="tls", security_cipher="auto", alter_id=0
    )
    b64 = link.split("vmess://")[1]
    decoded = json.loads(base64.b64decode(b64).decode())
    assert decoded.get("alpn") == "h2,http/1.1", f"got alpn: {decoded.get('alpn')}"
    assert decoded.get("fp") == "safari", f"got fp: {decoded.get('fp')}"
    assert decoded.get("sni") == "vmess.com"


def test_vmess_httpupgrade_link():
    link = build_vmess_link(
        inbound={}, client={"client_uuid_or_pwd": "vmess-hu"}, host="hu.com", port=443,
        display_name="vmess-hu", settings={}, stream_settings={
            "httpupgradeSettings": {"path": "/vmess-up", "host": "hu.com"}
        }, network="httpupgrade", security="none", security_cipher="auto", alter_id=0
    )
    b64 = link.split("vmess://")[1]
    decoded = json.loads(base64.b64decode(b64).decode())
    assert decoded["net"] == "httpupgrade"
    assert decoded["path"] == "/vmess-up"


# ─── Trojan ───────────────────────────────────────────────────────────────────

def test_trojan_tcp_tls_link():
    link = build_trojan_link(
        inbound={}, client={"client_uuid_or_pwd": "trojan-pw"}, host="trojan.com", port=443,
        display_name="test-trojan", settings={}, stream_settings={
            "tlsSettings": {"serverName": "trojan.com", "alpn": ["h2"], "fingerprint": "edge"},
            "tcpSettings": {"header": {"type": "none"}}
        }, network="tcp", security="tls"
    )
    assert "type=tcp" in link
    assert "fp=edge" in link
    assert "alpn=" in link


def test_trojan_httpupgrade_link():
    link = build_trojan_link(
        inbound={}, client={"client_uuid_or_pwd": "trojan-pw"}, host="tru.com", port=443,
        display_name="trojan-hu", settings={}, stream_settings={
            "httpupgradeSettings": {"path": "/trojan-up"}
        }, network="httpupgrade", security="tls"
    )
    assert "type=httpupgrade" in link
    assert "path=%2Ftrojan-up" in link


# ─── Hysteria2 ────────────────────────────────────────────────────────────────

def test_hysteria2_password_url_encoding():
    link = build_hysteria2_link(
        inbound={}, client={"client_uuid_or_pwd": "p@ss:word/test#123"},
        host="1.2.3.4", port=443, display_name="hyst-enc",
        stream_settings={"hysteria": {}}, client_email="user1"
    )
    assert "p%40ss%3Aword%2Ftest%23123" in link, f"password not URL-encoded in: {link}"
    assert "p@ss:word" not in link, "raw special chars leaked into link"


def test_hysteria2_custom_sni():
    link = build_hysteria2_link(
        inbound={}, client={"client_uuid_or_pwd": "pass123"},
        host="1.2.3.4", port=443, display_name="hyst-sni",
        stream_settings={"hysteria": {"sni": "custom.example.com"}}, client_email="user1"
    )
    assert "sni=custom.example.com" in link


def test_hysteria2_no_sni_for_ip_host():
    """When host is a raw IP, SNI should not be set to the IP address."""
    link = build_hysteria2_link(
        inbound={}, client={"client_uuid_or_pwd": "pass"},
        host="1.2.3.4", port=443, display_name="hyst-ip",
        stream_settings={"hysteria": {}}, client_email="user1"
    )
    assert "sni=" not in link, f"unexpected sni in IP-only link: {link}"


# ─── Shadowsocks ──────────────────────────────────────────────────────────────

def test_shadowsocks_link():
    link = build_shadowsocks_link(
        inbound={}, client={"client_uuid_or_pwd": "ss-pass"},
        host="1.2.3.4", port=8388, display_name="ss-test",
        settings={"method": "2022-blake3-aes-256-gcm"}
    )
    assert link.startswith("ss://")
    assert "1.2.3.4:8388" in link
