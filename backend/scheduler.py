# Facade for scheduler operations.
# Exposes variables and functions for backward compatibility, including dependencies mocked by tests.

from backend.config import XRAY_LOG_PATH, HYSTERIA_LOG_PATH
from backend.xray import remove_client_api, write_xray_config, is_xray_running, restart_xray
from backend.hysteria import kick_client_hysteria_api, restart_hysteria, is_hysteria_running

from backend.scheduler_jobs.limits import (
    ACTIVE_IP_CACHE,
    enforce_client_limits_and_rules,
    parse_recent_xray_ips,
    parse_recent_singbox_ips,
    asyncio_notify_admin
)
from backend.scheduler_jobs.backups import check_and_run_backups
from backend.scheduler_jobs.maintenance import (
    truncate_logs_if_large,
    run_db_cleanup_maintenance
)
