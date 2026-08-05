# Facade for telegram alerts operations.
# Exposes variables and functions for backward compatibility.

from backend.alerts.geoip import (
    get_geoip_info,
    get_server_ip
)
from backend.alerts.admin_notifications import (
    async_send_telegram_alert,
    trigger_telegram_alert,
    trigger_investigation_result_alert,
    trigger_investigation_failed_alert
)
from backend.alerts.client_connections import (
    active_activity_cards,
    format_card_msg,
    is_card_active,
    handle_client_event,
    update_panel_active_cards_traffic,
    check_new_ip_and_get_history
)
