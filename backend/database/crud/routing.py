import json
from backend.models import RoutingRule
import backend.database

def routing_rule_to_dict(rule: RoutingRule) -> dict:
    if not rule:
        return None
    return {
        "id": rule.id,
        "remark": rule.remark,
        "outbound_tag": rule.outbound_tag,
        "inbound_tags": json.loads(rule.inbound_tags) if rule.inbound_tags else [],
        "users": json.loads(rule.users) if rule.users else [],
        "domains": json.loads(rule.domains) if rule.domains else [],
        "ips": json.loads(rule.ips) if rule.ips else [],
        "protocols": json.loads(rule.protocols) if rule.protocols else [],
        "enable": rule.enable,
        "sort_order": rule.sort_order
    }

def get_all_routing_rules():
    with backend.database.db_session() as session:
        rules = session.query(RoutingRule).order_by(RoutingRule.sort_order.asc()).all()
        return [backend.database.routing_rule_to_dict(r) for r in rules]

def get_routing_rule_by_id(rule_id: int):
    with backend.database.db_session() as session:
        rule = session.query(RoutingRule).filter_by(id=rule_id).first()
        return backend.database.routing_rule_to_dict(rule)

def add_routing_rule(remark: str, outbound_tag: str, inbound_tags: list = None, users: list = None, domains: list = None, ips: list = None, protocols: list = None, enable: int = 1, sort_order: int = 0):
    with backend.database.db_session() as session:
        if sort_order == 0:
            max_order = session.query(RoutingRule.sort_order).order_by(RoutingRule.sort_order.desc()).first()
            sort_order = (max_order[0] + 1) if max_order else 1
            
        rule = RoutingRule(
            remark=remark,
            outbound_tag=outbound_tag,
            inbound_tags=json.dumps(inbound_tags or []),
            users=json.dumps(users or []),
            domains=json.dumps(domains or []),
            ips=json.dumps(ips or []),
            protocols=json.dumps(protocols or []),
            enable=enable,
            sort_order=sort_order
        )
        session.add(rule)
        session.flush()
        return rule.id

def update_routing_rule(rule_id: int, remark: str, outbound_tag: str, inbound_tags: list = None, users: list = None, domains: list = None, ips: list = None, protocols: list = None, enable: int = 1, sort_order: int = None):
    with backend.database.db_session() as session:
        rule = session.query(RoutingRule).filter_by(id=rule_id).first()
        if not rule:
            return False
            
        rule.remark = remark
        rule.outbound_tag = outbound_tag
        rule.inbound_tags = json.dumps(inbound_tags or [])
        rule.users = json.dumps(users or [])
        rule.domains = json.dumps(domains or [])
        rule.ips = json.dumps(ips or [])
        rule.protocols = json.dumps(protocols or [])
        rule.enable = enable
        if sort_order is not None:
            rule.sort_order = sort_order
        return True

def delete_routing_rule(rule_id: int):
    with backend.database.db_session() as session:
        rule = session.query(RoutingRule).filter_by(id=rule_id).first()
        if not rule:
            return False
        session.delete(rule)
        return True

def update_rules_priority(rule_ids_in_order: list):
    with backend.database.db_session() as session:
        for idx, rule_id in enumerate(rule_ids_in_order):
            rule = session.query(RoutingRule).filter_by(id=int(rule_id)).first()
            if rule:
                rule.sort_order = idx + 1
        return True
