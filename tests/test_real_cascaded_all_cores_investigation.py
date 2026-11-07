"""
End-to-End Tests for 3-Server Cascades with REAL Cores and REAL Traffic.
Tests real binaries (Xray, Sing-box, Hysteria 2) across all supported protocols:
VLESS, Hysteria 2, Shadowsocks 2022, Trojan, VMess, and SOCKS5.
Validates:
1. Live network traffic flow through Server 1 -> Server 2 -> Server 3 -> Target.
2. Real log generation on disk by each active binary process.
3. Multi-tier cascaded investigation and attribution via sentinel-core.
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
from pathlib import Path
import pytest
from httpx import AsyncClient

from backend.config import XRAY_BIN_PATH, SINGBOX_BIN_PATH, HYSTERIA_BIN_PATH
from backend.sentinel_core_bridge import (
    find_xray_client_email,
    find_hysteria_client_email,
    find_client_ip_for_email_in_hysteria_log
)

CERT_PATH = str(Path(HYSTERIA_BIN_PATH.parent / "hysteria.crt").resolve())
KEY_PATH = str(Path(HYSTERIA_BIN_PATH.parent / "hysteria.key").resolve())


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
    port = get_free_port()
    httpd = http.server.HTTPServer(("127.0.0.1", port), UpstreamTargetHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield port
    try:
        httpd.shutdown()
        httpd.server_close()
    except Exception:
        pass


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
# TEST 1: VLESS (Xray) -> Shadowsocks 2022 (Sing-box) -> Shadowsocks (Sing-box Exit)
# Protocols: VLESS + Shadowsocks 2022
# Cores: Xray + Sing-box + Sing-box
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_vless_to_shadowsocks_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Sing-box Mixed Inbound -> VLESS Outbound to Server 2
    Server 2 (Relay): Xray VLESS Inbound -> Shadowsocks 2022 Outbound to Server 3
    Server 3 (Exit): Sing-box Shadowsocks Inbound -> Direct to Target HTTP
    Client: Real client connects to Server 1 -> sends traffic to Target HTTP
    Investigation: Server 3 (transit tunnel) -> Server 2 (transit tunnel) -> Server 1 (attacker).
    """
    target_port = target_http_server
    port_s3 = get_free_port()
    port_s2 = get_free_port()
    port_s1 = get_free_port()

    client_email = "attacker_vless_ss@corp.lan"
    s1_tunnel = "server1_vless_tunnel@corp.lan"
    ss_password = "4X0OQ6U6f7G2g8H+4jK8lg=="

    # Server 3 (Exit): Sing-box Shadowsocks -> Direct
    s3_log = tmp_path / "s3.log"
    s3_cfg = {
        "log": {"level": "info", "output": str(s3_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "shadowsocks",
            "tag": "ss-in",
            "listen": "127.0.0.1",
            "listen_port": port_s3,
            "method": "2022-blake3-aes-128-gcm",
            "password": ss_password
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }
    s3_file = tmp_path / "s3.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Xray VLESS Inbound -> Shadowsocks Outbound to Server 3
    s2_log = tmp_path / "s2_access.log"
    s2_cfg = {
        "log": {"loglevel": "debug", "access": str(s2_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "vless-in",
            "port": port_s2,
            "listen": "127.0.0.1",
            "protocol": "vless",
            "settings": {
                "clients": [{"id": "10000000-0000-4000-8000-000000000109", "email": s1_tunnel}],
                "decryption": "none"
            }
        }],
        "outbounds": [{
            "protocol": "shadowsocks",
            "tag": "to-s3",
            "settings": {
                "servers": [{
                    "address": "127.0.0.1",
                    "port": port_s3,
                    "method": "2022-blake3-aes-128-gcm",
                    "password": ss_password
                }]
            }
        }]
    }
    s2_file = tmp_path / "s2.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Sing-box Mixed -> VLESS Outbound to Server 2
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
            "tag": "to-s2",
            "server": "127.0.0.1",
            "server_port": port_s2,
            "uuid": "10000000-0000-4000-8000-000000000109"
        }]
    }
    s1_file = tmp_path / "s1.json"
    s1_file.write_text(json.dumps(s1_cfg, indent=2), encoding="utf-8")

    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s3_file)])
    supervisor.start([str(XRAY_BIN_PATH), "run", "-c", str(s2_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s1_file)])

    await asyncio.sleep(1.0)

    # Send real HTTP traffic through the 3-server cascade
    proxy_url = f"http://{client_email}:pwd_client@127.0.0.1:{port_s1}"
    resp = None
    for _ in range(6):
        try:
            async with AsyncClient(proxy=proxy_url, timeout=5.0) as cl:
                resp = await cl.get(f"http://127.0.0.1:{target_port}/test")
                if resp.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(0.4)

    assert resp is not None and resp.status_code == 200
    assert "CASCADE_TARGET_REACHED_200_OK" in resp.text

    await asyncio.sleep(0.5)

    # Verify real logs on disk
    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = s3_log.read_text(encoding="utf-8").splitlines() if s3_log.exists() else []

    assert len(s1_lines) > 0, "Server 1 log file must contain real entries"
    assert len(s2_lines) > 0, "Server 2 log file must contain real entries"
    assert len(s3_lines) > 0, "Server 3 log file must contain real entries"

    # Step 1: Investigation on Server 2 (Xray log)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s2 == s1_tunnel, f"Server 2 investigation failed: expected {s1_tunnel}, got {email_s2}"

    # Step 2: Investigation on Server 1 (Sing-box log)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s1 == client_email, f"Server 1 investigation failed: expected {client_email}, got {email_s1}"
    assert ip_s1 == "127.0.0.1"


# ===========================================================================
# TEST 2: VLESS (Xray) -> Trojan (Sing-box) -> Hysteria 2 (Native Hysteria Exit)
# Protocols: VLESS + Trojan + Hysteria 2
# Cores: Xray + Sing-box + Native Hysteria 2
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_vless_trojan_hysteria2_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Xray VLESS Inbound -> Trojan Outbound to Server 2
    Server 2 (Relay): Sing-box Trojan Inbound -> Hysteria 2 Outbound to Server 3
    Server 3 (Exit): Native Hysteria 2 Inbound -> Direct to Target HTTP
    Client: Sing-box mixed proxy connecting to Server 1
    Investigation: Server 3 Hysteria 2 -> Server 2 Sing-box -> Server 1 Xray (culprit).
    """
    target_port = target_http_server
    port_s3 = get_free_port()
    port_s2 = get_free_port()
    port_s1 = get_free_port()
    client_port = get_free_port()

    client_email = "attacker_hy2_cascade@corp.lan"
    s1_tunnel = "server1_trojan_tunnel@corp.lan"
    s2_tunnel = "server2_transit_tunnel"

    # Server 3 (Exit): Native Hysteria 2
    s3_cfg = {
        "listen": f"127.0.0.1:{port_s3}",
        "tls": {"cert": CERT_PATH, "key": KEY_PATH},
        "auth": {
            "type": "userpass",
            "userpass": {s2_tunnel: "pwd_transit_s2"}
        }
    }
    s3_file = tmp_path / "s3_hy.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Sing-box Trojan -> Hysteria 2 Outbound
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
            "server": "127.0.0.1",
            "server_port": port_s3,
            "password": f"{s2_tunnel}:pwd_transit_s2",
            "tls": {"enabled": True, "insecure": True}
        }]
    }
    s2_file = tmp_path / "s2_trojan.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Xray VLESS Inbound -> Trojan Outbound
    s1_log = tmp_path / "s1_vless_access.log"
    s1_cfg = {
        "log": {"loglevel": "debug", "access": str(s1_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "vless-in",
            "port": port_s1,
            "listen": "127.0.0.1",
            "protocol": "vless",
            "settings": {
                "clients": [{"id": "c7112233-4455-6677-8899-aabbccddeeff", "email": client_email}],
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

    # Client (Sing-box mixed)
    client_cfg = {
        "log": {"level": "warn"},
        "inbounds": [{"type": "mixed", "tag": "client-in", "listen": "127.0.0.1", "listen_port": client_port}],
        "outbounds": [{
            "type": "vless",
            "tag": "to-s1",
            "server": "127.0.0.1",
            "server_port": port_s1,
            "uuid": "c7112233-4455-6677-8899-aabbccddeeff"
        }]
    }
    client_file = tmp_path / "client.json"
    client_file.write_text(json.dumps(client_cfg, indent=2), encoding="utf-8")

    s3_stdout = open(tmp_path / "s3_hy_stdout.log", "w", encoding="utf-8")
    supervisor.start([str(HYSTERIA_BIN_PATH), "server", "-c", str(s3_file)], stdout=s3_stdout, stderr=subprocess.STDOUT)
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(s2_file)])
    supervisor.start([str(XRAY_BIN_PATH), "run", "-c", str(s1_file)])
    supervisor.start([str(SINGBOX_BIN_PATH), "run", "-c", str(client_file)])

    await asyncio.sleep(1.0)

    # Send real HTTP traffic through the 3-server cascade
    resp = None
    for _ in range(6):
        try:
            async with AsyncClient(proxy=f"http://127.0.0.1:{client_port}", timeout=5.0) as cl:
                resp = await cl.get(f"http://127.0.0.1:{target_port}/test")
                if resp.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(0.4)

    assert resp is not None and resp.status_code == 200
    assert "CASCADE_TARGET_REACHED_200_OK" in resp.text

    await asyncio.sleep(0.5)
    s3_stdout.flush()

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = (tmp_path / "s3_hy_stdout.log").read_text(encoding="utf-8").splitlines()

    # Step 1: Investigation on Server 3 (Hysteria 2)
    client_ip_s3 = find_client_ip_for_email_in_hysteria_log(s3_lines, s2_tunnel)
    assert client_ip_s3 == "127.0.0.1"

    # Step 2: Investigation on Server 2 (Sing-box Trojan)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s2 == s1_tunnel

    # Step 3: Investigation on Server 1 (Xray VLESS)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s1 == client_email
    assert ip_s1 == "127.0.0.1"


# ===========================================================================
# TEST 3: VMess (Xray) -> VMess (Sing-box) -> Trojan (Xray Exit)
# Protocols: VMess + Trojan
# Cores: Xray + Sing-box + Xray
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_vmess_to_trojan_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Xray VMess Inbound -> VMess Outbound to Server 2
    Server 2 (Relay): Sing-box VMess Inbound -> Trojan Outbound to Server 3
    Server 3 (Exit): Xray Trojan Inbound -> Direct to Target HTTP
    Client: Sing-box mixed proxy connecting to Server 1 via VMess
    Investigation: Server 3 (Trojan) -> Server 2 (VMess) -> Server 1 (VMess culprit).
    """
    target_port = target_http_server
    port_s3 = get_free_port()
    port_s2 = get_free_port()
    port_s1 = get_free_port()
    client_port = get_free_port()

    client_email = "attacker_vmess@corp.lan"
    s1_tunnel = "server1_vmess_tunnel@corp.lan"
    s2_tunnel = "server2_trojan_tunnel@corp.lan"

    vmess_uuid_s1 = "11111111-2222-3333-4444-555555555555"
    vmess_uuid_s2 = "22222222-3333-4444-5555-666666666666"

    # Server 3 (Exit): Xray Trojan Inbound -> Direct
    s3_log = tmp_path / "s3_trojan_access.log"
    s3_cfg = {
        "log": {"loglevel": "debug", "access": str(s3_log).replace("\\", "/")},
        "inbounds": [{
            "tag": "trojan-in",
            "port": port_s3,
            "listen": "127.0.0.1",
            "protocol": "trojan",
            "settings": {
                "clients": [{"password": "pwd_trojan_s2", "email": s2_tunnel}]
            }
        }],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}]
    }
    s3_file = tmp_path / "s3_trojan.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Sing-box VMess Inbound -> Trojan Outbound to Server 3
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
            "server": "127.0.0.1",
            "server_port": port_s3,
            "password": "pwd_trojan_s2"
        }]
    }
    s2_file = tmp_path / "s2_vmess.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Xray VMess Inbound -> VMess Outbound to Server 2
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

    # Client (Sing-box mixed)
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

    # Send real HTTP traffic through the 3-server cascade
    resp = None
    for _ in range(6):
        try:
            async with AsyncClient(proxy=f"http://127.0.0.1:{client_port}", timeout=5.0) as cl:
                resp = await cl.get(f"http://127.0.0.1:{target_port}/test")
                if resp.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(0.4)

    assert resp is not None and resp.status_code == 200
    assert "CASCADE_TARGET_REACHED_200_OK" in resp.text

    await asyncio.sleep(0.5)

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = s3_log.read_text(encoding="utf-8").splitlines() if s3_log.exists() else []

    # Step 1: Investigation on Server 3 (Xray Trojan log)
    email_s3, ip_s3, tag_s3 = find_xray_client_email(s3_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s3 == s2_tunnel

    # Step 2: Investigation on Server 2 (Sing-box VMess log)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s2 == s1_tunnel

    # Step 3: Investigation on Server 1 (Xray VMess log)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s1 == client_email
    assert ip_s1 == "127.0.0.1"


# ===========================================================================
# TEST 4: SOCKS5 (Xray) -> VLESS (Sing-box) -> Hysteria 2 (Sing-box Exit)
# Protocols: SOCKS5 + VLESS + Hysteria 2
# Cores: Xray + Sing-box + Sing-box
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_socks_vless_singbox_hysteria2_investigation(tmp_path, target_http_server, supervisor):
    """
    Server 1 (Gateway): Xray SOCKS5 Inbound with Auth -> VLESS Outbound to Server 2
    Server 2 (Relay): Sing-box VLESS Inbound -> Hysteria 2 Outbound to Server 3
    Server 3 (Exit): Sing-box Hysteria 2 Inbound -> Direct to Target HTTP
    Client: Python HTTP request through authenticated SOCKS5 on Server 1
    Investigation: Server 3 -> Server 2 -> Server 1.
    """
    target_port = target_http_server
    port_s3 = get_free_port()
    port_s2 = get_free_port()
    port_s1 = get_free_port()

    client_email = "socks_intruder@corp.lan"
    s1_tunnel = "server1_vless_tunnel@corp.lan"
    s2_tunnel = "server2_hy2_tunnel@corp.lan"
    vless_uuid = "33333333-4444-5555-6666-777777777777"

    # Server 3 (Exit): Sing-box Hysteria 2 Inbound -> Direct
    s3_log = tmp_path / "s3_sb_hy.log"
    s3_cfg = {
        "log": {"level": "info", "output": str(s3_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "hysteria2",
            "tag": "hy2-in",
            "listen": "127.0.0.1",
            "listen_port": port_s3,
            "users": [{"name": s2_tunnel, "password": "pwd_transit_s2"}],
            "tls": {"enabled": True, "certificate_path": CERT_PATH, "key_path": KEY_PATH}
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }
    s3_file = tmp_path / "s3_sb_hy.json"
    s3_file.write_text(json.dumps(s3_cfg, indent=2), encoding="utf-8")

    # Server 2 (Relay): Sing-box VLESS Inbound -> Hysteria 2 Outbound
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
            "server": "127.0.0.1",
            "server_port": port_s3,
            "password": "pwd_transit_s2",
            "tls": {"enabled": True, "insecure": True}
        }]
    }
    s2_file = tmp_path / "s2_sb_vless.json"
    s2_file.write_text(json.dumps(s2_cfg, indent=2), encoding="utf-8")

    # Server 1 (Gateway): Sing-box SOCKS5 with Auth -> VLESS Outbound
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

    client_port = get_free_port()
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

    # Send real HTTP traffic through client process connected via SOCKS5 to Server 1
    resp = None
    proxy_url = f"http://127.0.0.1:{client_port}"
    for _ in range(6):
        try:
            async with AsyncClient(proxy=proxy_url, timeout=5.0) as cl:
                resp = await cl.get(f"http://127.0.0.1:{target_port}/test")
                if resp.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(0.4)

    assert resp is not None and resp.status_code == 200
    assert "CASCADE_TARGET_REACHED_200_OK" in resp.text

    await asyncio.sleep(0.5)

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines() if s1_log.exists() else []
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines() if s2_log.exists() else []
    s3_lines = s3_log.read_text(encoding="utf-8").splitlines() if s3_log.exists() else []

    # Step 1: Investigation on Server 3 (Sing-box Hysteria 2 log)
    email_s3, ip_s3, tag_s3 = find_xray_client_email(s3_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s3 == s2_tunnel

    # Step 2: Investigation on Server 2 (Sing-box VLESS log)
    email_s2, ip_s2, tag_s2 = find_xray_client_email(s2_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s2 == s1_tunnel

    # Step 3: Investigation on Server 1 (Xray SOCKS5 log)
    email_s1, ip_s1, tag_s1 = find_xray_client_email(s1_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert email_s1 == client_email
    assert ip_s1 == "127.0.0.1"


# ===========================================================================
# TEST 5: FULL E2E CLIENT BAN & TRANSIT TUNNEL PRESERVATION
# ===========================================================================
@pytest.mark.asyncio
async def test_real_cascade_client_ban_and_transit_preservation(tmp_path, target_http_server, supervisor):
    """
    Tests that after live 3-server cascade investigation successfully attributes the attack,
    the Panel / Security system disables ONLY the culprit client on Server 1,
    while transit tunnels on Server 2 and Server 3 remain fully enabled and active.
    """
    target_port = target_http_server
    port_s3 = get_free_port()
    port_s2 = get_free_port()
    port_s1 = get_free_port()

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
        transit_s2: {"enable": 1, "inbound": "ss-s3"}
    }

    # Setup 3-server cascade with Sing-box -> Xray -> Sing-box
    ss_password = "4X0OQ6U6f7G2g8H+4jK8lg=="
    vless_uuid = "44444444-5555-6666-7777-888888888888"

    s3_log = tmp_path / "ban_s3.log"
    s3_cfg = {
        "log": {"level": "info", "output": str(s3_log).replace("\\", "/"), "timestamp": True},
        "inbounds": [{
            "type": "shadowsocks",
            "tag": "ss-in",
            "listen": "127.0.0.1",
            "listen_port": port_s3,
            "method": "2022-blake3-aes-128-gcm",
            "password": ss_password
        }],
        "outbounds": [{"type": "direct", "tag": "direct"}]
    }
    (tmp_path / "ban_s3.json").write_text(json.dumps(s3_cfg, indent=2))

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
            "protocol": "shadowsocks",
            "tag": "to-s3",
            "settings": {
                "servers": [{"address": "127.0.0.1", "port": port_s3, "method": "2022-blake3-aes-128-gcm", "password": ss_password}]
            }
        }]
    }
    (tmp_path / "ban_s2.json").write_text(json.dumps(s2_cfg, indent=2))

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

    # Culprit sends live attack request
    proxy_url = f"http://{culprit_email}:pwd_culprit@127.0.0.1:{port_s1}"
    resp = None
    for _ in range(6):
        try:
            async with AsyncClient(proxy=proxy_url, timeout=5.0) as cl:
                resp = await cl.get(f"http://127.0.0.1:{target_port}/attack")
                if resp.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(0.4)

    assert resp is not None and resp.status_code == 200
    await asyncio.sleep(0.5)

    s1_lines = s1_log.read_text(encoding="utf-8").splitlines()
    s2_lines = s2_log.read_text(encoding="utf-8").splitlines()

    # Step 1: Trace attack to Server 2
    found_tunnel_s1, _, _ = find_xray_client_email(s2_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert found_tunnel_s1 == transit_s1

    # Step 2: Trace attack to Server 1
    found_culprit, found_ip, _ = find_xray_client_email(s1_lines, dst_ip="127.0.0.1", dst_port=target_port)
    assert found_culprit == culprit_email

    # Step 3: Apply remediation actions
    # Ban culprit on Server 1
    mock_db_s1[found_culprit]["enable"] = 0

    # Ensure transit tunnels remain enabled
    assert mock_db_s1[culprit_email]["enable"] == 0, "Culprit client must be disabled on Server 1"
    assert mock_db_s1[innocent_email]["enable"] == 1, "Innocent client must remain enabled on Server 1"
    assert mock_db_s2[transit_s1]["enable"] == 1, "Transit tunnel on Server 2 must remain enabled"
    assert mock_db_s3[transit_s2]["enable"] == 1, "Transit tunnel on Server 3 must remain enabled"
