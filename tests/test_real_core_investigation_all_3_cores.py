import json
import time
import subprocess
import pytest
from pathlib import Path
import backend.routes.security as sec_facade
from backend.routes.security_routes.log_parsers import (
    parse_xray_timestamp,
    parse_hysteria_timestamp,
    find_email_and_ip_in_xray_log,
    find_email_in_hysteria_log,
    find_client_ip_for_email_in_hysteria_log
)
from backend.config import XRAY_BIN_PATH, SINGBOX_BIN_PATH
from backend.hysteria import HYSTERIA_BIN_PATH


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

    # Verify execution of each binary
    res_xray = subprocess.run([str(XRAY_BIN_PATH), "version"], capture_output=True, text=True, timeout=5)
    assert res_xray.returncode == 0 or "Xray" in res_xray.stdout

    res_sb = subprocess.run([str(SINGBOX_BIN_PATH), "version"], capture_output=True, text=True, timeout=5)
    assert res_sb.returncode == 0 or "sing-box" in res_sb.stdout

    res_hy = subprocess.run([str(HYSTERIA_BIN_PATH), "version"], capture_output=True, text=True, timeout=5)
    assert "Hysteria" in res_hy.stdout or "version" in res_hy.stdout.lower() or res_hy.returncode == 0


def test_investigation_on_real_xray_logs(tmp_path):
    """
    Проверяет расследование и атрибуцию нарушителя в логах ядра Xray (VLESS, Trojan, VMess, Shadowsocks).
    """
    now_str = time.strftime("%Y/%m/%d %H:%M:%S")
    logs = [
        f"{now_str} [Info] proxy/vless: accepted tcp:1.2.3.4:41926 [inbound-tag] email: hacker_vless@cyber.org\n",
        f"{now_str} [Info] proxy/trojan: accepted tcp:198.51.100.22:22 [ssh-tag] email: brute_force_trojan@dark.net\n",
        f"{now_str} [Info] proxy/vmess: accepted tcp:203.0.113.88:5432 [pg-tag] email: db_dumper_vmess@leak.com\n",
    ]

    sec_facade.XRAY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(sec_facade.XRAY_LOG_PATH, "w", encoding="utf-8") as f:
        f.writelines(logs)

    # SSH threat investigation
    res_ssh = find_email_and_ip_in_xray_log(client_ip=None, dst_ip="198.51.100.22", dst_port=22)
    assert res_ssh is not None
    email, ip = res_ssh
    assert email == "brute_force_trojan@dark.net"

    # Database port 5432 threat investigation
    res_db = find_email_and_ip_in_xray_log(client_ip=None, dst_ip="203.0.113.88", dst_port=5432)
    assert res_db is not None
    assert res_db[0] == "db_dumper_vmess@leak.com"


def test_investigation_on_real_singbox_logs():
    """
    Проверяет расследование и атрибуцию нарушителя в логах ядра sing-box (SOCKS / VLESS / Shadowsocks).
    """
    now_str = time.strftime("%Y/%m/%d %H:%M:%S")
    logs = [
        f"{now_str} [info] 192.168.1.104:41234 accepted tcp:198.51.100.50:22 [socks-ips >> direct] email: singbox_attacker@exploit.net\n",
        f"{now_str} [info] 192.168.1.104:41235 accepted tcp:203.0.113.77:3389 [vless-in >> direct] email: rdp_spammer@darkweb.org\n"
    ]

    import backend.config as b_cfg
    with open(b_cfg.XRAY_LOG_PATH, "w", encoding="utf-8") as f:
        f.writelines(logs)

    res_ssh = find_email_and_ip_in_xray_log(client_ip="192.168.1.104", dst_ip="198.51.100.50", dst_port=22)
    assert res_ssh is not None
    assert res_ssh[0] == "singbox_attacker@exploit.net"

    res_rdp = find_email_and_ip_in_xray_log(client_ip=None, dst_ip="203.0.113.77", dst_port=3389)
    assert res_rdp is not None
    assert res_rdp[0] == "rdp_spammer@darkweb.org"


def test_investigation_on_real_hysteria_logs():
    """
    Проверяет расследование и атрибуцию нарушителя в логах ядра Hysteria 2:
    - JSON debug формат (id + reqAddr)
    - JSON auth формат (auth + req)
    - Текстовые логи аутентификации
    - Резолв реального IP-адреса клиента
    """
    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    json_logs = [
        json.dumps({
            "time": now_str,
            "level": "debug",
            "msg": "outbound connection",
            "id": "hysteria_scanner@attacker.com",
            "reqAddr": "198.51.100.99:22"
        }) + "\n",
        json.dumps({
            "time": now_str,
            "level": "debug",
            "msg": "outbound connection",
            "auth": "hysteria_db_bot@leak.com",
            "req": "203.0.113.55:5432"
        }) + "\n",
        json.dumps({
            "time": now_str,
            "level": "info",
            "msg": "client connected",
            "id": "hysteria_scanner@attacker.com",
            "addr": "203.0.113.188:51234"
        }) + "\n"
    ]

    sec_facade.HYSTERIA_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(sec_facade.HYSTERIA_LOG_PATH, "w", encoding="utf-8") as f:
        f.writelines(json_logs)

    # Investigate SSH port 22
    found_ssh = find_email_in_hysteria_log(dst_ip="198.51.100.99", dst_port=22)
    assert found_ssh == "hysteria_scanner@attacker.com"

    # Investigate Postgres port 5432
    found_db = find_email_in_hysteria_log(dst_ip="203.0.113.55", dst_port=5432)
    assert found_db == "hysteria_db_bot@leak.com"

    # Resolve client source IP
    resolved_ip = find_client_ip_for_email_in_hysteria_log(email="hysteria_scanner@attacker.com")
    assert resolved_ip == "203.0.113.188"
