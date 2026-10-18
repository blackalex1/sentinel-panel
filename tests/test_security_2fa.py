import json
import time
import pytest
from backend.database import db_session
from backend.models import SystemSetting


def test_telegram_2fa_auth_endpoints(client):
    """
    Проверка маршрутов опроса и действий Telegram 2FA (/api/auth/tg-2fa/poll, /api/auth/tg-2fa/action).
    """
    token = "test_tg_2fa_token_12345"
    
    # 1. Создаем запрос 2FA в SystemSetting
    with db_session() as session:
        session.query(SystemSetting).filter(SystemSetting.key.like("tg_2fa_req_%")).delete()
        
        req = SystemSetting(
            key=f"tg_2fa_req_{token}",
            value=json.dumps({
                "username": "admin",
                "client_ip": "192.168.1.100",
                "status": "pending",
                "expires": time.time() + 120
            })
        )
        session.add(req)
        session.commit()
        
    # 2. Опрашиваем статус (ожидаем pending)
    response = client.get(f"/api/auth/tg-2fa/poll?token={token}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "pending"
    
    # 2.5. Неавторизованный запрос к action -> 404 decoy
    res_unauth = client.post("/api/auth/tg-2fa/action", json={"token": token, "action": "approve"})
    assert res_unauth.status_code == 404

    # 3. Выполняем подтверждение входа (approve) с авторизацией
    headers = {"Authorization": "Bearer test_bearer_token"}
    response = client.post("/api/auth/tg-2fa/action", json={"token": token, "action": "approve"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # 4. Снова опрашиваем статус (ожидаем approved и установку session_id cookie)
    response = client.get(f"/api/auth/tg-2fa/poll?token={token}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "approved"
    assert "session_id" in response.cookies
    
    # 5. Проверяем блокировку (block) с повторным созданием
    token_block = "test_tg_2fa_token_block"
    with db_session() as session:
        req = SystemSetting(
            key=f"tg_2fa_req_{token_block}",
            value=json.dumps({
                "username": "admin",
                "client_ip": "1.2.3.4",
                "status": "pending",
                "expires": time.time() + 120
            })
        )
        session.add(req)
        session.commit()
        
    response = client.post("/api/auth/tg-2fa/action", json={"token": token_block, "action": "block"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # 6. Опрашиваем статус после блокировки
    response = client.get(f"/api/auth/tg-2fa/poll?token={token_block}")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "blocked"


def test_telegram_2fa_token_format_validation(client):
    """Verifies that invalid or malformed tokens in tg-2fa/poll are rejected."""
    # Special characters
    res = client.get("/api/auth/tg-2fa/poll?token=../../etc/passwd")
    assert res.status_code == 200
    assert res.json() == {"success": False, "status": "expired"}

    # Oversized token (>64 chars)
    res = client.get(f"/api/auth/tg-2fa/poll?token={'a' * 100}")
    assert res.status_code == 200
    assert res.json() == {"success": False, "status": "expired"}

    # Whitespace/SQL injection chars
    res = client.get("/api/auth/tg-2fa/poll?token=token%20with%20spaces")
    assert res.status_code == 200
    assert res.json() == {"success": False, "status": "expired"}


def test_telegram_2fa_action_validation(client):
    """Verifies that invalid actions or malformed tokens in tg-2fa/action are rejected."""
    headers = {"Authorization": "Bearer test_bearer_token"}
    # Invalid action
    res = client.post("/api/auth/tg-2fa/action", json={"token": "valid_token_123", "action": "evil_action"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is False

    # Malformed token
    res = client.post("/api/auth/tg-2fa/action", json={"token": "bad token!#$", "action": "approve"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["success"] is False
