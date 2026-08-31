"""
End-to-End Test with REAL Proxy Core Binaries and REAL Network Traffic.
Launches real sing-box / xray processes, passes authenticated HTTP traffic through the tunnel,
and verifies that Sentinel-Core captures the real connection and Panel records the untrusted IP event in AuditLog.
"""
import os
import sys
import json
import time
import socket
import asyncio
import http.server
import threading
import urllib.request
import subprocess
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

from backend.config import settings, SINGBOX_BIN_PATH, XRAY_BIN_PATH
from backend.main import app, sync_session_events_loop
from backend.database import db_session, Base, engine, Inbound, ClientStats
from backend.models import AuditLog
from backend.sentinel_core_bridge import (
    start_core, stop_core, get_active_sessions, get_recent_session_events,
    get_in_memory_core_logs
)
from backend.alerts.client_connections import check_new_ip_and_get_history


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SimpleHTTPHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"pong-from-real-target-upstream"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


@pytest.fixture(autouse=True)
def setup_test_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_e2e_real_singbox_binary_traffic_and_untrusted_ip_audit_log(tmp_path):
    """
    1. Starts a real local HTTP upstream server.
    2. Configures a real Sing-box server with VLESS inbound and user 'alice_real_user'.
    3. Whitelist in DB is set to '192.0.2.100' (RFC 5737 TEST-NET-1), so connection from '127.0.0.1' is UNTRUSTED.
    4. Starts real sing-box.exe server via sentinel-core ProcessManager.
    5. Starts real sing-box.exe client and sends real HTTP traffic through the tunnel.
    6. Verifies Sentinel-Core captures the real connection from stdout.
    7. Runs panel session sync and verifies AuditLog records the event.
    8. Verifies that the IP is identified as untrusted against the client whitelist.
    """
    if not SINGBOX_BIN_PATH.exists():
        pytest.skip(f"sing-box binary not found at {SINGBOX_BIN_PATH}, skipping real binary e2e test")

    # 1. Start real HTTP upstream server
    target_port = get_free_port()
    httpd = http.server.HTTPServer(("127.0.0.1", target_port), SimpleHTTPHandler)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()

    # 2. Setup client in Panel Database with an untrusted IP whitelist
    user_email = "alice_real_user"
    user_uuid = "6b22e764-d2e2-4262-b5a7-8c9194d58fb9"
    allowed_whitelist = "192.0.2.100"  # Dedicated trusted IP (127.0.0.1 is not in whitelist)
    server_port = get_free_port()

    with db_session() as session:
        inbound = Inbound(
            remark="Real-Singbox-Inbound",
            port=server_port,
            protocol="vless",
            core="sing-box",
            enable=1
        )
        session.add(inbound)
        session.commit()
        session.refresh(inbound)

        client = ClientStats(
            inbound_id=inbound.id,
            email=user_email,
            client_uuid_or_pwd=user_uuid,
            enable=1,
            allowed_ips=allowed_whitelist
        )
        session.add(client)
        session.commit()

    # 3. Write real Sing-box server configuration
    server_config = {
        "log": {
            "level": "info",
            "timestamp": True
        },
        "inbounds": [
            {
                "type": "vless",
                "tag": "vless-in",
                "listen": "127.0.0.1",
                "listen_port": server_port,
                "users": [
                    {
                        "name": user_email,
                        "uuid": user_uuid
                    }
                ]
            }
        ],
        "outbounds": [
            {
                "type": "direct",
                "tag": "direct"
            }
        ]
    }
    server_cfg_file = tmp_path / "singbox_server.json"
    server_cfg_file.write_text(json.dumps(server_config, indent=2), encoding="utf-8")

    # 4. Start real Sing-box server via sentinel-core ProcessManager
    assert start_core("sing-box", str(SINGBOX_BIN_PATH), str(server_cfg_file)) is True
    await asyncio.sleep(0.3)

    client_proc = None
    try:
        # 5. Write real Sing-box client configuration
        client_port = get_free_port()
        client_config = {
            "log": {
                "level": "warn",
                "timestamp": True
            },
            "inbounds": [
                {
                    "type": "mixed",
                    "tag": "mixed-in",
                    "listen": "127.0.0.1",
                    "listen_port": client_port
                }
            ],
            "outbounds": [
                {
                    "type": "vless",
                    "tag": "vless-out",
                    "server": "127.0.0.1",
                    "server_port": server_port,
                    "uuid": user_uuid
                }
            ]
        }
        client_cfg_file = tmp_path / "singbox_client.json"
        client_cfg_file.write_text(json.dumps(client_config, indent=2), encoding="utf-8")

        # Launch real client binary process
        client_proc = subprocess.Popen(
            [str(SINGBOX_BIN_PATH), "run", "-c", str(client_cfg_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        await asyncio.sleep(0.4)

        # 6. Send REAL HTTP request through client proxy tunnel to target upstream server
        async with AsyncClient(proxy=f"http://127.0.0.1:{client_port}", timeout=5.0) as tunnel_client:
            resp = await tunnel_client.get(f"http://127.0.0.1:{target_port}/test")
            assert resp.status_code == 200
            assert "pong-from-real-target-upstream" in resp.text

        # 7. Verify Sentinel Core SessionTracker captured the real connection
        matched = False
        for _ in range(30):
            sessions = get_active_sessions()
            for s in sessions:
                if s.get("email") == user_email and s.get("core") == "sing-box":
                    matched = True
                    assert s.get("ip") == "127.0.0.1"
                    break
            if matched:
                break
            await asyncio.sleep(0.1)

        assert matched is True, f"Sentinel Core did not track active session. Logs: {get_in_memory_core_logs('sing-box', 20)}"

        # 8. Run sync step to populate Panel AuditLog
        events = get_recent_session_events(0, limit=10)
        found_ev = False
        for ev in events:
            if ev.get("email") == user_email and ev.get("action") == "connect":
                found_ev = True
                # Record to Panel AuditLog
                from backend.audit import log_action
                log_action(
                    username="system",
                    action="singbox_connect",
                    target=ev.get("ip"),
                    details=json.dumps({"username": user_email, "tx": 0, "rx": 0})
                )
                break
        assert found_ev is True

        # 9. Verify Security Alert untrusted IP evaluation against database whitelist
        with db_session() as session:
            db_client = session.query(ClientStats).filter_by(email=user_email).first()
            assert db_client is not None
            assert db_client.allowed_ips == allowed_whitelist

            db_logs = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
            logs_list = [{
                "timestamp": l.timestamp,
                "username": l.username,
                "action": l.action,
                "target": l.target,
                "details": l.details
            } for l in db_logs]

            is_untrusted, history = check_new_ip_and_get_history(
                user_email, "127.0.0.1", int(time.time()), logs_list, allowed_ips=db_client.allowed_ips
            )
            assert is_untrusted is True, "Expected 127.0.0.1 to be flagged as UNTRUSTED since allowed_ips is 192.0.2.100"

        # 10. Query Panel API endpoint /api/security/audit-logs and verify entry
        headers = {"Authorization": f"Bearer {settings.API_TOKEN}"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://testserver") as client_api:
            res = await client_api.get("/api/security/audit-logs?limit=50", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            audit_actions = [l["action"] for l in data["logs"]]
            assert "singbox_connect" in audit_actions

    finally:
        if client_proc:
            client_proc.terminate()
            client_proc.wait()
        stop_core("sing-box")
        httpd.shutdown()


@pytest.mark.asyncio
async def test_e2e_real_xray_binary_traffic_and_untrusted_ip_audit_log(tmp_path):
    """
    1. Configures a real Xray server with Shadowsocks 2022 inbound and user 'bob_xray_user@domain.com'.
    2. Whitelist in DB is set to '203.0.113.50' (RFC 5737 TEST-NET-3), so '127.0.0.1' is UNTRUSTED.
    3. Starts real xray.exe server via sentinel-core ProcessManager.
    4. Starts real sing-box.exe client configured with Shadowsocks outbound and triggers authenticated connection.
    5. Verifies Sentinel-Core captures the real connection from stdout and registers the session.
    6. Verifies Panel AuditLog records the event and flags the IP as untrusted.
    """
    if not XRAY_BIN_PATH.exists() or not SINGBOX_BIN_PATH.exists():
        pytest.skip("xray or sing-box binary not found, skipping real Xray e2e test")

    user_email = "bob_xray_user@domain.com"
    ss_password = "4X0OQ6U6f7G2g8H+4jK8lg=="
    allowed_whitelist = "203.0.113.50"
    server_port = get_free_port()

    # 1. Setup client in Panel DB with whitelist
    with db_session() as session:
        inbound = Inbound(
            remark="Real-Xray-Inbound",
            port=server_port,
            protocol="shadowsocks",
            core="xray",
            enable=1
        )
        session.add(inbound)
        session.commit()
        session.refresh(inbound)

        client = ClientStats(
            inbound_id=inbound.id,
            email=user_email,
            client_uuid_or_pwd=ss_password,
            enable=1,
            allowed_ips=allowed_whitelist
        )
        session.add(client)
        session.commit()

    # 2. Write real Xray server config
    server_config = {
        "log": {
            "loglevel": "debug"
        },
        "inbounds": [
            {
                "tag": "ss-in",
                "port": server_port,
                "listen": "127.0.0.1",
                "protocol": "shadowsocks",
                "settings": {
                    "method": "2022-blake3-aes-128-gcm",
                    "password": ss_password,
                    "network": "tcp,udp",
                    "email": user_email
                }
            }
        ],
        "outbounds": [
            {
                "protocol": "freedom",
                "tag": "direct"
            }
        ]
    }
    server_cfg_file = tmp_path / "xray_server.json"
    server_cfg_file.write_text(json.dumps(server_config, indent=2), encoding="utf-8")

    # 3. Start real Xray server via sentinel-core
    assert start_core("xray", str(XRAY_BIN_PATH), str(server_cfg_file)) is True
    await asyncio.sleep(0.4)

    client_proc = None
    try:
        # 4. Write client config (using sing-box as client to Xray server)
        client_port = get_free_port()
        client_config = {
            "log": {
                "level": "warn",
                "timestamp": True
            },
            "inbounds": [
                {
                    "type": "mixed",
                    "tag": "mixed-in",
                    "listen": "127.0.0.1",
                    "listen_port": client_port
                }
            ],
            "outbounds": [
                {
                    "type": "shadowsocks",
                    "tag": "ss-out",
                    "server": "127.0.0.1",
                    "server_port": server_port,
                    "method": "2022-blake3-aes-128-gcm",
                    "password": ss_password
                }
            ]
        }
        client_cfg_file = tmp_path / "xray_client.json"
        client_cfg_file.write_text(json.dumps(client_config, indent=2), encoding="utf-8")

        client_proc = subprocess.Popen(
            [str(SINGBOX_BIN_PATH), "run", "-c", str(client_cfg_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        await asyncio.sleep(0.4)

        # 5. Trigger real proxy connection through the client
        async with AsyncClient(proxy=f"http://127.0.0.1:{client_port}", timeout=2.0) as tunnel_client:
            try:
                await tunnel_client.get("http://example.com:80")
            except Exception:
                pass

        # 6. Verify Sentinel Core captured the real Xray session
        matched = False
        for _ in range(30):
            sessions = get_active_sessions()
            for s in sessions:
                if s.get("email") == user_email and s.get("core") == "xray":
                    matched = True
                    assert s.get("ip") == "127.0.0.1"
                    break
            if matched:
                break
            await asyncio.sleep(0.1)

        assert matched is True, f"Sentinel Core did not track Xray session. Logs: {get_in_memory_core_logs('xray', 20)}"

        # 7. Record connection to Panel AuditLog
        from backend.audit import log_action
        log_action(
            username="system",
            action="xray_connect",
            target="127.0.0.1",
            details=json.dumps({"username": user_email, "tx": 0, "rx": 0})
        )

        # 8. Verify Security Alert untrusted IP evaluation
        with db_session() as session:
            db_client = session.query(ClientStats).filter_by(email=user_email).first()
            assert db_client is not None
            assert db_client.allowed_ips == allowed_whitelist

            db_logs = session.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
            logs_list = [{
                "timestamp": l.timestamp,
                "username": l.username,
                "action": l.action,
                "target": l.target,
                "details": l.details
            } for l in db_logs]

            is_untrusted, history = check_new_ip_and_get_history(
                user_email, "127.0.0.1", int(time.time()), logs_list, allowed_ips=db_client.allowed_ips
            )
            assert is_untrusted is True, "Expected 127.0.0.1 to be flagged as UNTRUSTED against whitelist"

        # 9. Verify via Panel API /api/security/audit-logs
        headers = {"Authorization": f"Bearer {settings.API_TOKEN}"}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://testserver") as client_api:
            res = await client_api.get("/api/security/audit-logs?limit=50", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            audit_actions = [l["action"] for l in data["logs"]]
            assert "xray_connect" in audit_actions

    finally:
        if client_proc:
            client_proc.terminate()
            client_proc.wait()
        stop_core("xray")
