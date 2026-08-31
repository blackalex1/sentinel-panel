import json
import time
import pytest
from pathlib import Path
from backend.sentinel_core_bridge import (
    find_xray_client_email,
    find_hysteria_client_email,
    find_client_ip_for_email_in_hysteria_log,
    get_core_version
)
from backend.config import XRAY_BIN_PATH, SINGBOX_BIN_PATH
from backend.hysteria import HYSTERIA_BIN_PATH


@pytest.mark.xdist_group("core_ops")
def test_remote_server_all_3_real_core_binaries_present():
    """
    Проверяет установку и исполняемость всех 3 нативных Linux-бинарников на сервере:
    1. Xray Core
    2. sing-box Core
    3. Hysteria 2 Core
    """
    assert XRAY_BIN_PATH.exists(), f"Xray binary missing at {XRAY_BIN_PATH}"
    assert SINGBOX_BIN_PATH.exists(), f"sing-box binary missing at {SINGBOX_BIN_PATH}"
    assert HYSTERIA_BIN_PATH.exists(), f"Hysteria binary missing at {HYSTERIA_BIN_PATH}"

    # Verify execution of each binary via sentinel-core
    v_xray = get_core_version("xray", str(XRAY_BIN_PATH))
    assert v_xray != "Not Installed" and v_xray != "", f"Xray version check failed: {v_xray}"

    v_sb = get_core_version("sing-box", str(SINGBOX_BIN_PATH))
    assert v_sb != "Not Installed" and v_sb != "", f"sing-box version check failed: {v_sb}"

    v_hy = get_core_version("hysteria2", str(HYSTERIA_BIN_PATH))
    assert v_hy != "Not Installed" and v_hy != "", f"Hysteria version check failed: {v_hy}"


def test_investigation_on_real_xray_logs():
    """
    Проверяет расследование и атрибуцию нарушителя в логах ядра Xray (VLESS, Trojan, VMess, Shadowsocks) через Go-ядро.
    """
    now_str = time.strftime("%Y/%m/%d %H:%M:%S")
    logs = [
        f"{now_str} [Info] proxy/vless: accepted tcp:198.51.100.4:41926 [inbound-tag] email: hacker_vless@example.com\n",
        f"{now_str} [Info] proxy/trojan: accepted tcp:198.51.100.22:22 [ssh-tag] email: brute_force_trojan@example.com\n",
        f"{now_str} [Info] proxy/vmess: accepted tcp:203.0.113.88:5432 [pg-tag] email: db_dumper_vmess@example.com\n",
    ]

    # SSH threat investigation via Go sentinel-core
    email, ip, tag = find_xray_client_email(logs, dst_ip="198.51.100.22", dst_port=22)
    assert email == "brute_force_trojan@example.com"

    # Database port 5432 threat investigation via Go sentinel-core
    email_db, _, _ = find_xray_client_email(logs, dst_ip="203.0.113.88", dst_port=5432)
    assert email_db == "db_dumper_vmess@example.com"


def test_investigation_on_real_singbox_logs():
    """
    Проверяет расследование и атрибуцию нарушителя в логах ядра sing-box (SOCKS / VLESS / Shadowsocks) через Go-ядро.
    """
    now_str = time.strftime("%Y/%m/%d %H:%M:%S")
    logs = [
        f"{now_str} [info] 192.168.1.104:41234 accepted tcp:198.51.100.50:22 [socks-ips >> direct] email: singbox_attacker@example.com\n",
        f"{now_str} [info] 192.168.1.104:41235 accepted tcp:203.0.113.77:3389 [vless-in >> direct] email: rdp_spammer@example.com\n"
    ]

    email_ssh, _, _ = find_xray_client_email(logs, client_ip="192.168.1.104", dst_ip="198.51.100.50", dst_port=22)
    assert email_ssh == "singbox_attacker@example.com"

    email_rdp, _, _ = find_xray_client_email(logs, dst_ip="203.0.113.77", dst_port=3389)
    assert email_rdp == "rdp_spammer@example.com"


def test_investigation_on_real_hysteria_logs():
    """
    Проверяет расследование и атрибуцию нарушителя в логах ядра Hysteria 2 через Go-ядро.
    """
    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    json_logs = [
        json.dumps({
            "time": now_str,
            "level": "debug",
            "msg": "outbound connection",
            "id": "hysteria_scanner@example.com",
            "reqAddr": "198.51.100.99:22"
        }) + "\n",
        json.dumps({
            "time": now_str,
            "level": "debug",
            "msg": "outbound connection",
            "auth": "hysteria_db_bot@example.com",
            "req": "203.0.113.55:5432"
        }) + "\n",
        json.dumps({
            "time": now_str,
            "level": "info",
            "msg": "client connected",
            "id": "hysteria_scanner@example.com",
            "addr": "198.51.100.88:51234"
        }) + "\n"
    ]

    # Investigate SSH port 22
    found_ssh = find_hysteria_client_email(json_logs, dst_ip="198.51.100.99", dst_port=22)
    assert found_ssh == "hysteria_scanner@example.com"

    # Investigate Postgres port 5432
    found_db = find_hysteria_client_email(json_logs, dst_ip="203.0.113.55", dst_port=5432)
    assert found_db == "hysteria_db_bot@example.com"

    # Resolve client source IP
    resolved_ip = find_client_ip_for_email_in_hysteria_log(json_logs, email="hysteria_scanner@example.com")
    assert resolved_ip == "198.51.100.88"
