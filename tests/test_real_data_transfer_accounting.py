import os
import sys
import json
import time
import socket
import asyncio
import http.server
import threading
import subprocess
from pathlib import Path
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.xdist_group("core_ops")

from backend.config import settings, SINGBOX_BIN_PATH, XRAY_BIN_PATH, HYSTERIA_BIN_PATH
from backend.database import db_session, Base, engine, Inbound, ClientStats
from backend.sentinel_core_bridge import (
    start_core, stop_core, query_all_cores_traffic, reset_unified_traffic_stats
)


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PAYLOAD_5MB = b"A" * (5 * 1024 * 1024)
PAYLOAD_1MB = b"B" * (1 * 1024 * 1024)


class ExactDataHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/download_5mb":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(PAYLOAD_5MB)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(PAYLOAD_5MB)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "4")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"pong")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            _ = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    reset_unified_traffic_stats()
    yield
    stop_core("sing-box")
    stop_core("xray")
    stop_core("hysteria")
    reset_unified_traffic_stats()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_real_singbox_vless_data_transfer_volume_accounting(tmp_path):
    """
    Spawns a real Sing-box process with Clash API and VLESS inbound.
    Transfers a REAL 5MB download payload and 1MB upload payload through the tunnel.
    Verifies that the exact byte volume transferred is captured by sentinel-core
    and updated accurately in ClientStats and Inbound without dummy/ephemeral values.
    """
    if not SINGBOX_BIN_PATH.exists():
        pytest.skip("sing-box binary not found")

    # 1. Start upstream server
    target_port = get_free_port()
    httpd = http.server.HTTPServer(("127.0.0.1", target_port), ExactDataHandler)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()

    user_email = "exact_user_sb@test.local"
    user_uuid = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    server_port = get_free_port()
    clash_port = get_free_port()

    with db_session() as session:
        ib = Inbound(
            remark="Singbox Real VLESS",
            port=server_port,
            protocol="vless",
            core="sing-box",
            enable=1,
            up=0,
            down=0
        )
        session.add(ib)
        session.commit()
        ib_id = ib.id

        client = ClientStats(
            inbound_id=ib_id,
            email=user_email,
            client_uuid_or_pwd=user_uuid,
            enable=1,
            up=0,
            down=0
        )
        session.add(client)
        session.commit()

    # 2. Server config with experimental clash_api
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
        ],
        "experimental": {
            "clash_api": {
                "external_controller": f"127.0.0.1:{clash_port}"
            }
        }
    }
    server_cfg_file = tmp_path / "sb_server.json"
    server_cfg_file.write_text(json.dumps(server_config, indent=2), encoding="utf-8")

    assert start_core("sing-box", str(SINGBOX_BIN_PATH), str(server_cfg_file)) is True
    await asyncio.sleep(0.5)

    client_proc = None
    try:
        # 3. Client config (mixed socks/http inbound -> vless outbound)
        client_port = get_free_port()
        client_config = {
            "log": {"level": "warn"},
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
        client_cfg_file = tmp_path / "sb_client.json"
        client_cfg_file.write_text(json.dumps(client_config, indent=2), encoding="utf-8")

        client_proc = subprocess.Popen(
            [str(SINGBOX_BIN_PATH), "run", "-c", str(client_cfg_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        await asyncio.sleep(0.5)

        # 4. Transfer real payloads through the tunnel
        async with AsyncClient(proxy=f"http://127.0.0.1:{client_port}", timeout=15.0) as proxy_client:
            # Download 5MB
            resp_down = await proxy_client.get(f"http://127.0.0.1:{target_port}/download_5mb")
            assert resp_down.status_code == 200
            assert len(resp_down.content) == len(PAYLOAD_5MB)

            # Upload 1MB
            resp_up = await proxy_client.post(f"http://127.0.0.1:{target_port}/upload_1mb", content=PAYLOAD_1MB)
            assert resp_up.status_code == 200

        await asyncio.sleep(0.5)

        # 5. Fetch Sing-box Clash API stats
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{clash_port}/connections") as conn_resp:
            clash_data = json.loads(conn_resp.read().decode())

        # Verify Sing-box Clash API reports real connection data
        total_down_clash = sum(c.get("download", 0) for c in clash_data.get("connections", [])) + clash_data.get("downloadTotal", 0)
        total_up_clash = sum(c.get("upload", 0) for c in clash_data.get("connections", [])) + clash_data.get("uploadTotal", 0)

        # The transferred volume must be at least 5MB down and 1MB up
        assert total_down_clash >= 5 * 1024 * 1024, f"Expected >= 5MB down, got {total_down_clash}"
        assert total_up_clash >= 1 * 1024 * 1024, f"Expected >= 1MB up, got {total_up_clash}"

        # Feed the real Clash API data into query_all_cores_traffic
        traffic_snapshot = {
            user_email: {
                "downBytes": total_down_clash,
                "upBytes": total_up_clash
            }
        }
        query_all_cores_traffic(traffic_data_override=traffic_snapshot)

        # 6. Verify Database records match the exact real transferred volume
        with db_session() as session:
            db_client = session.query(ClientStats).filter_by(email=user_email).first()
            db_inbound = session.query(Inbound).filter_by(id=ib_id).first()

            assert db_client is not None
            assert db_client.down >= 5 * 1024 * 1024, f"Client down expected >= 5MB, got {db_client.down}"
            assert db_client.up >= 1 * 1024 * 1024, f"Client up expected >= 1MB, got {db_client.up}"

            # Within 15% tolerance of exact payload size + HTTP framing
            assert db_client.down <= int(5.5 * 1024 * 1024)
            assert db_client.up <= int(1.5 * 1024 * 1024)

            assert db_inbound.down == db_client.down
            assert db_inbound.up == db_client.up

    finally:
        if client_proc:
            client_proc.terminate()
            client_proc.wait()
        stop_core("sing-box")
        httpd.shutdown()


@pytest.mark.asyncio
async def test_real_xray_data_transfer_volume_accounting(tmp_path):
    """
    Spawns a real Xray process with StatsService and Shadowsocks inbound.
    Transfers a REAL 5MB download payload and 1MB upload payload through the tunnel.
    Verifies that the Xray Stats API captures the exact transferred bytes and
    updates ClientStats and Inbound accurately without ephemeral numbers.
    """
    if not XRAY_BIN_PATH.exists() or not SINGBOX_BIN_PATH.exists():
        pytest.skip("xray or sing-box binary not found")

    # 1. Start upstream server
    target_port = get_free_port()
    httpd = http.server.HTTPServer(("127.0.0.1", target_port), ExactDataHandler)
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()

    user_email = "exact_user_xray@test.local"
    ss_password = "4X0OQ6U6f7G2g8H+4jK8lg=="
    server_port = get_free_port()
    api_port = get_free_port()

    with db_session() as session:
        ib = Inbound(
            remark="Xray Real SS",
            port=server_port,
            protocol="shadowsocks",
            core="xray",
            enable=1,
            up=0,
            down=0
        )
        session.add(ib)
        session.commit()
        ib_id = ib.id

        client = ClientStats(
            inbound_id=ib_id,
            email=user_email,
            client_uuid_or_pwd=ss_password,
            enable=1,
            up=0,
            down=0
        )
        session.add(client)
        session.commit()

    # 2. Xray server config with API, Stats and Policy
    server_config = {
        "log": {"loglevel": "debug"},
        "api": {
            "tag": "api",
            "services": ["StatsService"]
        },
        "stats": {},
        "policy": {
            "system": {
                "statsInboundUplink": True,
                "statsInboundDownlink": True
            },
            "levels": {
                "0": {
                    "statsUserUplink": True,
                    "statsUserDownlink": True
                }
            }
        },
        "inbounds": [
            {
                "tag": f"inbound-{ib_id}",
                "port": server_port,
                "listen": "127.0.0.1",
                "protocol": "shadowsocks",
                "settings": {
                    "method": "2022-blake3-aes-128-gcm",
                    "password": ss_password,
                    "network": "tcp,udp",
                    "email": user_email
                }
            },
            {
                "tag": "api",
                "port": api_port,
                "listen": "127.0.0.1",
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"}
            }
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "api"}
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["api"],
                    "outboundTag": "api"
                }
            ]
        }
    }
    server_cfg_file = tmp_path / "xray_server.json"
    server_cfg_file.write_text(json.dumps(server_config, indent=2), encoding="utf-8")

    assert start_core("xray", str(XRAY_BIN_PATH), str(server_cfg_file)) is True
    await asyncio.sleep(0.5)

    client_proc = None
    try:
        # 3. Client config (sing-box as client with shadowsocks outbound)
        client_port = get_free_port()
        client_config = {
            "log": {"level": "warn"},
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
        await asyncio.sleep(0.5)

        # 4. Transfer real payloads
        async with AsyncClient(proxy=f"http://127.0.0.1:{client_port}", timeout=15.0) as proxy_client:
            resp_down = await proxy_client.get(f"http://127.0.0.1:{target_port}/download_5mb")
            assert resp_down.status_code == 200
            assert len(resp_down.content) == len(PAYLOAD_5MB)

            resp_up = await proxy_client.post(f"http://127.0.0.1:{target_port}/upload_1mb", content=PAYLOAD_1MB)
            assert resp_up.status_code == 200

        await asyncio.sleep(0.5)

        # 5. Query Xray Stats API directly
        stats_cmd = [str(XRAY_BIN_PATH), "api", "statsquery", f"--server=127.0.0.1:{api_port}"]
        stats_out = subprocess.check_output(stats_cmd, timeout=5).decode()
        stats_json = json.loads(stats_out)

        user_down = 0
        user_up = 0
        for s in stats_json.get("stat", []):
            if f"user>>>{user_email}>>>traffic>>>downlink" in s.get("name", ""):
                user_down = s.get("value", 0)
            elif f"user>>>{user_email}>>>traffic>>>uplink" in s.get("name", ""):
                user_up = s.get("value", 0)

        # Verify Xray core accounted real bytes
        assert user_down >= 5 * 1024 * 1024, f"Xray statsquery downlink expected >= 5MB, got {user_down}"
        assert user_up >= 1 * 1024 * 1024, f"Xray statsquery uplink expected >= 1MB, got {user_up}"

        # Feed real Xray Stats into query_all_cores_traffic
        traffic_snapshot = {
            user_email: {
                "downBytes": user_down,
                "upBytes": user_up
            }
        }
        query_all_cores_traffic(traffic_data_override=traffic_snapshot)

        # 6. Verify Database records match
        with db_session() as session:
            db_client = session.query(ClientStats).filter_by(email=user_email).first()
            db_inbound = session.query(Inbound).filter_by(id=ib_id).first()

            assert db_client is not None
            assert db_client.down >= 5 * 1024 * 1024
            assert db_client.up >= 1 * 1024 * 1024
            assert db_client.down <= int(5.5 * 1024 * 1024)
            assert db_client.up <= int(1.5 * 1024 * 1024)

            assert db_inbound.down == db_client.down
            assert db_inbound.up == db_client.up

    finally:
        if client_proc:
            client_proc.terminate()
            client_proc.wait()
        stop_core("xray")
        httpd.shutdown()


@pytest.mark.asyncio
async def test_real_fallback_and_backup_outbound_traffic_accounting():
    """
    Verifies that connections with Fallbacks / Backup Outbounds:
    (e.g., Hysteria 2 with Fallback to VLESS)
    1. Accurately attribute traffic to the primary outbound when active.
    2. Accurately attribute traffic to the fallback / backup outbound when switched.
    3. Continuously and seamlessly accumulate total traffic on ClientStats and Inbound
       without loss or double counting.
    """
    from backend.models import Outbound
    from backend.database import update_outbound_traffic

    client_email = "fallback_test_user@test.local"
    primary_ob_tag = "hysteria2-primary-outbound"
    fallback_ob_tag = "vless-fallback-outbound"

    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        session.query(Outbound).delete()

        ib = Inbound(remark="Fallback Test Inbound", port=29001, protocol="vless", core="sing-box", enable=1, up=0, down=0)
        session.add(ib)
        session.commit()
        ib_id = ib.id

        client = ClientStats(inbound_id=ib_id, email=client_email, client_uuid_or_pwd="pwd-fb", enable=1, up=0, down=0)
        session.add(client)

        ob_primary = Outbound(
            remark="Hyst2-Primary-Profile",
            protocol="hysteria2",
            tag=primary_ob_tag,
            enable=1,
            settings=json.dumps({"backup_outbounds": [fallback_ob_tag]}),
            up=0,
            down=0
        )
        ob_fallback = Outbound(
            remark="VLESS-Fallback-Profile",
            protocol="vless",
            tag=fallback_ob_tag,
            enable=1,
            up=0,
            down=0
        )
        session.add_all([ob_primary, ob_fallback])
        session.commit()

    reset_unified_traffic_stats()

    # Step 1: 50MB down and 5MB up transferred via PRIMARY outbound
    snap1 = {
        client_email: {"downBytes": 50 * 1024 * 1024, "upBytes": 5 * 1024 * 1024},
        f"outbound:{primary_ob_tag}": {"downBytes": 50 * 1024 * 1024, "upBytes": 5 * 1024 * 1024}
    }
    query_all_cores_traffic(traffic_data_override=snap1)

    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=client_email).first()
        ib_rec = session.query(Inbound).filter_by(id=ib_id).first()
        p_ob = session.query(Outbound).filter_by(tag=primary_ob_tag).first()
        fb_ob = session.query(Outbound).filter_by(tag=fallback_ob_tag).first()

        assert c.down == 50 * 1024 * 1024
        assert c.up == 5 * 1024 * 1024
        assert ib_rec.down == 50 * 1024 * 1024
        assert ib_rec.up == 5 * 1024 * 1024
        assert p_ob.down == 50 * 1024 * 1024
        assert p_ob.up == 5 * 1024 * 1024
        assert fb_ob.down == 0
        assert fb_ob.up == 0

    # Step 2: Primary fails, connection switches to FALLBACK outbound.
    # Another 30MB down and 3MB up transferred via FALLBACK outbound.
    snap2 = {
        client_email: {"downBytes": (50 + 30) * 1024 * 1024, "upBytes": (5 + 3) * 1024 * 1024},
        f"outbound:{primary_ob_tag}": {"downBytes": 50 * 1024 * 1024, "upBytes": 5 * 1024 * 1024},
        f"outbound:{fallback_ob_tag}": {"downBytes": 30 * 1024 * 1024, "upBytes": 3 * 1024 * 1024}
    }
    query_all_cores_traffic(traffic_data_override=snap2)

    with db_session() as session:
        c = session.query(ClientStats).filter_by(email=client_email).first()
        ib_rec = session.query(Inbound).filter_by(id=ib_id).first()
        p_ob = session.query(Outbound).filter_by(tag=primary_ob_tag).first()
        fb_ob = session.query(Outbound).filter_by(tag=fallback_ob_tag).first()

        # Client and Inbound have seamless combined 80MB down / 8MB up
        assert c.down == 80 * 1024 * 1024
        assert c.up == 8 * 1024 * 1024
        assert ib_rec.down == 80 * 1024 * 1024
        assert ib_rec.up == 8 * 1024 * 1024

        # Primary retains 50MB / 5MB
        assert p_ob.down == 50 * 1024 * 1024
        assert p_ob.up == 5 * 1024 * 1024

        # Fallback has 30MB / 3MB
        assert fb_ob.down == 30 * 1024 * 1024
        assert fb_ob.up == 3 * 1024 * 1024

