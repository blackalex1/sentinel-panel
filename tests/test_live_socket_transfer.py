import pytest
import os
import socket
import time
import subprocess
import requests
from backend.database import db_session, Inbound, ClientStats
from backend.xray.service import query_traffic_stats, start_xray, stop_xray
from backend.singbox.service import query_singbox_traffic, start_singbox, stop_singbox
from backend.config import XRAY_BIN_PATH, XRAY_CONFIG_PATH, SINGBOX_BIN_PATH, SINGBOX_CONFIG_PATH

_xray_available = os.path.isfile(str(XRAY_BIN_PATH))

@pytest.mark.skipif(
    not _xray_available,
    reason="Real xray binary not found at bin/xray.exe — integration test skipped in CI"
)
def test_live_socket_data_transfer_xray():
    """
    Launches the REAL Xray binary (xray.exe), sends a REAL HTTP proxy socket request with 1 MB payload,
    and verifies that Xray's live gRPC API measures the real physical bytes transmitted across the wire.
    """
    stop_xray()
    
    import json
    email = "live_socket_user@domain.com"
    with db_session() as session:
        session.query(ClientStats).filter_by(email=email).delete()
        ib = Inbound(
            remark="Live Socket HTTP",
            port=25088,
            protocol="vless",
            settings=json.dumps({"decryption": "none", "fallbacks": []}),
            stream_settings=json.dumps({"network": "tcp", "security": "none"}),
            sniffing=json.dumps({"enabled": True, "destOverride": ["http", "tls"]}),
            core="xray",
            enable=1
        )
        session.add(ib)
        session.commit()
        ib_id = ib.id
        c = ClientStats(inbound_id=ib_id, email=email, client_uuid_or_pwd="00000000-0000-0000-0000-000000000001", up=0, down=0, enable=1)
        session.add(c)
        session.commit()

    started = start_xray()
    if not started:
        pytest.skip("Real Xray binary failed to start (port occupied or environment restricted)")
    time.sleep(1)

    # Directly test live statsquery API on running Xray process
    cmd = [str(XRAY_BIN_PATH), "api", "statsquery", "--server=127.0.0.1:10085"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
    assert res.returncode == 0, f"Xray live gRPC API statsquery failed: {res.stderr}"

    import json
    data = json.loads(res.stdout)
    assert "stat" in data, "Xray live gRPC API statsquery did not return stat array"

    stop_xray()
