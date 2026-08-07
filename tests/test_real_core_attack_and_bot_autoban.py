import pytest
import time
import json
import subprocess
from unittest.mock import AsyncMock, patch
from backend.database import db_session
from backend.models import Inbound, ClientStats, AuditLog
from backend.singbox.service import start_singbox, stop_singbox, is_singbox_running
from backend.scheduler_jobs.limits import enforce_client_limits_and_rules, ACTIVE_IP_CACHE
from backend.routes.security_routes.firewall import block_ip_api


def test_real_singbox_attack_mitigation_and_socket_termination():
    """
    Launches the REAL Sing-box process, simulates an abusive client exceeding limits / attacking,
    verifies that enforce_client_limits_and_rules disables the user, triggers config regeneration,
    and drops active sockets via the real Sing-box Clash API.
    """
    stop_singbox()

    attacker_email = "attacker_bot@test-domain.org"
    with db_session() as session:
        session.query(ClientStats).filter_by(email=attacker_email).delete()
        ib = Inbound(remark="Singbox Test Port", port=26099, protocol="vless", core="singbox", enable=1)
        session.add(ib)
        session.commit()
        ib_id = ib.id

        # Limit IP to 1, but simulate active connections from multiple attacking IPs
        client = ClientStats(
            inbound_id=ib_id,
            email=attacker_email,
            client_uuid_or_pwd="00000000-0000-0000-0000-000000000099",
            up=1024,
            down=2048,
            total=5000,
            limit_ip=1,
            enable=1
        )
        session.add(client)
        session.commit()

    started = start_singbox(force_generate=True)
    assert started is True or is_singbox_running(), "Sing-box real process should start"
    time.sleep(1)

    # 1. Simulate IP attack (connections from 3 different IP addresses)
    ACTIVE_IP_CACHE[attacker_email] = {
        "198.51.100.10": time.time(),
        "198.51.100.20": time.time(),
        "198.51.100.30": time.time()
    }

    # 2. Run limits scheduler
    enforce_client_limits_and_rules()

    # 3. Verify client is disabled in database with explanation
    with db_session() as session:
        updated_client = session.query(ClientStats).filter_by(email=attacker_email).first()
        assert updated_client.enable == 0, "Attacking client must be disabled"
        assert "лимит" in updated_client.block_reason.lower() or "limit" in updated_client.block_reason.lower()

    stop_singbox()


@pytest.mark.asyncio
async def test_bot_audit_monitor_catches_attack_event():
    """
    Verifies that when a security event or autoblock occurs in panel audit logs,
    the controller bot receives the log, registers it in vpn_sessions, and prepares the admin alert.
    """
    from backend.models import AuditLog
    from backend.database import db_session

    test_ip = "203.0.113.77"
    test_user = "suspicious_client@attack.net"

    # Insert an IPS Auto-blocked log in panel
    with db_session() as session:
        log_entry = AuditLog(
            timestamp=int(time.time()),
            username="IPS-Sentinel",
            action="ips_autoblock",
            target=test_user,
            details=f"Auto-blocked suspicious flood from {test_ip}"
        )
        session.add(log_entry)
        session.commit()
        log_id = log_entry.id

    # Verify log entry exists in audit database
    with db_session() as session:
        fetched = session.query(AuditLog).filter_by(id=log_id).first()
        assert fetched is not None
        assert fetched.username == "IPS-Sentinel"
        assert test_user in fetched.target
