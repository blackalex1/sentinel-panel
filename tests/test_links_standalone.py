"""Standalone test for link generation - no database needed."""
import json
import base64
import sys
sys.path.insert(0, ".")

from backend.links.protocols.vless import build_vless_link
from backend.links.protocols.vmess import build_vmess_link
from backend.links.protocols.trojan import build_trojan_link
from backend.links.protocols.hysteria2 import build_hysteria2_link
from backend.links.protocols.shadowsocks import build_shadowsocks_link

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")

print("\n=== 1. VLESS Reality ===")
link = build_vless_link(
    inbound={}, client={"client_uuid_or_pwd": "uuid-1"}, host="1.2.3.4", port=443,
    display_name="test", settings={}, stream_settings={
        "realitySettings": {"publicKey": "pk123", "serverNames": ["google.com"], "shortIds": ["ab12"], "fingerprint": "chrome", "spiderX": "/"}
    }, network="tcp", security="reality", flow="xtls-rprx-vision"
)
check("has uuid", "vless://uuid-1@1.2.3.4:443" in link)
check("has security=reality", "security=reality" in link)
check("has pbk", "pbk=pk123" in link)
check("has sni", "sni=google.com" in link)
check("has sid", "sid=ab12" in link)
check("has flow", "flow=xtls-rprx-vision" in link)
check("has fp", "fp=chrome" in link)

print("\n=== 2. VLESS TLS (fp + alpn) ===")
link = build_vless_link(
    inbound={}, client={"client_uuid_or_pwd": "uuid-tls"}, host="example.com", port=443,
    display_name="test-tls", settings={}, stream_settings={
        "tlsSettings": {"serverName": "example.com", "alpn": ["h2", "http/1.1"], "fingerprint": "firefox"}
    }, network="ws", security="tls", flow=""
)
check("has fp=firefox", "fp=firefox" in link)
check("has alpn", "alpn=" in link)
check("has sni", "sni=example.com" in link)
check("has type=ws", "type=ws" in link)

print("\n=== 3. VLESS HTTPUpgrade ===")
link = build_vless_link(
    inbound={}, client={"client_uuid_or_pwd": "uuid-hu"}, host="hu.com", port=443,
    display_name="test-hu", settings={}, stream_settings={
        "httpupgradeSettings": {"path": "/upgrade", "host": "hu.com"}
    }, network="httpupgrade", security="none", flow=""
)
check("has type=httpupgrade", "type=httpupgrade" in link)
check("has path", "path=%2Fupgrade" in link)
check("has host", "host=hu.com" in link)

print("\n=== 4. VLESS XHTTP ===")
link = build_vless_link(
    inbound={}, client={"client_uuid_or_pwd": "uuid-xh"}, host="xh.com", port=443,
    display_name="test-xh", settings={}, stream_settings={
        "xhttpSettings": {"path": "/xhttp", "host": "xh.com", "mode": "packet-up"}
    }, network="xhttp", security="none", flow=""
)
check("has type=xhttp", "type=xhttp" in link)
check("has path", "path=%2Fxhttp" in link)
check("has mode=packet-up", "mode=packet-up" in link)

print("\n=== 5. VMess TLS (alpn + fp) ===")
link = build_vmess_link(
    inbound={}, client={"client_uuid_or_pwd": "vmess-uuid"}, host="vmess.com", port=443,
    display_name="test-vmess", settings={}, stream_settings={
        "tlsSettings": {"serverName": "vmess.com", "alpn": ["h2", "http/1.1"], "fingerprint": "safari"}
    }, network="ws", security="tls", security_cipher="auto", alter_id=0
)
b64 = link.split("vmess://")[1]
decoded = json.loads(base64.b64decode(b64).decode())
check("has alpn", decoded.get("alpn") == "h2,http/1.1", f"got: {decoded.get('alpn')}")
check("has fp=safari", decoded.get("fp") == "safari", f"got: {decoded.get('fp')}")
check("has sni", decoded.get("sni") == "vmess.com")

print("\n=== 6. VMess HTTPUpgrade ===")
link = build_vmess_link(
    inbound={}, client={"client_uuid_or_pwd": "vmess-hu"}, host="hu.com", port=443,
    display_name="vmess-hu", settings={}, stream_settings={
        "httpupgradeSettings": {"path": "/vmess-up", "host": "hu.com"}
    }, network="httpupgrade", security="none", security_cipher="auto", alter_id=0
)
b64 = link.split("vmess://")[1]
decoded = json.loads(base64.b64decode(b64).decode())
check("net=httpupgrade", decoded["net"] == "httpupgrade")
check("path=/vmess-up", decoded["path"] == "/vmess-up")

print("\n=== 7. Trojan TCP (type=tcp + fp + alpn) ===")
link = build_trojan_link(
    inbound={}, client={"client_uuid_or_pwd": "trojan-pw"}, host="trojan.com", port=443,
    display_name="test-trojan", settings={}, stream_settings={
        "tlsSettings": {"serverName": "trojan.com", "alpn": ["h2"], "fingerprint": "edge"},
        "tcpSettings": {"header": {"type": "none"}}
    }, network="tcp", security="tls"
)
check("has type=tcp", "type=tcp" in link)
check("has fp=edge", "fp=edge" in link)
check("has alpn", "alpn=" in link)

print("\n=== 8. Trojan HTTPUpgrade ===")
link = build_trojan_link(
    inbound={}, client={"client_uuid_or_pwd": "trojan-pw"}, host="tru.com", port=443,
    display_name="trojan-hu", settings={}, stream_settings={
        "httpupgradeSettings": {"path": "/trojan-up"}
    }, network="httpupgrade", security="tls"
)
check("has type=httpupgrade", "type=httpupgrade" in link)
check("has path", "path=%2Ftrojan-up" in link)

print("\n=== 9. Hysteria2 URL-encode password ===")
link = build_hysteria2_link(
    inbound={}, client={"client_uuid_or_pwd": "p@ss:word/test#123"},
    host="1.2.3.4", port=443, display_name="hyst-enc",
    stream_settings={"hysteria": {}}, client_email="user1"
)
check("password encoded", "p%40ss%3Aword%2Ftest%23123" in link)
check("no raw special chars", "p@ss:word" not in link)

print("\n=== 10. Hysteria2 custom SNI ===")
link = build_hysteria2_link(
    inbound={}, client={"client_uuid_or_pwd": "pass123"},
    host="1.2.3.4", port=443, display_name="hyst-sni",
    stream_settings={"hysteria": {"sni": "custom.example.com"}}, client_email="user1"
)
check("has custom sni", "sni=custom.example.com" in link)

print("\n=== 11. Hysteria2 no SNI for IP ===")
link = build_hysteria2_link(
    inbound={}, client={"client_uuid_or_pwd": "pass"},
    host="1.2.3.4", port=443, display_name="hyst-ip",
    stream_settings={"hysteria": {}}, client_email="user1"
)
check("no sni for IP", "sni=" not in link)

print("\n=== 12. Shadowsocks ===")
link = build_shadowsocks_link(
    inbound={}, client={"client_uuid_or_pwd": "ss-pass"},
    host="1.2.3.4", port=8388, display_name="ss-test",
    settings={"method": "2022-blake3-aes-256-gcm"}
)
check("starts with ss://", link.startswith("ss://"))
check("has host:port", "1.2.3.4:8388" in link)

print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")
if failed > 0:
    sys.exit(1)
else:
    print("All tests passed!")
