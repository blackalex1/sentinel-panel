"""Routing-preset synchronization adapter combining database models and sentinel-core presets."""

import json

from backend.database import db_session
from backend.models import RoutingRule
from backend.sentinel_core_bridge import get_preset_details, get_routing_presets


def get_preset_spec(key: str) -> dict:
    """Dynamically fetches rule spec from sentinel-core presets."""
    preset_id = key.replace("block_", "")
    details = get_preset_details(preset_id)
    if isinstance(details, dict) and "id" in details:
        out_target = "blocked" if details.get("defaultTarget") == "block" else details.get("defaultTarget", "direct")
        return {
            "remark": details.get("name", f"Rule {preset_id}"),
            "outbound_tag": out_target,
            "protocols": details.get("protocols", []),
            "domains": details.get("domains", []),
            "ips": details.get("ips", []),
        }
    return {}


def find_quick_rule(session, key: str):
    spec = get_preset_spec(key)
    if not spec:
        return None
    remark = spec.get("remark", "")
    if remark:
        rule = session.query(RoutingRule).filter(RoutingRule.remark.ilike(f"%{remark}%")).first()
        if rule:
            return rule

    for proto in spec.get("protocols", []):
        rule = session.query(RoutingRule).filter(RoutingRule.protocols.like(f"%{proto}%")).first()
        if rule:
            return rule

    for dom in spec.get("domains", []):
        rule = session.query(RoutingRule).filter(RoutingRule.domains.like(f"%{dom}%")).first()
        if rule:
            return rule

    for ip in spec.get("ips", []):
        rule = session.query(RoutingRule).filter(RoutingRule.ips.like(f"%{ip}%")).first()
        if rule:
            return rule

    return None


def sync_quick_security_rules(settings_dict: dict):
    presets = get_routing_presets()
    with db_session() as session:
        for p in presets:
            pid = p.get("id", "")
            key = "ip_checkers" if pid == "ip_checkers" else f"block_{pid}"
            spec = get_preset_spec(key)
            if not spec:
                continue
            outbound_key = f"{key}_outbound"
            desired_outbound = settings_dict.get(outbound_key)
            if key in settings_dict or outbound_key in settings_dict:
                enabled = 1 if settings_dict.get(key) in (True, "true", 1, "1") else 0
                rule = find_quick_rule(session, key)
                if desired_outbound and str(desired_outbound).strip():
                    out_tag = str(desired_outbound).strip()
                elif outbound_key in settings_dict and rule and rule.outbound_tag:
                    out_tag = rule.outbound_tag
                else:
                    out_tag = spec["outbound_tag"]
                if rule:
                    rule.enable = enabled
                    rule.outbound_tag = out_tag
                    rule.domains = json.dumps(spec["domains"])
                    rule.ips = json.dumps(spec["ips"])
                    rule.protocols = json.dumps(spec["protocols"])
                    if pid == "ipv6" and rule.sort_order > 3:
                        rule.sort_order = 1
                elif enabled:
                    if pid == "ipv6":
                        sort_order = 1
                        for existing_r in session.query(RoutingRule).all():
                            existing_r.sort_order += 1
                    else:
                        max_order = session.query(RoutingRule.sort_order).order_by(RoutingRule.sort_order.desc()).first()
                        sort_order = (max_order[0] + 1) if max_order else 1
                    new_rule = RoutingRule(
                        remark=spec["remark"],
                        outbound_tag=out_tag,
                        inbound_tags="[]",
                        users="[]",
                        domains=json.dumps(spec["domains"]),
                        ips=json.dumps(spec["ips"]),
                        protocols=json.dumps(spec["protocols"]),
                        enable=1,
                        sort_order=sort_order,
                    )
                    session.add(new_rule)
        session.commit()


def get_quick_security_rules_state() -> dict:
    state = {}
    presets = get_routing_presets()
    with db_session() as session:
        for p in presets:
            pid = p.get("id", "")
            key = "ip_checkers" if pid == "ip_checkers" else f"block_{pid}"
            spec = get_preset_spec(key)
            if not spec:
                continue
            rule = find_quick_rule(session, key)
            state[key] = bool(rule and rule.enable == 1)
            state[f"{key}_outbound"] = rule.outbound_tag if rule else spec["outbound_tag"]
    return state
