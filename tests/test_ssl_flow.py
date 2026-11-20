import pytest
import socket
import urllib.request
from unittest.mock import patch, MagicMock
from backend.ssl.challenge_server import (
    TemporaryAcmeServer,
    ACME_CHALLENGES,
    AcmeChallengeHandler,
)
from backend.ssl.acme_client import AcmeClient
from backend.ssl.flow import run_acme_flow


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_temporary_acme_server_lifecycle():
    port = get_free_port()
    server = TemporaryAcmeServer(port=port)
    started = server.start()
    assert started is True
    assert server.last_error is None

    token = "test_token_lifecycle"
    key_auth = "test_token_lifecycle.test_thumbprint"
    ACME_CHALLENGES[token] = key_auth

    try:
        # Request valid token
        req_url = f"http://127.0.0.1:{port}/.well-known/acme-challenge/{token}"
        req = urllib.request.Request(req_url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            assert resp.read().decode("utf-8") == key_auth

        # Request with query param
        req_url_param = f"http://127.0.0.1:{port}/.well-known/acme-challenge/{token}?param=1"
        req = urllib.request.Request(req_url_param)
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            assert resp.read().decode("utf-8") == key_auth

        # Request missing token -> 404
        req_404 = f"http://127.0.0.1:{port}/.well-known/acme-challenge/missing"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req_404, timeout=3)
        assert exc_info.value.code == 404
    finally:
        ACME_CHALLENGES.pop(token, None)
        server.stop()


def test_temporary_acme_server_port_collision():
    # Bind a socket first to simulate an occupied port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", 0))
    s.listen(1)
    port = s.getsockname()[1]

    try:
        server = TemporaryAcmeServer(port=port)
        started = server.start()
        assert started is False
        assert server.last_error is not None
    finally:
        s.close()


def test_poll_authorization_extracts_detail():
    client = AcmeClient()

    # Mock response when Let's Encrypt validation fails with connection error
    mock_invalid_resp = {
        "status": "invalid",
        "challenges": [
            {
                "type": "http-01",
                "status": "invalid",
                "error": {
                    "type": "urn:ietf:params:acme:error:connection",
                    "detail": "1.2.3.4: Fetching http://example.com/.well-known/acme-challenge/xyz: Timeout during connect (likely firewall problem)",
                    "status": 400,
                },
            }
        ],
    }

    with patch.object(client, "_sign_and_post", return_value=(200, mock_invalid_resp, {})):
        success, err_detail = client.poll_authorization("https://acme.example/auth/1")
        assert success is False
        assert "Timeout during connect" in err_detail


def test_run_acme_flow_fails_gracefully_on_bind_error():
    # If TemporaryAcmeServer fails to bind, run_acme_flow should exit early with informative error
    with patch("backend.ssl.flow.TemporaryAcmeServer") as MockServer:
        mock_instance = MagicMock()
        mock_instance.start.return_value = False
        mock_instance.last_error = "[Errno 98] Address already in use"
        MockServer.return_value = mock_instance

        success, msg, cert, key = run_acme_flow("example.com", "admin@example.com")
        assert success is False
        assert "Address already in use" in msg
        assert cert is None
        assert key is None
