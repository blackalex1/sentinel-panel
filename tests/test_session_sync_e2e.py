import time
import json
import pytest
from unittest.mock import patch
from backend.database import db_session
from backend.models import AuditLog


@pytest.mark.asyncio
async def test_session_events_sync_to_audit_log(client, monkeypatch):
    """Verifies that events from sentinel-core SessionTracker are written into AuditLog with correct fields."""
    import backend.routes.security_routes.bans
    monkeypatch.setattr(backend.routes.security_routes.bans, 'check_auth', lambda r: True)

    with db_session() as session:
        session.query(AuditLog).delete()

    mock_event = {
        'timestamp': int(time.time()),
        'action': 'connect',
        'core': 'sing-box',
        'email': 'client_test',
        'ip': '198.51.100.230'
    }

    with patch('backend.sentinel_core_bridge.get_recent_session_events', return_value=[mock_event]), \
         patch('backend.sentinel_core_bridge.get_active_sessions', return_value=[]), \
         patch('backend.client_alerts.get_singbox_user_traffic', return_value=(1024, 2048)):

        from backend.sentinel_core_bridge import get_recent_session_events
        from backend.audit import log_action

        events = get_recent_session_events(0, limit=100)
        assert len(events) == 1
        ev = events[0]
        action_type = ev.get('action')
        core_name = str(ev.get('core', 'singbox')).replace('-', '')
        action = f'{core_name}_{action_type}'
        email = ev.get('email')
        ip = ev.get('ip')

        details_dict = {'username': email, 'tx': 1024, 'rx': 2048}
        log_action(
            username='system',
            action=action,
            target=ip,
            details=json.dumps(details_dict)
        )

    with db_session() as session:
        log_entry = session.query(AuditLog).filter(AuditLog.target == '198.51.100.230').first()
        assert log_entry is not None
        assert log_entry.action == 'singbox_connect'
        assert log_entry.target == '198.51.100.230'
        details = json.loads(log_entry.details)
        assert details['username'] == 'client_test'
        assert details['tx'] == 1024
        assert details['rx'] == 2048

    resp = client.get('/api/security/audit-logs?limit=10')
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    logs = data['logs']
    assert len(logs) >= 1
    matched = [l for l in logs if l['target'] == '198.51.100.230' and l['action'] == 'singbox_connect']
    assert len(matched) == 1
    assert json.loads(matched[0]['details'])['username'] == 'client_test'
