import pytest
from starlette.websockets import WebSocketDisconnect
from backend.auth.sessions import ACTIVE_SESSIONS
from backend.database import add_session_db
from backend.log_streamer import push_log_line


def test_ws_logs_unauthorized_rejected(client):
    """
    Проверка, что неавторизованные WebSocket-подключения к логам немедленно отклоняются.
    """
    for core in ("xray", "singbox", "hysteria"):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/api/{core}/logs/ws"):
                pass
        # Connection closed due to unauthorized policy violation
        assert excinfo.value.code in (1008, 4401, 1000)


def test_ws_logs_authorized_streaming(client):
    """
    Проверка, что авторизованный пользователь получает стрим логов через WebSocket.
    """
    sess_id = "test_ws_stream_session_12345"
    add_session_db(sess_id, "admin", 7)
    ACTIVE_SESSIONS.add(sess_id)
    client.cookies.set("session_id", sess_id)

    with client.websocket_connect("/api/xray/logs/ws") as ws:
        # Push live test line
        push_log_line("xray", "TEST_LIVE_STREAM_LINE_123")
        msg = ws.receive_json()
        assert "event" in msg
