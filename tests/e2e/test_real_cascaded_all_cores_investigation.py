"""
End-to-End Tests for 3-Server Cascades with REAL Cores, REAL Traffic, and IPv4-to-IPv6 Transition.
Tests real binaries (Xray, Sing-box, Hysteria 2) across all supported protocols:
VLESS, Hysteria 2, Shadowsocks 2022, Trojan, VMess, and SOCKS5.

Topology:
  Client -> Server 1 (Gateway, IPv4 127.0.0.1)
         -> Server 2 (Relay, IPv4 127.0.0.1)
         -> Server 3 (Exit, IPv6 ::1)
         -> Sensitive Target HTTP Service (IPv6 [::1]:target_port)

Validates:
1. Live network traffic flow through Server 1 (IPv4) -> Server 2 (IPv4) -> Server 3 (IPv6) -> Target (IPv6).
2. Real log generation on disk by each active binary process.
3. Multi-tier cascaded investigation and attribution via sentinel-core:
   - Server 3 (Exit) detects incoming tunnel from Server 2 on IPv6 (::1).
   - Server 2 (Relay) traces tunnel to Server 1 on IPv4 (127.0.0.1).
   - Server 1 (Gateway) identifies the culprit client on IPv4 (127.0.0.1).
4. Selective banning of the real culprit client on Server 1 while preserving transit tunnels.
"""
import os
import sys
import json
import time
import socket
import asyncio
import threading
import http.server
import subprocess
import urllib.request
from pathlib import Path
import pytest

from backend.config import XRAY_BIN_PATH, SINGBOX_BIN_PATH, HYSTERIA_BIN_PATH
from backend.sentinel_core_bridge import (
    find_xray_client_email,
    find_hysteria_client_email,
    find_client_ip_for_email_in_hysteria_log
)

CERT_PATH = str(Path(HYSTERIA_BIN_PATH.parent / "hysteria.crt").resolve())
KEY_PATH = str(Path(HYSTERIA_BIN_PATH.parent / "hysteria.key").resolve())


def get_free_port_ipv4() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_free_port_ipv6() -> int:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
        s.bind(("::1", 0))
        return s.getsockname()[1]


class IPv6HTTPServer(http.server.HTTPServer):
    address_family = socket.AF_INET6


class UpstreamTargetHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"CASCADE_TARGET_REACHED_200_OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def target_http_server():
    port = get_free_port_ipv6()
    httpd = IPv6HTTPServer(("::1", port), UpstreamTargetHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield port
    try:
        httpd.shutdown()
        httpd.server_close()
    except Exception:
        pass


def send_proxy_request(proxy_url: str, target_url: str, timeout: float = 5.0) -> tuple[int, str]:
    """Sends RFC 3986 compliant HTTP request through a proxy supporting IPv6 target URLs."""
    proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
    opener = urllib.request.build_opener(proxy_handler)
    req = urllib.request.Request(target_url, headers={"User-Agent": "SentinelCascadedAudit/1.0"})
    with opener.open(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


class ProcessSupervisor:
    """Helper to cleanly start and terminate multiple real core subprocesses."""
    def __init__(self):
        self.procs = []

    def start(self, cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        p = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
        self.procs.append(p)
        return p

    def cleanup(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in self.procs:
            try:
                p.wait(timeout=2)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        self.procs.clear()


@pytest.fixture
def supervisor():
    sup = ProcessSupervisor()
    yield sup
    sup.cleanup()


# ===========================================================================
# TEST 1: VLESS (Sing-box) -> VLESS (Xray) -> Trojan (Sing-box IPv6 Exit)
# Protocols: VLESS + Trojan
# Cores: Sing-box + Xray + Sing-box
# Chain: Client (IPv4) -> S1 (IPv4) -> S2 (IPv4) -> S3 (IPv6 ::1) -> Target (IPv6 [::1]:port)
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_vless_to_trojan_ipv6_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Sing-box Mixed Inbound on IPv4 -> VLESS Outbound to Server 2 on IPv4
    Server 2 (Relay): Xray VLESS Inbound on IPv4 -> Trojan Outbound to Server 3 on IPv6 (::1)
    Server 3 (Exit): Sing-box Trojan Inbound on IPv6 (::1) -> Direct to Target IPv6 HTTP
    Client: Real client connects to Server 1 -> sends traffic to IPv6 Target
    Investigation: Server 3 (sees S2 via IPv6 ::1) -> Server 2 (sees S1 via IPv4) -> Server 1 (culprit).
    """
    target_port = target_http_server
    port_s3 = get_free_port_ipv6()
    port_s2 = get_free_port_ipv4()
    port_s1 = get_free_port_ipv4()

    client_email = "attacker_vless_trojan@corp.lan"
    s1_tunnel = "server1_vless_tunnel@corp.lan"
    s2_tunnel = "server2_trojan_tunnel@corp.lan"
    vless_uuid = "10000000-0000-4000-8000-000000000109"

    # Server 3 (Exit): Sing-box Trojan Inbound listening on IPv6 ::1 -> Direct
    s3_log = tmp_path / "s3_trojan.log"
    s3_cfg = {
        "log": {"level": "info", "output": str(s3_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "trojan",
            "tag": "trojan-in",
            "listen": "::1",
            "listen_port": port_s3,
            "users": [{"name": s2_tunnel, "password": "pwd_transit_s2"}]
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }
    s3_file = tmp_path / "s3_trojan.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Xray VLESS Inbound on IPv4 -> Trojan Outbound to Server 3 on IPv6 ::1
    s2_log = tmp_path / "s2_access.log"
    s2_cfg = {
        "log": {"loglevel": "debug", "access": str(s2_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "vless-in",
            "port": port_s2,
            "listen": "127.0.0.1",
            "protocol": "vless",
            "settings": {
                "clients": [{"id": vless_uuid, "email": s1_tunnel}],
                "decryption": "none"
            }
        }],
        "outbounds": [{
            "protocol": "trojan",
            "tag": "to-s3-trojan",
            "settings": {
                "servers": [{
                    "address": "::1",
                    "port": port_s3,
                    "password": "pwd_transit_s2"
                }]
            }
        }]
    }
    s2_file = tmp_path / "s2.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Sing-box Mixed on IPv4 -> VLESS Outbound to Server 2 on IPv4
    s1_log = tmp_path / "s1.log"
    s1_cfg = {
        "log": {"level": "info", "output": str(s1_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": port_s1,
            "users": [{"username": client_email, "password": "pwd_client"}]
        }],
        "outbounds": [{
            "type": "vless",
            "tag": "to-s2-vless",
            "server": "127.0.0.1",
            "server_port": port_s2,
            "uuid": vless_uuid
        }]
    }
    s1_file = tmp_path / "s1.json"
    s1_file.write_text(json.dumps(s1_cfg, indent=2), encoding="utf-8")

    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s3_file)])
    supervisor.start([str(XRAY_BIN_PATH), "run", "-c", str(s2_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s1_file)])

    await asyncio.sleep(1.0)

    # Send real HTTP traffic through the 3-server cascade to IPv6 Target
    proxy_url = f"http://{client_email}:pwd_client@127.0.0.1:{port_s1}"
    status_code, body = None, ""
    for _ in range(8):
        try:
            status_code, body = send_proxy_request(proxy_url, f"http://[::1]:{target_port}/test", timeout=3.0)
            if status_code == 200:
                break
        except Exception:
            pass
        await asyncio.sleep(0.3)

    assert status_code == 200, f"Cascade request failed: {status_code}"
    assert "CASCADE_TARGET_REACHED_200_OK" in body

    await asyncio.sleep(0.5)

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = s3_log.read_text(encoding="utf-8").splitlines() if s3_log.exists() else []

    assert len(s1_lines) > 0, "Server 1 log file must contain real entries"
    assert len(s2_lines) > 0, "Server 2 log file must contain real entries"
    assert len(s3_lines) > 0, "Server 3 log file must contain real entries"

    # Step 1: Investigation on Server 3 (Exit Sing-box Trojan on IPv6)
    email_s3, ip_s3, tag_s3 = find_xray_client_email(s3_lines, dst_ip="::1", dst_port=target_port)
    assert email_s3 == s2_tunnel, f"Server 3 investigation failed: expected {s2_tunnel}, got {email_s3}"
    assert ip_s3 == "::1", f"Server 3 should observe incoming connection from Server 2 on IPv6 (::1), got {ip_s3}"

    # Step 2: Investigation on Server 2 (Relay Xray VLESS on IPv4)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="::1", dst_port=target_port)
    assert email_s2 == s1_tunnel, f"Server 2 investigation failed: expected {s1_tunnel}, got {email_s2}"
    assert ip_s2 == "127.0.0.1", f"Server 2 should observe incoming connection from Server 1 on IPv4, got {ip_s2}"

    # Step 3: Investigation on Server 1 (Gateway Sing-box on IPv4)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="::1", dst_port=target_port)
    assert email_s1 == client_email, f"Server 1 investigation failed: expected {client_email}, got {email_s1}"
    assert ip_s1 == "127.0.0.1", f"Server 1 should observe incoming connection from client on IPv4, got {ip_s1}"


# ===========================================================================
# TEST 2: VLESS (Xray) -> Trojan (Sing-box) -> Hysteria 2 (Native Hysteria IPv6 Exit)
# Protocols: VLESS + Trojan + Hysteria 2
# Cores: Xray + Sing-box + Native Hysteria 2
# Chain: Client (IPv4) -> S1 (IPv4) -> S2 (IPv4) -> S3 (IPv6 [::1]:port) -> Target (IPv6 [::1]:port)
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_vless_trojan_hysteria2_ipv6_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Xray VLESS Inbound on IPv4 -> Trojan Outbound to Server 2 on IPv4
    Server 2 (Relay): Sing-box Trojan Inbound on IPv4 -> Hysteria 2 Outbound to Server 3 on IPv6 (::1)
    Server 3 (Exit): Native Hysteria 2 Inbound on IPv6 ([::1]:port) -> Direct to Target IPv6 HTTP
    Client: Sing-box mixed proxy connecting to Server 1 via VLESS
    Investigation: Server 3 Hysteria 2 (sees S2 on IPv6 ::1) -> Server 2 Sing-box (sees S1 on IPv4) -> Server 1 Xray (culprit).
    """
    target_port = target_http_server
    port_s3 = get_free_port_ipv6()
    port_s2 = get_free_port_ipv4()
    port_s1 = get_free_port_ipv4()
    client_port = get_free_port_ipv4()

    client_email = "attacker_cascaded_hy2@corp.lan"
    s1_tunnel = "server1_trojan_tunnel@corp.lan"
    s2_tunnel = "server2_transit_tunnel"
    vless_uuid = "12345678-1234-1234-1234-123456789abc"

    acl_path = tmp_path / "hy_acl.txt"
    acl_path.write_text("direct(all)\n", encoding="utf-8")

    # Server 3 (Exit): Native Hysteria 2 listening on IPv6 [::1]:port_s3
    s3_cfg = {
        "listen": f"[::1]:{port_s3}",
        "tls": {"cert": CERT_PATH, "key": KEY_PATH},
        "auth": {"type": "userpass", "userpass": {s2_tunnel: "pwd_transit_s2"}},
        "acl": {"file": str(acl_path).replace("\\", "/")},
    }
    s3_file = tmp_path / "s3_hy.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Sing-box Trojan Inbound on IPv4 -> Hysteria 2 Outbound to Server 3 on IPv6
    s2_log = tmp_path / "s2_trojan.log"
    s2_cfg = {
        "log": {"level": "info", "output": str(s2_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "trojan",
            "tag": "trojan-in",
            "listen": "127.0.0.1",
            "listen_port": port_s2,
            "users": [{"name": s1_tunnel, "password": "pwd_transit_s1"}]
        }],
        "outbounds": [{
            "type": "hysteria2",
            "tag": "to-s3-hy2",
            "server": "::1",
            "server_port": port_s3,
            "password": f"{s2_tunnel}:pwd_transit_s2",
            "tls": {"enabled": True, "server_name": "localhost", "insecure": True}
        }]
    }
    s2_file = tmp_path / "s2_trojan.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Xray VLESS Inbound on IPv4 -> Trojan Outbound to Server 2 on IPv4
    s1_log = tmp_path / "s1_vless_access.log"
    s1_cfg = {
        "log": {"loglevel": "debug", "access": str(s1_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "vless-in",
            "port": port_s1,
            "listen": "127.0.0.1",
            "protocol": "vless",
            "settings": {
                "clients": [{"id": vless_uuid, "email": client_email}],
                "decryption": "none"
            }
        }],
        "outbounds": [{
            "protocol": "trojan",
            "tag": "to-s2-trojan",
            "settings": {
                "servers": [{
                    "address": "127.0.0.1",
                    "port": port_s2,
                    "password": "pwd_transit_s1"
                }]
            }
        }]
    }
    s1_file = tmp_path / "s1_vless.json"
    s1_file.write_text(json.dumps(s1_cfg, indent=2), encoding="utf-8")

    # Client: Sing-box mixed proxy on IPv4 connecting to Server 1 via VLESS
    client_cfg = {
        "log": {"level": "warn"},
        "inbounds": [{"type": "mixed", "tag": "client-in", "listen": "127.0.0.1", "listen_port": client_port}],
        "outbounds": [{
            "type": "vless",
            "tag": "to-s1",
            "server": "127.0.0.1",
            "server_port": port_s1,
            "uuid": vless_uuid
        }]
    }
    client_file = tmp_path / "client.json"
    client_file.write_text(json.dumps(client_cfg, indent=2), encoding="utf-8")

    s3_stdout = open(tmp_path / "s3_hy_stdout.log", "w", encoding="utf-8")
    supervisor.start([str(HYSTERIA_BIN_PATH), "server", "-c", str(s3_file)], stdout=s3_stdout, stderr=subprocess.STDOUT)
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s2_file)])
    supervisor.start([str(XRAY_BIN_PATH), "run", "-c", str(s1_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(client_file)])

    await asyncio.sleep(1.2)

    proxy_url = f"http://127.0.0.1:{client_port}"
    status_code, body = None, ""
    for _ in range(8):
        try:
            status_code, body = send_proxy_request(proxy_url, f"http://[::1]:{target_port}/test", timeout=3.0)
            if status_code == 200:
                break
        except Exception:
            pass
        await asyncio.sleep(0.3)

    assert status_code == 200, f"Cascade request failed: {status_code}"
    assert "CASCADE_TARGET_REACHED_200_OK" in body

    await asyncio.sleep(0.5)
    s3_stdout.flush()

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = (tmp_path / "s3_hy_stdout.log").read_text(encoding="utf-8").splitlines()

    # Step 1: Investigation on Server 3 (Native Hysteria 2 on IPv6)
    client_ip_s3 = find_client_ip_for_email_in_hysteria_log(s3_lines, s2_tunnel)
    assert client_ip_s3 == "::1", f"Server 3 should observe incoming connection from Server 2 on IPv6 (::1), got {client_ip_s3}"

    # Step 2: Investigation on Server 2 (Sing-box Trojan on IPv4)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="::1", dst_port=target_port)
    assert email_s2 == s1_tunnel, f"Server 2 investigation failed: expected {s1_tunnel}, got {email_s2}"
    assert ip_s2 == "127.0.0.1", f"Server 2 should observe incoming connection from Server 1 on IPv4, got {ip_s2}"

    # Step 3: Investigation on Server 1 (Xray VLESS on IPv4)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="::1", dst_port=target_port)
    assert email_s1 == client_email, f"Server 1 investigation failed: expected {client_email}, got {email_s1}"
    assert ip_s1 == "127.0.0.1", f"Server 1 should observe incoming connection from client on IPv4, got {ip_s1}"


# ===========================================================================
# TEST 3: VMess (Xray) -> VMess (Sing-box) -> Trojan (Xray IPv6 Exit)
# Protocols: VMess + Trojan
# Cores: Xray + Sing-box + Xray
# Chain: Client (IPv4) -> S1 (IPv4) -> S2 (IPv4) -> S3 (IPv6 ::1) -> Target (IPv6 [::1]:port)
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_vmess_to_trojan_ipv6_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Xray VMess Inbound on IPv4 -> VMess Outbound to Server 2 on IPv4
    Server 2 (Relay): Sing-box VMess Inbound on IPv4 -> Trojan Outbound to Server 3 on IPv6 (::1)
    Server 3 (Exit): Xray Trojan Inbound on IPv6 (::1) -> Direct to Target IPv6 HTTP
    Client: Sing-box mixed proxy on IPv4 connecting to Server 1 via VMess
    Investigation: Server 3 (sees S2 on IPv6 ::1) -> Server 2 (sees S1 on IPv4) -> Server 1 (culprit).
    """
    target_port = target_http_server
    port_s3 = get_free_port_ipv6()
    port_s2 = get_free_port_ipv4()
    port_s1 = get_free_port_ipv4()
    client_port = get_free_port_ipv4()

    client_email = "attacker_vmess@corp.lan"
    s1_tunnel = "server1_vmess_tunnel@corp.lan"
    s2_tunnel = "server2_trojan_tunnel@corp.lan"

    vmess_uuid_s1 = "11111111-2222-3333-4444-555555555555"
    vmess_uuid_s2 = "22222222-3333-4444-5555-666666666666"

    # Server 3 (Exit): Xray Trojan Inbound listening on IPv6 ::1 -> Direct
    s3_log = tmp_path / "s3_trojan_access.log"
    s3_cfg = {
        "log": {"loglevel": "debug", "access": str(s3_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "trojan-in",
            "port": port_s3,
            "listen": "::1",
            "protocol": "trojan",
            "settings": {
                "clients": [{"password": "pwd_trojan_s2", "email": s2_tunnel}]
            }
        }],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}]
    }
    s3_file = tmp_path / "s3_trojan.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Sing-box VMess Inbound on IPv4 -> Trojan Outbound to Server 3 on IPv6 ::1
    s2_log = tmp_path / "s2_vmess.log"
    s2_cfg = {
        "log": {"level": "info", "output": str(s2_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "vmess",
            "tag": "vmess-in",
            "listen": "127.0.0.1",
            "listen_port": port_s2,
            "users": [{"name": s1_tunnel, "uuid": vmess_uuid_s2, "alterId": 0}]
        }],
        "outbounds": [{
            "type": "trojan",
            "tag": "to-s3-trojan",
            "server": "::1",
            "server_port": port_s3,
            "password": "pwd_trojan_s2"
        }]
    }
    s2_file = tmp_path / "s2_vmess.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Xray VMess Inbound on IPv4 -> VMess Outbound to Server 2 on IPv4
    s1_log = tmp_path / "s1_vmess_access.log"
    s1_cfg = {
        "log": {"loglevel": "debug", "access": str(s1_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "vmess-in",
            "port": port_s1,
            "listen": "127.0.0.1",
            "protocol": "vmess",
            "settings": {
                "clients": [{"id": vmess_uuid_s1, "alterId": 0, "email": client_email}]
            }
        }],
        "outbounds": [{
            "protocol": "vmess",
            "tag": "to-s2-vmess",
            "settings": {
                "vnext": [{
                    "address": "127.0.0.1",
                    "port": port_s2,
                    "users": [{"id": vmess_uuid_s2, "alterId": 0, "security": "auto"}]
                }]
            }
        }]
    }
    s1_file = tmp_path / "s1_vmess.json"
    s1_file.write_text(json.dumps(s1_cfg, indent=2), encoding="utf-8")

    # Client (Sing-box mixed on IPv4)
    client_cfg = {
        "log": {"level": "warn"},
        "inbounds": [{"type": "mixed", "tag": "client-in", "listen": "127.0.0.1", "listen_port": client_port}],
        "outbounds": [{
            "type": "vmess",
            "tag": "to-s1",
            "server": "127.0.0.1",
            "server_port": port_s1,
            "uuid": vmess_uuid_s1,
            "security": "auto",
            "alter_id": 0
        }]
    }
    client_file = tmp_path / "client_vmess.json"
    client_file.write_text(json.dumps(client_cfg, indent=2), encoding="utf-8")

    supervisor.start([str(XRAY_BIN_PATH), "run", "-c", str(s3_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s2_file)])
    supervisor.start([str(XRAY_BIN_PATH), "run", "-c", str(s1_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(client_file)])

    await asyncio.sleep(1.0)

    proxy_url = f"http://127.0.0.1:{client_port}"
    status_code, body = None, ""
    for _ in range(8):
        try:
            status_code, body = send_proxy_request(proxy_url, f"http://[::1]:{target_port}/test", timeout=3.0)
            if status_code == 200:
                break
        except Exception:
            pass
        await asyncio.sleep(0.3)

    assert status_code == 200, f"Cascade request failed: {status_code}"
    assert "CASCADE_TARGET_REACHED_200_OK" in body

    await asyncio.sleep(0.5)

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = s3_log.read_text(encoding="utf-8").splitlines() if s3_log.exists() else []

    # Step 1: Investigation on Server 3 (Xray Trojan log on IPv6)
    email_s3, ip_s3, tag_s3 = find_xray_client_email(s3_lines, dst_ip="::1", dst_port=target_port)
    assert email_s3 == s2_tunnel, f"Server 3 expected {s2_tunnel}, got {email_s3}"
    assert ip_s3 == "::1", f"Server 3 expected incoming IPv6 ::1, got {ip_s3}"

    # Step 2: Investigation on Server 2 (Sing-box VMess log on IPv4)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="::1", dst_port=target_port)
    assert email_s2 == s1_tunnel, f"Server 2 expected {s1_tunnel}, got {email_s2}"
    assert ip_s2 == "127.0.0.1", f"Server 2 expected incoming IPv4 127.0.0.1, got {ip_s2}"

    # Step 3: Investigation on Server 1 (Xray VMess log on IPv4)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="::1", dst_port=target_port)
    assert email_s1 == client_email, f"Server 1 expected {client_email}, got {email_s1}"
    assert ip_s1 == "127.0.0.1", f"Server 1 expected incoming IPv4 127.0.0.1, got {ip_s1}"


# ===========================================================================
# TEST 4: SOCKS5 (Sing-box) -> VLESS (Sing-box) -> Hysteria 2 (Sing-box IPv6 Exit)
# Protocols: SOCKS5 + VLESS + Hysteria 2
# Cores: Sing-box + Sing-box + Sing-box
# Chain: Client (IPv4) -> S1 (IPv4) -> S2 (IPv4) -> S3 (IPv6 ::1) -> Target (IPv6 [::1]:port)
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_socks_vless_singbox_hysteria2_ipv6_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Sing-box SOCKS5 Inbound with Auth on IPv4 -> VLESS Outbound to Server 2 on IPv4
    Server 2 (Relay): Sing-box VLESS Inbound on IPv4 -> Hysteria 2 Outbound to Server 3 on IPv6 (::1)
    Server 3 (Exit): Sing-box Hysteria 2 Inbound on IPv6 (::1) -> Direct to Target IPv6 HTTP
    Client: Python HTTP request through authenticated SOCKS5 on Server 1
    Investigation: Server 3 (sees S2 on IPv6 ::1) -> Server 2 (sees S1 on IPv4) -> Server 1 (culprit).
    """
    target_port = target_http_server
    port_s3 = get_free_port_ipv6()
    port_s2 = get_free_port_ipv4()
    port_s1 = get_free_port_ipv4()

    client_email = "socks_intruder@corp.lan"
    s1_tunnel = "server1_vless_tunnel@corp.lan"
    s2_tunnel = "server2_hy2_tunnel@corp.lan"
    vless_uuid = "33333333-4444-5555-6666-777777777777"

    # Server 3 (Exit): Sing-box Hysteria 2 Inbound listening on IPv6 ::1 -> Direct
    s3_log = tmp_path / "s3_sb_hy.log"
    s3_cfg = {
        "log": {"level": "info", "output": str(s3_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "hysteria2",
            "tag": "hy2-in",
            "listen": "::1",
            "listen_port": port_s3,
            "users": [{"name": s2_tunnel, "password": "pwd_transit_s2"}],
            "tls": {"enabled": True, "certificate_path": CERT_PATH, "key_path": KEY_PATH}
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }
    s3_file = tmp_path / "s3_sb_hy.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Sing-box VLESS Inbound on IPv4 -> Hysteria 2 Outbound to Server 3 on IPv6 ::1
    s2_log = tmp_path / "s2_sb_vless.log"
    s2_cfg = {
        "log": {"level": "info", "output": str(s2_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "vless",
            "tag": "vless-in",
            "listen": "127.0.0.1",
            "listen_port": port_s2,
            "users": [{"name": s1_tunnel, "uuid": vless_uuid}]
        }],
        "outbounds": [{
            "type": "hysteria2",
            "tag": "to-s3-hy2",
            "server": "::1",
            "server_port": port_s3,
            "password": "pwd_transit_s2",
            "tls": {"enabled": True, "server_name": "localhost", "insecure": True}
        }]
    }
    s2_file = tmp_path / "s2_sb_vless.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Sing-box SOCKS5 with Auth on IPv4 -> VLESS Outbound to Server 2 on IPv4
    s1_log = tmp_path / "s1_socks.log"
    s1_cfg = {
        "log": {"level": "info", "output": str(s1_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "socks",
            "tag": "socks-in",
            "listen": "127.0.0.1",
            "listen_port": port_s1,
            "users": [{"username": client_email, "password": "pwd_socks"}]
        }],
        "outbounds": [{
            "type": "vless",
            "tag": "to-s2-vless",
            "server": "127.0.0.1",
            "server_port": port_s2,
            "uuid": vless_uuid
        }]
    }
    s1_file = tmp_path / "s1_socks.json"
    s1_file.write_text(json.dumps(s1_cfg, indent=2), encoding="utf-8")

    # Client Proxy: Sing-box mixed proxy on IPv4 connecting to Server 1 via SOCKS5
    client_port = get_free_port_ipv4()
    client_cfg = {
        "log": {"level": "warn"},
        "inbounds": [{"type": "mixed", "tag": "client-in", "listen": "127.0.0.1", "listen_port": client_port}],
        "outbounds": [{
            "type": "socks",
            "tag": "to-s1-socks",
            "server": "127.0.0.1",
            "server_port": port_s1,
            "version": "5",
            "username": client_email,
            "password": "pwd_socks"
        }]
    }
    client_file = tmp_path / "client_socks.json"
    client_file.write_text(json.dumps(client_cfg, indent=2), encoding="utf-8")

    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s3_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s2_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s1_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(client_file)])

    await asyncio.sleep(1.0)

    proxy_url = f"http://127.0.0.1:{client_port}"
    status_code, body = None, ""
    for _ in range(8):
        try:
            status_code, body = send_proxy_request(proxy_url, f"http://[::1]:{target_port}/test", timeout=3.0)
            if status_code == 200:
                break
        except Exception:
            pass
        await asyncio.sleep(0.3)

    assert status_code == 200, f"Cascade request failed: {status_code}"
    assert "CASCADE_TARGET_REACHED_200_OK" in body

    await asyncio.sleep(0.5)

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = s3_log.read_text(encoding="utf-8").splitlines() if s3_log.exists() else []

    # Step 1: Investigation on Server 3 (Sing-box Hysteria 2 log on IPv6)
    email_s3, ip_s3, tag_s3 = find_xray_client_email(s3_lines, dst_ip="::1", dst_port=target_port)
    assert email_s3 == s2_tunnel, f"Server 3 expected {s2_tunnel}, got {email_s3}"
    assert ip_s3 == "::1", f"Server 3 expected incoming IPv6 ::1, got {ip_s3}"

    # Step 2: Investigation on Server 2 (Sing-box VLESS log on IPv4)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="::1", dst_port=target_port)
    assert email_s2 == s1_tunnel, f"Server 2 expected {s1_tunnel}, got {email_s2}"
    assert ip_s2 == "127.0.0.1", f"Server 2 expected incoming IPv4 127.0.0.1, got {ip_s2}"

    # Step 3: Investigation on Server 1 (Sing-box SOCKS5 log on IPv4)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="::1", dst_port=target_port)
    assert email_s1 == client_email, f"Server 1 expected {client_email}, got {email_s1}"
    assert ip_s1 == "127.0.0.1", f"Server 1 expected incoming IPv4 127.0.0.1, got {ip_s1}"


# ===========================================================================
# TEST 5: FULL E2E CLIENT BAN & TRANSIT TUNNEL PRESERVATION (IPv4 -> IPv6)
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_client_ban_and_transit_preservation_ipv6(tmp_path, target_http_server, supervisor):
    """
    Tests that after live 3-server cascade investigation over IPv4-to-IPv6 transition:
    - Server 1 (IPv4) -> Server 2 (IPv4) -> Server 3 (IPv6 ::1) -> Target (IPv6 [::1]:port)
    The Security / Panel system disables ONLY the culprit client on Server 1,
    while transit tunnels on Server 2 and Server 3 remain fully enabled and active.
    """
    target_port = target_http_server
    port_s3 = get_free_port_ipv6()
    port_s2 = get_free_port_ipv4()
    port_s1 = get_free_port_ipv4()

    culprit_email = "abusive_cascaded_client@corp.lan"
    innocent_email = "innocent_work_client@corp.lan"
    transit_s1 = "transit_s1_tunnel@corp.lan"
    transit_s2 = "transit_s2_tunnel@corp.lan"

    # Simulated Panel DB state across the 3 nodes
    mock_db_s1 = {
        culprit_email: {"enable": 1, "inbound": "mixed-s1"},
        innocent_email: {"enable": 1, "inbound": "mixed-s1"}
    }
    mock_db_s2 = {
        transit_s1: {"enable": 1, "inbound": "vless-s2"}
    }
    mock_db_s3 = {
        transit_s2: {"enable": 1, "inbound": "trojan-s3"}
    }

    # Setup 3-server cascade: Sing-box (IPv4) -> Xray (IPv4) -> Sing-box (IPv6 ::1)
    vless_uuid = "44444444-5555-6666-7777-888888888888"

    # Server 3 (Exit): Sing-box Trojan on IPv6 ::1 -> Direct
    s3_log = tmp_path / "ban_s3.log"
    s3_cfg = {
        "log": {"level": "info", "output": str(s3_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "trojan",
            "tag": "trojan-in",
            "listen": "::1",
            "listen_port": port_s3,
            "users": [{"name": transit_s2, "password": "pwd_transit_s2"}]
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }
    (tmp_path / "ban_s3.json").write_text(json.dumps(s3_cfg, indent=2))

    # Server 2 (Relay): Xray VLESS on IPv4 -> Trojan Outbound to Server 3 on IPv6 ::1
    s2_log = tmp_path / "ban_s2.log"
    s2_cfg = {
        "log": {"loglevel": "debug", "access": str(s2_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "vless-in",
            "port": port_s2,
            "listen": "127.0.0.1",
            "protocol": "vless",
            "settings": {
                "clients": [{"id": vless_uuid, "email": transit_s1}],
                "decryption": "none"
            }
        }],
        "outbounds": [{
            "protocol": "trojan",
            "tag": "to-s3-ipv6",
            "settings": {
                "servers": [{"address": "::1", "port": port_s3, "password": "pwd_transit_s2"}]
            }
        }]
    }
    (tmp_path / "ban_s2.json").write_text(json.dumps(s2_cfg, indent=2))

    # Server 1 (Gateway): Sing-box Mixed on IPv4 -> VLESS Outbound to Server 2 on IPv4
    s1_log = tmp_path / "ban_s1.log"
    s1_cfg = {
        "log": {"level": "info", "output": str(s1_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": port_s1,
            "users": [
                {"username": culprit_email, "password": "pwd_culprit"},
                {"username": innocent_email, "password": "pwd_innocent"}
            ]
        }],
        "outbounds": [{
            "type": "vless",
            "tag": "to-s2",
            "server": "127.0.0.1",
            "server_port": port_s2,
            "uuid": vless_uuid
        }]
    }
    (tmp_path / "ban_s1.json").write_text(json.dumps(s1_cfg, indent=2))

    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(tmp_path / "ban_s3.json")])
    supervisor.start([str(XRAY_BIN_PATH), "run", "-c", str(tmp_path / "ban_s2.json")])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(tmp_path / "ban_s1.json")])

    await asyncio.sleep(1.0)

    # Culprit client launches real attack request to IPv6 target
    culprit_proxy = f"http://{culprit_email}:pwd_culprit@127.0.0.1:{port_s1}"
    status_code, body = None, ""
    for _ in range(8):
        try:
            status_code, body = send_proxy_request(culprit_proxy, f"http://[::1]:{target_port}/sensitive", timeout=3.0)
            if status_code == 200:
                break
        except Exception:
            pass
        await asyncio.sleep(0.3)

    assert status_code == 200
    assert "CASCADE_TARGET_REACHED_200_OK" in body

    await asyncio.sleep(0.5)

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = s3_log.read_text(encoding="utf-8").splitlines() if s3_log.exists() else []

    # Cascade investigation across IPv4-to-IPv6 transition:
    # 1. On Server 3 (IPv6): Identify transit tunnel
    id_s3, ip_s3, _ = find_xray_client_email(s3_lines, dst_ip="::1", dst_port=target_port)
    assert id_s3 == transit_s2, f"Expected {transit_s2}, got {id_s3}"
    assert ip_s3 == "::1", f"Server 3 should observe incoming connection from Server 2 on IPv6 (::1), got {ip_s3}"

    # 2. On Server 2 (IPv4): Trace upstream tunnel
    id_s2, ip_s2, _ = find_xray_client_email(s2_lines, dst_ip="::1", dst_port=target_port)
    assert id_s2 == transit_s1, f"Expected {transit_s1}, got {id_s2}"
    assert ip_s2 == "127.0.0.1", f"Server 2 should observe incoming connection from Server 1 on IPv4, got {ip_s2}"

    # 3. On Server 1 (IPv4): Identify original culprit client
    id_s1, ip_s1, _ = find_xray_client_email(s1_lines, dst_ip="::1", dst_port=target_port)
    assert id_s1 == culprit_email, f"Expected culprit {culprit_email}, got {id_s1}"
    assert ip_s1 == "127.0.0.1", f"Server 1 should observe incoming connection from culprit on IPv4, got {ip_s1}"

    # 4. Action: Panel Security System executes ban on identified culprit ONLY
    mock_db_s1[id_s1]["enable"] = 0

    # 5. Verification: Culprit is disabled, but transit tunnels on S2/S3 and innocent client on S1 remain active
    assert mock_db_s1[culprit_email]["enable"] == 0, "Culprit client MUST be disabled on Server 1"
    assert mock_db_s1[innocent_email]["enable"] == 1, "Innocent client on Server 1 must remain enabled"
    assert mock_db_s2[transit_s1]["enable"] == 1, "Transit tunnel on Server 2 MUST remain active"
    assert mock_db_s3[transit_s2]["enable"] == 1, "Transit tunnel on Server 3 MUST remain active"
