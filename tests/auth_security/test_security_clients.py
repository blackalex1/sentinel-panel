import pytest
from backend.database import db_session
from backend.models import Inbound, ClientStats


def test_security_search_client_and_disable(client):
    """
    Проверка эндпоинтов поиска и блокировки клиента (/api/security/search-client, disable-client, enable-client).
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Создаем тестового клиента в БД
    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        
        ib = Inbound(
            remark="Test Inbound for Security API",
            port=20800,
            protocol="vless",
            settings="{}",
            stream_settings="{}",
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.flush()
        
        c = ClientStats(
            inbound_id=ib.id,
            email="threat_user@example.com",
            client_uuid_or_pwd="c56a4180-65aa-42ec-a945-5fd21dec0538",
            up=1000,
            down=2000,
            total=1000000,
            expiry_time=0,
            enable=1,
            limit_ip=1,
            block_reason=""
        )
        session.add(c)
        session.commit()

    # 2. Выполняем поиск клиента по email
    response = client.get("/api/security/search-client?key=threat_user@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["clients"]) == 1
    assert data["clients"][0]["client"]["email"] == "threat_user@example.com"
    assert data["clients"][0]["client"]["enable"] == 1

    # 3. Блокируем клиента через API
    response = client.post("/api/security/disable-client", data={"email": "threat_user@example.com"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # 4. Проверяем, что в БД клиент заблокирован
    with db_session() as session:
        c_db = session.query(ClientStats).filter_by(email="threat_user@example.com").first()
        assert c_db.enable == 0
        assert c_db.block_reason == "IPS Auto-blocked"

    # 5. Проверяем поиск заблокированного клиента
    response = client.get("/api/security/search-client?key=threat_user@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["clients"][0]["client"]["enable"] == 0

    # 6. Разблокируем клиента через API /api/security/enable-client
    response = client.post("/api/security/enable-client", data={"email": "threat_user@example.com"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    # 7. Проверяем, что в БД клиент снова разблокирован
    with db_session() as session:
        c_db = session.query(ClientStats).filter_by(email="threat_user@example.com").first()
        assert c_db.enable == 1
        assert c_db.block_reason is None


def test_security_banned_clients_endpoints(client):
    """
    Проверка эндпоинтов GET /api/security/banned-clients и POST /api/security/unban-client:
    1. Без авторизации -> 404 decoy response.
    2. С авторизацией -> корректное получение списка и разблокировка.
    """
    headers = {"Authorization": "Bearer test_bearer_token"}
    
    # 1. Тест безопасности: Запросы без авторизации должны отдавать decoy response (404)
    res_get_unauth = client.get("/api/security/banned-clients")
    assert res_get_unauth.status_code == 404
    
    res_post_unauth = client.post("/api/security/unban-client", json={"email": "test@test.com"})
    assert res_post_unauth.status_code == 404
    
    # 2. Создаем заблокированного клиента в БД
    with db_session() as session:
        session.query(ClientStats).delete()
        session.query(Inbound).delete()
        
        ib = Inbound(remark="Test-VLESS", port=44332, protocol="vless", enable=1)
        session.add(ib)
        session.commit()
        
        c1 = ClientStats(
            inbound_id=ib.id,
            email="banned_user@example.com",
            client_uuid_or_pwd="uuid-banned-1",
            enable=0,
            block_reason="Multi-login ban test"
        )
        session.add(c1)
        session.commit()
        
    # 3. Запрос с авторизацией: получаем список
    response = client.get("/api/security/banned-clients", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["banned_clients"]) == 1
    bc = data["banned_clients"][0]
    assert bc["email"] == "banned_user@example.com"
    assert bc["reason"] == "Multi-login ban test"
    assert bc["inbound_remark"] == "Test-VLESS"
    
    # 4. Разблокировка клиента через POST /api/security/unban-client
    unban_res = client.post("/api/security/unban-client", json={"email": "banned_user@example.com"}, headers=headers)
    assert unban_res.status_code == 200
    assert unban_res.json()["success"] is True
    
    # 5. Проверяем, что у клиента в БД сброшен флаг enable=1 и block_reason=""
    with db_session() as session:
        updated = session.query(ClientStats).filter_by(email="banned_user@example.com").first()
        assert updated is not None
        assert updated.enable == 1
        assert updated.block_reason == ""
        
    # 6. Список заблокированных теперь пуст
    response_after = client.get("/api/security/banned-clients", headers=headers)
    assert len(response_after.json()["banned_clients"]) == 0
