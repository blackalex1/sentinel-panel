import pytest
from backend.database import db_session
from backend.models import UserSession
from backend.auth_utils import ACTIVE_SESSIONS, CSRF_TOKENS
from backend.database.crud.sessions import add_session_db


def test_security_sessions_management(client):
    """
    Проверка эндпоинтов управления активными сессиями:
    - GET /api/security/sessions
    - POST /api/security/sessions/terminate
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Очищаем старые сессии в БД
    with db_session() as session:
        session.query(UserSession).delete()
        session.commit()
        
    ACTIVE_SESSIONS.clear()
    CSRF_TOKENS.clear()
    
    # 2. Добавляем две тестовые сессии в БД и кэш
    sid1 = "session_test_token_1"
    sid2 = "session_test_token_2"
    
    add_session_db(sid1, "admin", 1, ip_address="192.168.1.1", user_agent="Mozilla/Windows")
    add_session_db(sid2, "admin", 1, ip_address="10.0.0.1", user_agent="Mozilla/iPhone")
    
    ACTIVE_SESSIONS.add(sid1)
    ACTIVE_SESSIONS.add(sid2)
    CSRF_TOKENS[sid1] = "csrf_token_1"
    CSRF_TOKENS[sid2] = "csrf_token_2"
    
    # 3. Вызываем GET /api/security/sessions (без куки сессии)
    response = client.get("/api/security/sessions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["sessions"]) == 2
    
    # Сверяем IP и User Agent одной из сессий
    s_ips = [s["ip_address"] for s in data["sessions"]]
    assert "192.168.1.1" in s_ips
    assert "10.0.0.1" in s_ips
    
    # 4. Устанавливаем куку сессии sid1, чтобы проверить флаг is_current
    client.cookies.set("session_id", sid1)
    response = client.get("/api/security/sessions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Находим сессию sid1 и проверяем, что is_current == True, а для sid2 == False
    s1_obj = next(s for s in data["sessions"] if s["session_id"] == sid1)
    s2_obj = next(s for s in data["sessions"] if s["session_id"] == sid2)
    assert s1_obj["is_current"] is True
    assert s2_obj["is_current"] is False
    
    # 5. Завершаем сессию sid2 через API
    response = client.post("/api/security/sessions/terminate", json={"session_id": sid2}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Проверяем, что сессия удалилась из БД и из кэша в памяти
    response = client.get("/api/security/sessions", headers=headers)
    assert len(response.json()["sessions"]) == 1
    assert sid2 not in ACTIVE_SESSIONS
    assert sid2 not in CSRF_TOKENS
