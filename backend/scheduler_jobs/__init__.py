# Facade for scheduler operations.
# Exposes variables and functions for backward compatibility, including dependencies mocked by tests.

from backend.config import XRAY_LOG_PATH, HYSTERIA_LOG_PATH
from backend.cores.xray import remove_client_api, write_xray_config, is_xray_running, restart_xray
from backend.cores.hysteria import kick_client_hysteria_api, restart_hysteria, is_hysteria_running

from backend.infra.runtime import ACTIVE_IP_CACHE
from backend.scheduler_jobs.limits import (
    enforce_client_limits_and_rules as _enforce_client_limits_and_rules,
    parse_recent_xray_ips,
    parse_recent_singbox_ips,
    parse_recent_hysteria_ips,
    asyncio_notify_admin
)


def enforce_client_limits_and_rules():
    """Runs limit enforcement wired with scheduler-level API hooks (for test monkeypatching)."""
    return _enforce_client_limits_and_rules(
        remove_client_fn=remove_client_api,
        kick_hysteria_fn=kick_client_hysteria_api,
        notify_admin_fn=asyncio_notify_admin,
    )
from backend.scheduler_jobs.backups import check_and_run_backups
from backend.scheduler_jobs.maintenance import (
    truncate_logs_if_large,
    run_db_cleanup_maintenance
)
