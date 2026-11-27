from backend.models import Base, Inbound, ClientStats, Outbound

from backend.database.connection import (
    engine,
    session_factory,
    Session,
    db_session,
)
from backend.database.seeding import init_db

from backend.database.crud.auth import (
    hash_password,
    verify_password,
    authenticate_admin,
    update_admin_credentials,
)

from backend.database.crud.inbounds import (
    inbound_to_dict,
    get_all_inbounds,
    get_inbound_by_id,
    add_inbound,
    update_inbound,
    delete_inbound,
    update_inbound_traffic,
)

from backend.database.crud.clients import (
    client_to_dict,
    get_clients_for_inbound,
    get_all_clients_grouped_by_inbound,
    get_client_by_id_or_pwd,
    add_client_db,
    update_client_db,
    delete_client_db,
    update_client_traffic,
    update_client_traffic_by_email,
    reset_client_traffic_db,
    reset_all_client_traffics_for_inbound_db,
    reset_client_traffic_globally_db,
    reset_all_traffics_db,
    sanitize_anomalous_traffic_db,
)

from backend.database.crud.settings import (
    get_setting,
    set_setting,
)

from backend.database.crud.sessions import (
    add_session_db,
    get_session_db,
    get_all_sessions_db,
    delete_session_db,
    clean_expired_sessions_db,
    update_session_ip_db,
)

from backend.database.crud.outbounds import (
    outbound_to_dict,
    get_all_outbounds,
    get_outbound_by_id,
    add_outbound,
    update_outbound,
    delete_outbound,
    update_outbound_traffic,
)

from backend.database.crud.routing import (
    routing_rule_to_dict,
    get_all_routing_rules,
    get_routing_rule_by_id,
    add_routing_rule,
    update_routing_rule,
    delete_routing_rule,
    update_rules_priority,
)

__all__ = [
    "Base",
    "Inbound",
    "ClientStats",
    "Outbound",
    "engine",
    "session_factory",
    "Session",
    "db_session",
    "init_db",
    "hash_password",
    "verify_password",
    "authenticate_admin",
    "update_admin_credentials",
    "inbound_to_dict",
    "get_all_inbounds",
    "get_inbound_by_id",
    "add_inbound",
    "update_inbound",
    "delete_inbound",
    "update_inbound_traffic",
    "client_to_dict",
    "get_clients_for_inbound",
    "get_all_clients_grouped_by_inbound",
    "get_client_by_id_or_pwd",
    "add_client_db",
    "update_client_db",
    "delete_client_db",
    "update_client_traffic",
    "update_client_traffic_by_email",
    "reset_client_traffic_db",
    "reset_all_client_traffics_for_inbound_db",
    "reset_client_traffic_globally_db",
    "reset_all_traffics_db",
    "sanitize_anomalous_traffic_db",
    "get_setting",
    "set_setting",
    "add_session_db",
    "get_session_db",
    "get_all_sessions_db",
    "delete_session_db",
    "clean_expired_sessions_db",
    "update_session_ip_db",
    "outbound_to_dict",
    "get_all_outbounds",
    "get_outbound_by_id",
    "add_outbound",
    "update_outbound",
    "delete_outbound",
    "update_outbound_traffic",
    "routing_rule_to_dict",
    "get_all_routing_rules",
    "get_routing_rule_by_id",
    "add_routing_rule",
    "update_routing_rule",
    "delete_routing_rule",
    "update_rules_priority",
]
