import time
import pytest
from backend.database import set_setting, get_setting, db_session
from backend.models import AuditLog


def test_security_unban_ip(client):
    """
    Проверка разблокировки IP через API /api/security/unban-ip.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    set_setting("banned_login_ips", "1.1.1.1,2.2.2.2,3.3.3.3")
    
    response = client.post("/api/security/unban-ip", data={"ip": "2.2.2.2"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Проверяем, что 2.2.2.2 удален из списка
    banned_ips = get_setting("banned_login_ips", "")
    assert "2.2.2.2" not in banned_ips
    assert "1.1.1.1" in banned_ips
    assert "3.3.3.3" in banned_ips


def test_security_banned_ips_list(client):
    """
    Проверка эндпоинта /api/security/banned-ips с поиском причин в аудите.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # Подготавливаем заблокированные IP и логи аудита
    set_setting("banned_login_ips", "1.1.1.1,5.5.5.5")
    
    with db_session() as session:
        session.query(AuditLog).delete()
        log1 = AuditLog(
            timestamp=int(time.time()), 
            username="system", 
            action="login_rate_limited", 
            target="1.1.1.1", 
            details="IP 1.1.1.1 exceeded max login attempts."
        )
        session.add(log1)
        session.commit()
        
    # 1. Запрос без авторизации -> 404 decoy
    response = client.get("/api/security/banned-ips")
    assert response.status_code == 404
    
    # 2. Запрос с авторизацией
    response = client.get("/api/security/banned-ips", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["banned_ips"]) == 2
    
    # Проверяем, что 1.1.1.1 получил причину Bruteforce из аудита
    ip1 = next(item for item in data["banned_ips"] if item["ip"] == "1.1.1.1")
    assert "Bruteforce" in ip1["reason"]
    
    # Проверяем, что 5.5.5.5 получил дефолтную причину (так как лога для него нет)
    ip2 = next(item for item in data["banned_ips"] if item["ip"] == "5.5.5.5")
    assert ip2["reason"] == "2FA-блокировка или настройки"
