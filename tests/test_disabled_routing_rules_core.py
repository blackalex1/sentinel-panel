import json
import pytest
from backend.database import (
    add_routing_rule,
    update_routing_rule,
    get_routing_rule_by_id,
    delete_routing_rule,
    get_all_routing_rules,
)
from backend.sentinel_core_bridge import compile_node_server_config
from backend.sentinel_core_bridge.ffi import _ffi_call_json


def _extract_rules(cfg_result, core_key="routing"):
    if isinstance(cfg_result, dict):
        if "config" in cfg_result:
            inner = cfg_result["config"]
            if isinstance(inner, str) and inner.strip():
                try:
                    inner = json.loads(inner)
                except Exception:
                    pass
            if isinstance(inner, dict):
                return inner.get(core_key, {}).get("rules", [])
        return cfg_result.get(core_key, {}).get("rules", [])
    return []


def test_disabled_rules_omitted_from_xray_config_by_core(client):
    """
    Verifies that routing rules with enable=0 are not compiled into the
    final Xray configuration by the native Go sentinel-core compiler.
    """
    # 1. Add an active rule (enable=1)
    rule_active_id = add_routing_rule(
        remark="Active Test Domain",
        outbound_tag="direct",
        domains=["domain:active-test-domain.org"],
        enable=1,
    )
    assert rule_active_id is not None

    # 2. Add disabled rules (enable=0)
    rule_disabled_udp_id = add_routing_rule(
        remark="Disabled UDP Block",
        outbound_tag="blocked",
        protocols=["udp"],
        enable=0,
    )
    assert rule_disabled_udp_id is not None

    rule_disabled_domain_id = add_routing_rule(
        remark="Disabled Domain Block",
        outbound_tag="blocked",
        domains=["domain:disabled-test-domain.org"],
        enable=0,
    )
    assert rule_disabled_domain_id is not None

    try:
        # 3. Compile server config via native Go sentinel-core
        result = compile_node_server_config("xray")
        rules = _extract_rules(result, "routing")
        assert len(rules) > 0

        # 4. Assert: active rule is compiled
        found_active = False
        found_disabled_udp = False
        found_disabled_domain = False

        for r in rules:
            # Check domain matchers
            if "domain" in r:
                for d in r["domain"]:
                    if "active-test-domain.org" in d:
                        found_active = True
                    if "disabled-test-domain.org" in d:
                        found_disabled_domain = True

            # Check UDP protocol matchers
            if r.get("network") == "udp" and r.get("outboundTag") in ("blocked", "block"):
                # Port 53 dns is allowed, but global UDP block is the one being tested
                if "port" not in r:
                    found_disabled_udp = True

        assert found_active is True, "Active rule (active-test-domain.org) must be compiled into Xray config"
        assert found_disabled_udp is False, "Disabled rule (protocols: ['udp']) must NOT be compiled into Xray config"
        assert found_disabled_domain is False, "Disabled rule (disabled-test-domain.org) must NOT be compiled into Xray config"

    finally:
        delete_routing_rule(rule_active_id)
        delete_routing_rule(rule_disabled_udp_id)
        delete_routing_rule(rule_disabled_domain_id)


def test_disabled_rules_omitted_from_singbox_config_by_core(client):
    """
    Verifies that routing rules with enable=0 are not compiled into the
    final Sing-box configuration by the native Go sentinel-core compiler.
    """
    rule_active_id = add_routing_rule(
        remark="Active SB Domain",
        outbound_tag="direct",
        domains=["domain:sb-active.org"],
        enable=1,
    )
    rule_disabled_id = add_routing_rule(
        remark="Disabled SB UDP Block",
        outbound_tag="blocked",
        protocols=["udp"],
        enable=0,
    )

    try:
        result = compile_node_server_config("singbox")
        rules = _extract_rules(result, "route")

        found_active = False
        found_disabled_udp = False

        for r in rules:
            if "sb-active.org" in str(r):
                found_active = True
            if r.get("network") == "udp" and r.get("outbound") in ("block", "blocked"):
                if "port" not in r:
                    found_disabled_udp = True

        assert found_active is True, "Active domain rule must be in Sing-box config"
        assert found_disabled_udp is False, "Disabled UDP block rule must NOT be in Sing-box config"

    finally:
        delete_routing_rule(rule_active_id)
        delete_routing_rule(rule_disabled_id)


def _extract_rules(cfg_result, core_key="routing"):
    if isinstance(cfg_result, dict):
        if "config" in cfg_result:
            inner = cfg_result["config"]
            if isinstance(inner, str) and inner.strip():
                try:
                    inner = json.loads(inner)
                except Exception:
                    pass
            if isinstance(inner, dict):
                return inner.get(core_key, {}).get("rules", [])
        return cfg_result.get(core_key, {}).get("rules", [])
    return []


def test_rule_toggle_lifecycle_in_core_config(client):
    """
    Tests the full lifecycle of creating a rule, verifying it in the compiled config,
    toggling it to disabled (enable=0) via API, verifying it disappears from core config,
    and toggling it back to active (enable=1).
    """
    headers = {"Authorization": "Bearer test_bearer_token"}

    # 1. Create rule enabled=1
    rule_id = add_routing_rule(
        remark="Lifecycle Test Rule",
        outbound_tag="direct",
        domains=["domain:lifecycle-test.org"],
        enable=1,
    )

    try:
        # Check that it compiles initially
        cfg1 = compile_node_server_config("xray")
        rules1 = _extract_rules(cfg1, "routing")
        assert any("lifecycle-test.org" in str(r) for r in rules1), "Rule must be present when enabled=1"

        # 2. Toggle to disabled (enable=0) via API
        update_payload = {
            "remark": "Lifecycle Test Rule",
            "outbound_tag": "direct",
            "domains": ["domain:lifecycle-test.org"],
            "ips": [],
            "protocols": [],
            "inbound_tags": [],
            "users": [],
            "enable": 0,
        }
        res = client.post(f"/api/routing/rules/update/{rule_id}", json=update_payload, headers=headers)
        assert res.status_code == 200
        assert res.json().get("success") is True

        # Check that Go core omits it
        cfg2 = compile_node_server_config("xray")
        rules2 = _extract_rules(cfg2, "routing")
        assert not any("lifecycle-test.org" in str(r) for r in rules2), "Rule must be ABSENT from core config when enable=0"

        # 3. Toggle back to active (enable=1) via API
        update_payload["enable"] = 1
        res = client.post(f"/api/routing/rules/update/{rule_id}", json=update_payload, headers=headers)
        assert res.status_code == 200
        assert res.json().get("success") is True

        # Check that Go core includes it again
        cfg3 = compile_node_server_config("xray")
        rules3 = _extract_rules(cfg3, "routing")
        assert any("lifecycle-test.org" in str(r) for r in rules3), "Rule must be PRESENT in core config when re-enabled"

    finally:
        delete_routing_rule(rule_id)


def test_direct_ffi_call_respects_enable_flag():
    """
    Directly invokes SentinelBuildServerConfig via C-FFI to verify that the
    native Go core independently and correctly filters rules by 'enable' and 'enabled' fields.
    """
    spec = {
        "targetCore": "xray",
        "serverInbounds": [
            {
                "listen": "0.0.0.0",
                "port": 443,
                "protocol": "vless",
                "tag": "vless-in",
                "clients": [{"id": "00000000-0000-0000-0000-000000000001", "email": "test@test.com"}]
            }
        ],
        "routing": {
            "rules": [
                {
                    "outboundTag": "blocked",
                    "protocols": ["udp"],
                    "enable": False,
                },
                {
                    "outboundTag": "blocked",
                    "domains": ["disabled-by-enabled-tag.com"],
                    "enabled": False,
                },
                {
                    "outboundTag": "direct",
                    "domains": ["strictly-active.com"],
                    "enable": True,
                },
            ]
        }
    }

    res = _ffi_call_json("SentinelBuildServerConfig", json.dumps(spec))
    assert isinstance(res, dict)
    assert "error" not in res, f"FFI error: {res.get('error')}"
    assert "config" in res

    cfg = json.loads(res["config"])
    rules = cfg.get("routing", {}).get("rules", [])

    # The active rule must be present
    has_active = any("strictly-active.com" in str(r) for r in rules)
    assert has_active, "Active rule 'strictly-active.com' must be compiled"

    # Both disabled rules must be absent
    for r in rules:
        if r.get("network") == "udp" and r.get("outboundTag") in ("blocked", "block") and "port" not in r:
            pytest.fail("Go core failed to skip disabled rule: " + str(r))
        if "disabled-by-enabled-tag.com" in str(r):
            pytest.fail("Go core failed to skip disabled rule: " + str(r))
