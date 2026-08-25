import time
import pytest
from backend.database import db_session
from backend.models import Inbound, ClientStats
from backend.singbox.service import _process_singbox_connection_data
from backend.client_alerts import process_xray_log_line, process_hysteria_log_line, active_xray_sessions
from backend.scheduler_jobs.limits import ACTIVE_IP_CACHE

def test_singbox_exhaustive_all_protocols_online_status():
    """
    Exhaustively tests online status tracking for ALL protocols supported by Sing-box:
    VLESS REALITY, VLESS gRPC, VMess, Trojan, Shadowsocks 2022, Hysteria 2, TUIC v5, WireGuard.
    """
    with db_session() as session:
        ib = Inbound(remark="Singbox Full IB", port=31001, protocol="vless", core="singbox", enable=1)
        session.add(ib)
        session.commit()
        ib_id = ib.id

        protocols = ["vless", "vmess", "trojan", "shadowsocks", "hysteria2", "tuic", "wireguard"]
        for p in protocols:
            c = ClientStats(inbound_id=ib_id, email=f"sb_{p}_user@test.com", client_uuid_or_pwd=f"pwd_{p}", enable=1)
            session.add(c)
        session.commit()

    # 1. Sing-box VLESS (inboundUser metadata)
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-vless-conn",
            "metadata": {"inboundUser": "sb_vless_user@test.com", "sourceIP": "198.51.100.1", "inboundName": f"inbound-{ib_id}"},
            "upload": 100, "download": 200
        }]
    })
    assert "sb_vless_user@test.com" in ACTIVE_IP_CACHE
    assert "198.51.100.1" in ACTIVE_IP_CACHE["sb_vless_user@test.com"]

    # 2. Sing-box VMess (user metadata)
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-vmess-conn",
            "metadata": {"user": "sb_vmess_user@test.com", "sourceIP": "198.51.100.2", "inboundName": f"inbound-{ib_id}"},
            "upload": 100, "download": 200
        }]
    })
    assert "sb_vmess_user@test.com" in ACTIVE_IP_CACHE
    assert "198.51.100.2" in ACTIVE_IP_CACHE["sb_vmess_user@test.com"]

    # 3. Sing-box Trojan (clientUser metadata)
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-trojan-conn",
            "metadata": {"clientUser": "sb_trojan_user@test.com", "sourceIP": "198.51.100.3", "inboundName": f"inbound-{ib_id}"},
            "upload": 100, "download": 200
        }]
    })
    assert "sb_trojan_user@test.com" in ACTIVE_IP_CACHE
    assert "198.51.100.3" in ACTIVE_IP_CACHE["sb_trojan_user@test.com"]

    # 4. Sing-box Shadowsocks (username metadata)
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-ss-conn",
            "metadata": {"username": "sb_shadowsocks_user@test.com", "sourceIP": "198.51.100.4", "inboundName": f"inbound-{ib_id}"},
            "upload": 100, "download": 200
        }]
    })
    assert "sb_shadowsocks_user@test.com" in ACTIVE_IP_CACHE
    assert "198.51.100.4" in ACTIVE_IP_CACHE["sb_shadowsocks_user@test.com"]

    # 5. Sing-box Hysteria 2 (auth_user metadata)
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-hy2-conn",
            "metadata": {"auth_user": "sb_hysteria2_user@test.com", "sourceIP": "198.51.100.5", "inboundName": f"inbound-{ib_id}"},
            "upload": 100, "download": 200
        }]
    })
    assert "sb_hysteria2_user@test.com" in ACTIVE_IP_CACHE
    assert "198.51.100.5" in ACTIVE_IP_CACHE["sb_hysteria2_user@test.com"]

    # 6. Sing-box TUIC v5 (name metadata)
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-tuic-conn",
            "metadata": {"name": "sb_tuic_user@test.com", "sourceIP": "198.51.100.6", "inboundName": f"inbound-{ib_id}"},
            "upload": 100, "download": 200
        }]
    })
    assert "sb_tuic_user@test.com" in ACTIVE_IP_CACHE
    assert "198.51.100.6" in ACTIVE_IP_CACHE["sb_tuic_user@test.com"]

    # 7. Sing-box WireGuard (email metadata)
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-wg-conn",
            "metadata": {"email": "sb_wireguard_user@test.com", "sourceIP": "198.51.100.7", "inboundName": f"inbound-{ib_id}"},
            "upload": 100, "download": 200
        }]
    })
    assert "sb_wireguard_user@test.com" in ACTIVE_IP_CACHE
    assert "198.51.100.7" in ACTIVE_IP_CACHE["sb_wireguard_user@test.com"]


def test_xray_exhaustive_all_protocols_online_status():
    """
    Exhaustively tests online status tracking for ALL protocols supported by Xray:
    VLESS REALITY, VLESS WS/gRPC, VMess, Trojan, Shadowsocks 2022 / AEAD, SOCKS.
    """
    with db_session() as session:
        ib = Inbound(remark="Xray Full IB", port=31002, protocol="vless", core="xray", enable=1)
        session.add(ib)
        session.commit()
        ib_id = ib.id

        protocols = ["vless", "vmess", "trojan", "shadowsocks", "socks"]
        for p in protocols:
            c = ClientStats(inbound_id=ib_id, email=f"xr_{p}_user@test.com", client_uuid_or_pwd=f"pwd_{p}", enable=1)
            session.add(c)
        session.commit()

    # 1. Xray VLESS REALITY
    vless_log = f"2026/08/09 16:55:00 [Info] [101] app/proxyman/inbound: connection from tcp:203.0.113.10:10001 accepted for tcp:google.com:443 [inbound-{ib_id}] email: xr_vless_user@test.com"
    process_xray_log_line(vless_log)
    assert ("xr_vless_user@test.com", "203.0.113.10") in active_xray_sessions

    # 2. Xray VMess WS/gRPC
    vmess_log = f"2026/08/09 16:55:01 [Info] [102] app/proxyman/inbound: connection from tcp:203.0.113.20:10002 accepted for tcp:bing.com:443 [inbound-{ib_id}] email: xr_vmess_user@test.com"
    process_xray_log_line(vmess_log)
    assert ("xr_vmess_user@test.com", "203.0.113.20") in active_xray_sessions

    # 3. Xray Trojan
    trojan_log = f"2026/08/09 16:55:02 [Info] [103] app/proxyman/inbound: connection from tcp:203.0.113.30:10003 accepted for tcp:cloudflare.com:443 [inbound-{ib_id}] email: xr_trojan_user@test.com"
    process_xray_log_line(trojan_log)
    assert ("xr_trojan_user@test.com", "203.0.113.30") in active_xray_sessions

    # 4. Xray Shadowsocks
    ss_log = f"2026/08/09 16:55:03 [Info] [104] app/proxyman/inbound: connection from udp:203.0.113.40:10004 accepted for udp:8.8.8.8:53 [inbound-{ib_id}] email: xr_shadowsocks_user@test.com"
    process_xray_log_line(ss_log)
    assert ("xr_shadowsocks_user@test.com", "203.0.113.40") in active_xray_sessions

    # 5. Xray SOCKS
    socks_log = f"2026/08/09 16:55:04 [Info] [105] app/proxyman/inbound: connection from tcp:203.0.113.50:10005 accepted for tcp:example.com:80 [inbound-{ib_id}] email: xr_socks_user@test.com"
    process_xray_log_line(socks_log)
    assert ("xr_socks_user@test.com", "203.0.113.50") in active_xray_sessions


def test_hysteria_standalone_online_status():
    """
    Tests Hysteria 2 standalone core online status tracking (Salamander / Masquerade).
    """
    with db_session() as session:
        ib = Inbound(remark="Hysteria Full IB", port=31003, protocol="hysteria2", core="hysteria", enable=1)
        session.add(ib)
        session.commit()
        ib_id = ib.id

        c = ClientStats(inbound_id=ib_id, email="hy2_standalone_user@test.com", client_uuid_or_pwd="pwd_hy2", enable=1)
        session.add(c)
        session.commit()

    hy2_log = '2026-08-09T16:55:10.000+0300\tINFO\tclient connected\t{"id": "hy2_standalone_user@test.com", "addr": "192.0.2.100:55555"}'
    process_hysteria_log_line(hy2_log)

    assert "hy2_standalone_user@test.com" in ACTIVE_IP_CACHE
    assert "192.0.2.100" in ACTIVE_IP_CACHE["hy2_standalone_user@test.com"]

    from backend.routes.clients.actions import update_online_emails
    onlines = update_online_emails()
    assert "hy2_standalone_user@test.com" in onlines


def test_hysteria_auth_endpoint_populates_active_ip_cache_for_unlimited_clients():
    """
    Verifies that authenticating via /api/hysteria/auth immediately registers client as online
    in ACTIVE_IP_CACHE even when limit_ip == 0 (unlimited).
    """
    import asyncio
    from backend.routes.hysteria_routes.auth import hysteria_client_auth
    from backend.routes.clients.actions import update_online_emails
    from starlette.requests import Request

    email = "unlimited_hy2_user@test.com"
    with db_session() as session:
        ib = Inbound(remark="Hysteria Unlim IB", port=31004, protocol="hysteria2", core="hysteria", enable=1)
        session.add(ib)
        session.commit()

        c = ClientStats(inbound_id=ib.id, email=email, client_uuid_or_pwd="pwd_unlimited", enable=1, limit_ip=0)
        session.add(c)
        session.commit()

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/hysteria/auth",
        "headers": [],
        "client": ("127.0.0.1", 54321),
    }
    request = Request(scope)
    payload = {
        "auth": f"{email}:pwd_unlimited",
        "addr": "198.51.100.99:43210"
    }

    res = asyncio.run(hysteria_client_auth(request, payload))
    assert res.get("ok") is True
    assert res.get("id") == email
    assert email in ACTIVE_IP_CACHE
    assert "198.51.100.99" in ACTIVE_IP_CACHE[email]

    onlines = update_online_emails()
    assert email in onlines


def test_end_to_end_multiclient_multicore_online_status(tmp_path, monkeypatch):
    """
    Creates multiple clients across Sing-box, Xray, and Hysteria 2,
    simulates real log streams and Clash API connections, and verifies
    that all clients are accurately marked as online in update_online_emails.
    """
    from backend.routes.clients.actions import update_online_emails
    from backend.scheduler_jobs.limits import parse_recent_singbox_ips, ACTIVE_IP_CACHE

    singbox_clients = ["phone", "laptop_singbox", "tablet_singbox"]
    xray_clients = ["user_xray_vless", "user_xray_vmess", "user_xray_trojan"]
    hy2_clients = ["user_hy2_fast", "user_hy2_mobile"]

    with db_session() as session:
        # Inbound 1: Sing-box VLESS
        ib_sb = Inbound(remark="Singbox VLESS", port=32001, protocol="vless", core="singbox", enable=1)
        session.add(ib_sb)
        session.commit()
        for u in singbox_clients:
            session.add(ClientStats(inbound_id=ib_sb.id, email=u, client_uuid_or_pwd=f"pwd_{u}", enable=1))

        # Inbound 2: Xray VMess
        ib_xr = Inbound(remark="Xray VMess", port=32002, protocol="vmess", core="xray", enable=1)
        session.add(ib_xr)
        session.commit()
        for u in xray_clients:
            session.add(ClientStats(inbound_id=ib_xr.id, email=u, client_uuid_or_pwd=f"pwd_{u}", enable=1))

        # Inbound 3: Hysteria 2
        ib_hy = Inbound(remark="Hysteria 2", port=32003, protocol="hysteria2", core="hysteria", enable=1)
        session.add(ib_hy)
        session.commit()
        for u in hy2_clients:
            session.add(ClientStats(inbound_id=ib_hy.id, email=u, client_uuid_or_pwd=f"pwd_{u}", enable=1))
        session.commit()

    import datetime
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    now_local = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    now_iso = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000+0300")

    # 1. Simulate Sing-box log file with timezone offset and bracketed usernames
    sb_log_file = tmp_path / "singbox.log"
    sb_log_content = (
        f"+0000 {now_utc} INFO [1035259714 0ms] inbound/vless[inbound-8]: inbound connection from 192.168.1.50:42944\n"
        f"+0000 {now_utc} INFO [1035259714 40ms] inbound/vless[inbound-8]: [phone] inbound connection to www.google.com:443\n"
        f"+0000 {now_utc} INFO [2287405019 40ms] inbound/vless[inbound-8]: [laptop_singbox] inbound connection to www.youtube.com:443\n"
    )
    sb_log_file.write_text(sb_log_content, encoding="utf-8")
    monkeypatch.setattr("backend.config.SINGBOX_LOG_PATH", sb_log_file)

    # 2. Simulate Sing-box Clash API connection for tablet_singbox
    _process_singbox_connection_data({
        "connections": [{
            "id": "sb-tablet-conn-01",
            "metadata": {"inboundUser": "tablet_singbox", "sourceIP": "192.168.1.77"},
            "upload": 5000, "download": 15000
        }]
    })

    # 3. Simulate Xray connections via log processor
    process_xray_log_line(f"{now_local} [Info] [201] app/proxyman/inbound: connection from tcp:198.51.100.11:10001 accepted for tcp:google.com:443 email: user_xray_vless")
    process_xray_log_line(f"{now_local} [Info] [202] app/proxyman/inbound: connection from tcp:198.51.100.12:10002 accepted for tcp:bing.com:443 email: user_xray_vmess")
    process_xray_log_line(f"{now_local} [Info] [203] app/proxyman/inbound: connection from tcp:198.51.100.13:10003 accepted for tcp:cloudflare.com:443 email: user_xray_trojan")

    # 4. Simulate Hysteria 2 connections via log processor
    process_hysteria_log_line(f'{now_iso}\tINFO\tclient connected\t{{"id": "user_hy2_fast", "addr": "198.51.100.21:55551"}}')
    process_hysteria_log_line(f'{now_iso}\tINFO\tclient connected\t{{"id": "user_hy2_mobile", "addr": "198.51.100.22:55552"}}')

    # Execute update_online_emails
    onlines = update_online_emails()

    # Verify every client on Sing-box is online
    assert "phone" in onlines, f"Expected 'phone' to be online, got: {onlines}"
    assert "laptop_singbox" in onlines, f"Expected 'laptop_singbox' to be online, got: {onlines}"
    assert "tablet_singbox" in onlines, f"Expected 'tablet_singbox' to be online, got: {onlines}"

    # Verify every client on Xray is online
    assert "user_xray_vless" in onlines, f"Expected 'user_xray_vless' to be online, got: {onlines}"
    assert "user_xray_vmess" in onlines, f"Expected 'user_xray_vmess' to be online, got: {onlines}"
    assert "user_xray_trojan" in onlines, f"Expected 'user_xray_trojan' to be online, got: {onlines}"

    # Verify every client on Hysteria 2 is online
    assert "user_hy2_fast" in onlines, f"Expected 'user_hy2_fast' to be online, got: {onlines}"
    assert "user_hy2_mobile" in onlines, f"Expected 'user_hy2_mobile' to be online, got: {onlines}"


