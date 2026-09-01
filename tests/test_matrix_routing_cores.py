import json
import pytest
from backend.xray.config import generate_xray_config_json
from backend.singbox.config import generate_singbox_config_json

pytestmark = pytest.mark.xdist_group("core_ops")

def test_intra_core_xray_routing(monkeypatch):
    """Test Xray intra-core routing: Xray inbound to Xray outbounds with complex routing rules."""
    mock_inbounds = [
        {
            "id": 10,
            "remark": "Xray Inbound VLESS",
            "port": 10010,
            "protocol": "vless",
            "enable": 1,
            "core": "xray",
            "settings": json.dumps({
                "clients": [{"email": "user1@xray.com", "id": "uuid-1", "flow": "xtls-rprx-vision"}]
            }),
            "stream_settings": json.dumps({"security": "none"}),
            "sniffing": json.dumps({"enabled": True, "destOverride": ["http", "tls"]})
        }
    ]

    mock_outbounds = [
        {
            "id": 1,
            "remark": "Direct Freedom",
            "protocol": "freedom",
            "tag": "direct",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 2,
            "remark": "Blackhole Blocked",
            "protocol": "blackhole",
            "tag": "blocked",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 3,
            "remark": "WARP Socks Outbound",
            "protocol": "socks",
            "tag": "warp-out",
            "settings": json.dumps({"servers": [{"address": "127.0.0.1", "port": 40000}]}),
            "stream_settings": "{}",
            "enable": 1
        }
    ]

    mock_rules = [
        {
            "id": 101,
            "remark": "Route WARP Traffic",
            "outbound_tag": "warp-out",
            "inbound_tags": ["inbound-10"],
            "users": ["user1@xray.com"],
            "domains": ["geosite:openai", "domain:chatgpt.com", "regexp:.*\\.openai\\.com"],
            "ips": ["geoip:us", "1.1.1.1/32"],
            "protocols": ["tcp", "bittorrent"],
            "enable": 1
        }
    ]

    monkeypatch.setattr("backend.xray.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.xray.config.get_clients_for_inbound", lambda ib_id: [
        {"email": "user1@xray.com", "client_uuid_or_pwd": "uuid-1", "enable": True}
    ])
    monkeypatch.setattr("backend.xray.config.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.xray.config.get_all_routing_rules", lambda: mock_rules)
    monkeypatch.setattr("backend.xray.config.get_setting", lambda key: "false")

    config = generate_xray_config_json()
    from tests.core_verifier import validate_xray_config
    valid, msg = validate_xray_config(config)
    assert valid is True, f"Real Xray binary validation failed: {msg}"

    # 1. Inbound check
    xray_inbound = next((ib for ib in config["inbounds"] if ib.get("tag") == "inbound-10"), None)
    assert xray_inbound is not None
    assert xray_inbound["port"] == 10010
    assert xray_inbound["protocol"] == "vless"

    # 2. Outbound check (direct must be sorted first)
    assert config["outbounds"][0]["tag"] == "direct"
    warp_ob = next((ob for ob in config["outbounds"] if ob.get("tag") == "warp-out"), None)
    assert warp_ob is not None
    assert warp_ob["protocol"] == "socks"

    # 3. Routing rules check
    rules = config["routing"]["rules"]
    domain_rule = next((r for r in rules if r.get("outboundTag") == "warp-out" and "domain" in r), None)
    assert domain_rule is not None
    assert domain_rule["inboundTag"] == ["inbound-10"]
    assert domain_rule["user"] == ["user1@xray.com"]
    assert "geosite:openai" in domain_rule["domain"]
    assert "domain:chatgpt.com" in domain_rule["domain"]
    assert "regexp:.*\\.openai\\.com" in domain_rule["domain"]

    ip_rule = next((r for r in rules if r.get("outboundTag") == "warp-out" and "ip" in r), None)
    assert ip_rule is not None
    assert "geoip:us" in ip_rule["ip"]
    assert "1.1.1.1/32" in ip_rule["ip"]


def test_intra_core_singbox_routing(monkeypatch):
    """Test Sing-box intra-core routing: Sing-box inbound to Sing-box outbounds (including native Hysteria2)."""
    mock_inbounds = [
        {
            "id": 20,
            "remark": "Singbox Inbound VLESS",
            "port": 10020,
            "protocol": "vless",
            "enable": 1,
            "core": "singbox",
            "settings": json.dumps({}),
            "stream_settings": json.dumps({"security": "reality", "realitySettings": {"serverNames": ["example.com"], "dest": "example.com:443", "privateKey": "MNVw1viyA8FrjtWe-lKw8WTaCitibL4Qt07R91gn4H0", "shortIds": ["12"]}}),
            "sniffing": "{}"
        }
    ]

    mock_outbounds = [
        {
            "id": 1,
            "remark": "Direct",
            "protocol": "freedom",
            "tag": "direct",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 2,
            "remark": "Singbox Hysteria 2 Out",
            "protocol": "hysteria2",
            "tag": "sb-hysteria2-out",
            "settings": json.dumps({
                "address": "2.3.4.5",
                "port": 8443,
                "password": "pass123",
                "obfs_type": "salamander",
                "obfs_password": "obfspassword"
            }),
            "stream_settings": json.dumps({"security": "tls", "tlsSettings": {"serverName": "hysteria.domain.com"}}),
            "enable": 1
        }
    ]

    mock_rules = [
        {
            "id": 201,
            "remark": "Route Rule for Singbox",
            "outbound_tag": "sb-hysteria2-out",
            "inbound_tags": ["inbound-20"],
            "users": ["user2@singbox.com"],
            "domains": ["geosite:google", "domain:google.com", "full:exact.google.com", "regexp:.*\\.google", "keyword:goog"],
            "ips": ["geoip:ru", "8.8.8.8/32"],
            "protocols": ["udp"],
            "enable": 1
        }
    ]

    monkeypatch.setattr("backend.singbox.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.singbox.config.get_clients_for_inbound", lambda ib_id: [
        {"email": "user2@singbox.com", "client_uuid_or_pwd": "uuid-2", "enable": True}
    ])
    monkeypatch.setattr("backend.database.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.database.get_all_routing_rules", lambda: mock_rules)
    monkeypatch.setattr("backend.singbox.config.get_setting", lambda key: "false")

    config = generate_singbox_config_json()
    from tests.core_verifier import validate_singbox_config
    valid, msg = validate_singbox_config(config)
    assert valid is True, f"Real sing-box binary validation failed: {msg}"

    # 1. Inbound check
    sb_inbound = next((ib for ib in config["inbounds"] if ib.get("tag") == "inbound-20"), None)
    assert sb_inbound is not None
    assert sb_inbound["listen_port"] == 10020
    assert sb_inbound["tls"]["enabled"] is True
    assert sb_inbound["tls"]["reality"]["enabled"] is True

    # 2. Hysteria2 Outbound check
    sb_ob = next((ob for ob in config["outbounds"] if ob.get("tag") == "sb-hysteria2-out"), None)
    assert sb_ob is not None
    assert sb_ob["type"] == "hysteria2"
    assert sb_ob["server"] == "2.3.4.5"
    assert sb_ob["server_port"] == 8443
    assert sb_ob["password"] == "pass123"
    assert sb_ob["tls"]["server_name"] == "hysteria.domain.com"
    assert sb_ob["obfs"]["type"] == "salamander"

    # 3. Routing rule check
    d_rule = next((r for r in config["route"]["rules"] if r.get("outbound") == "sb-hysteria2-out" and "geosite-google" in r.get("rule_set", [])), None)
    assert d_rule is not None
    assert d_rule["inbound"] == ["inbound-20"]
    assert d_rule["user"] == ["user2@singbox.com"]
    assert "google.com" in d_rule["domain"]
    assert "exact.google.com" in d_rule["domain"]
    assert ".*\\.google" in d_rule["domain_regex"]
    assert "goog" in d_rule["domain_keyword"]

    i_rule = next((r for r in config["route"]["rules"] if r.get("outbound") == "sb-hysteria2-out" and "geoip-ru" in r.get("rule_set", [])), None)
    assert i_rule is not None
    assert "8.8.8.8/32" in i_rule["ip_cidr"]
    assert i_rule["network"] == ["udp"]



def test_cross_core_hysteria2_socks_bridge_to_xray(monkeypatch):
    """Test Hysteria 2 inbound routing via Xray SOCKS bridge (routingViaXray=True)."""
    mock_inbounds = [
        {
            "id": 5,
            "remark": "Hysteria 2 Inbound",
            "port": 443,
            "protocol": "hysteria2",
            "enable": 1,
            "core": "hysteria",
            "settings": "{}",
            "stream_settings": json.dumps({"hysteria": {"routingViaXray": True, "socksUsername": "user_h2", "socksPassword": "pass_h2"}}),
            "sniffing": "{}"
        }
    ]

    mock_outbounds = [
        {
            "id": 1,
            "remark": "Direct",
            "protocol": "freedom",
            "tag": "direct",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 2,
            "remark": "Hysteria Outbound in Xray",
            "protocol": "hysteria",
            "tag": "hysteria-out-xray",
            "settings": json.dumps({"address": "3.4.5.6", "port": 443}),
            "stream_settings": "{}",
            "enable": 1
        }
    ]

    mock_rules = [
        {
            "id": 501,
            "remark": "Route Hysteria SOCKS traffic",
            "outbound_tag": "hysteria-out-xray",
            "inbound_tags": ["inbound-5-socks"],
            "users": [],
            "domains": ["domain:example.org"],
            "ips": [],
            "protocols": [],
            "enable": 1
        }
    ]

    monkeypatch.setattr("backend.xray.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.xray.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.xray.config.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.xray.config.get_all_routing_rules", lambda: mock_rules)
    monkeypatch.setattr("backend.xray.config.get_setting", lambda key: "false")

    config = generate_xray_config_json()
    from tests.core_verifier import validate_xray_config
    valid, msg = validate_xray_config(config)
    assert valid is True, f"Real Xray binary validation failed: {msg}"

    # 1. Verify Xray generated local SOCKS inbound for Hysteria 2 (port 20005 = 20000 + 5)
    socks_ib = next((ib for ib in config["inbounds"] if ib.get("tag") == "inbound-5-socks"), None)
    assert socks_ib is not None
    assert socks_ib["port"] == 20005
    assert socks_ib["protocol"] == "socks"
    assert socks_ib["settings"]["accounts"][0]["user"] == "user_h2"

    # 2. Verify routing rule avoids loop on hysteria-out-xray
    rule = next((r for r in config["routing"]["rules"] if r.get("outboundTag") == "hysteria-out-xray"), None)
    assert rule is not None
    assert "domain:example.org" in rule["domain"]


def test_core_isolation_matrix(monkeypatch):
    """Test that Xray ignores Sing-box inbounds and Sing-box ignores Xray inbounds."""
    mock_inbounds = [
        {
            "id": 100,
            "port": 10100,
            "protocol": "vless",
            "enable": 1,
            "core": "xray",
            "settings": "{}",
            "stream_settings": "{}",
            "sniffing": "{}"
        },
        {
            "id": 200,
            "port": 10200,
            "protocol": "vless",
            "enable": 1,
            "core": "singbox",
            "settings": "{}",
            "stream_settings": "{}",
            "sniffing": "{}"
        }
    ]

    monkeypatch.setattr("backend.xray.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.xray.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.xray.config.get_all_outbounds", lambda: [])
    monkeypatch.setattr("backend.xray.config.get_all_routing_rules", lambda: [])
    monkeypatch.setattr("backend.xray.config.get_setting", lambda key: "false")

    monkeypatch.setattr("backend.singbox.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.singbox.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.database.get_all_outbounds", lambda: [])
    monkeypatch.setattr("backend.database.get_all_routing_rules", lambda: [])

    # Xray config should contain inbound-100, but NOT inbound-200
    xray_cfg = generate_xray_config_json()
    from tests.core_verifier import validate_xray_config, validate_singbox_config
    valid, msg = validate_xray_config(xray_cfg)
    assert valid is True, f"Real Xray binary validation failed: {msg}"

    xray_tags = [ib.get("tag") for ib in xray_cfg["inbounds"]]
    assert "inbound-100" in xray_tags
    assert "inbound-200" not in xray_tags

    # Sing-box config should contain inbound-200, but NOT inbound-100
    singbox_cfg = generate_singbox_config_json()
    valid_sb, msg_sb = validate_singbox_config(singbox_cfg)
    assert valid_sb is True, f"Real sing-box binary validation failed: {msg_sb}"
    singbox_tags = [ib.get("tag") for ib in singbox_cfg["inbounds"]]
    assert "inbound-200" in singbox_tags
    assert "inbound-100" not in singbox_tags


def test_system_quick_blocks_matrix(monkeypatch):
    """Test global quick block rules (AdBlock, BitTorrent, Country Blocks) across Xray & Sing-box."""
    monkeypatch.setattr("backend.xray.config.get_all_inbounds", lambda: [])
    monkeypatch.setattr("backend.xray.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.singbox.config.get_all_inbounds", lambda: [])
    monkeypatch.setattr("backend.singbox.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.xray.config.get_all_outbounds", lambda: [])
    mock_quick_rules = [
        {"id": 1, "remark": "Блокировка BitTorrent", "outbound_tag": "blocked", "protocols": ["bittorrent"], "domains": [], "ips": [], "enable": 1},
        {"id": 2, "remark": "Блокировка рекламы", "outbound_tag": "blocked", "protocols": [], "domains": ["geosite:category-ads-all"], "ips": [], "enable": 1},
        {"id": 3, "remark": "Блокировка Китая (CN)", "outbound_tag": "blocked", "protocols": [], "domains": ["geosite:cn"], "ips": ["geoip:cn"], "enable": 1},
        {"id": 4, "remark": "Блокировка России (RU)", "outbound_tag": "blocked", "protocols": [], "domains": ["regexp:.*\\.ru$"], "ips": ["geoip:ru"], "enable": 1},
        {"id": 5, "remark": "Блокировка США (US)", "outbound_tag": "blocked", "protocols": [], "domains": ["regexp:.*\\.us$"], "ips": ["geoip:us"], "enable": 1},
    ]
    monkeypatch.setattr("backend.xray.config.get_all_routing_rules", lambda: mock_quick_rules)
    monkeypatch.setattr("backend.database.get_all_outbounds", lambda: [])
    monkeypatch.setattr("backend.database.get_all_routing_rules", lambda: mock_quick_rules)

    # Enable all quick blocks
    settings_dict = {
        "block_bittorrent": "true",
        "block_ads": "true",
        "block_cn": "true",
        "block_ru": "true",
        "block_us": "true"
    }

    monkeypatch.setattr("backend.xray.config.get_setting", lambda k: settings_dict.get(k, "false"))
    monkeypatch.setattr("backend.singbox.config.get_setting", lambda k: settings_dict.get(k, "false"))

    # Verify Xray Quick Block Rules
    xray_cfg = generate_xray_config_json()
    from tests.core_verifier import validate_xray_config, validate_singbox_config
    valid_x, msg_x = validate_xray_config(xray_cfg)
    assert valid_x is True, f"Real Xray binary validation failed: {msg_x}"

    xray_rules = xray_cfg["routing"]["rules"]
    assert any(r.get("outboundTag") == "blocked" and "bittorrent" in r.get("protocol", []) for r in xray_rules)
    assert any(r.get("outboundTag") == "blocked" and "geosite:category-ads-all" in r.get("domain", []) for r in xray_rules)
    assert any(r.get("outboundTag") == "blocked" and "geoip:cn" in r.get("ip", []) for r in xray_rules)

    # Verify Sing-box Quick Block Rules
    sb_cfg = generate_singbox_config_json()
    valid_sb, msg_sb = validate_singbox_config(sb_cfg)
    assert valid_sb is True, f"Real sing-box binary validation failed: {msg_sb}"
    sb_rules = sb_cfg["route"]["rules"]
    assert any(r.get("outbound") == "block" and "bittorrent" in r.get("protocol", []) for r in sb_rules)
    assert any(r.get("outbound") == "block" and "geosite-category-ads-all" in r.get("rule_set", []) for r in sb_rules)
    assert any(r.get("outbound") == "block" and "geoip-cn" in r.get("rule_set", []) for r in sb_rules)


def test_multi_split_routing_with_blocked_bittorrent(monkeypatch):
    """Test multi-split routing scenario: BitTorrent blocked, part to Hysteria, part to Direct, unrouted to Direct default."""
    mock_inbounds = [
        {
            "id": 99,
            "port": 10099,
            "protocol": "vless",
            "enable": 1,
            "core": "singbox",
            "settings": "{}",
            "stream_settings": "{}",
            "sniffing": "{}"
        }
    ]

    mock_outbounds = [
        {
            "id": 1,
            "remark": "Direct",
            "protocol": "freedom",
            "tag": "direct",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 2,
            "remark": "Hysteria2 Outbound",
            "protocol": "hysteria2",
            "tag": "hysteria2-vpn",
            "settings": json.dumps({"address": "1.1.1.1", "port": 443, "password": "pwd"}),
            "stream_settings": "{}",
            "enable": 1
        }
    ]

    mock_rules = [
        {
            "id": 0,
            "remark": "Блокировка BitTorrent",
            "outbound_tag": "blocked",
            "inbound_tags": [],
            "users": [],
            "domains": ["domain:torrent", "domain:tracker", "domain:peerexchange", "keyword:torrent"],
            "ips": [],
            "protocols": ["bittorrent"],
            "enable": 1
        },
        {
            "id": 1,
            "remark": "Route AI Traffic to Hysteria 2",
            "outbound_tag": "hysteria2-vpn",
            "inbound_tags": [],
            "users": [],
            "domains": ["geosite:openai", "domain:chatgpt.com"],
            "ips": [],
            "protocols": [],
            "enable": 1
        },
        {
            "id": 2,
            "remark": "Route RU Gov Traffic Direct",
            "outbound_tag": "direct",
            "inbound_tags": [],
            "users": [],
            "domains": ["geosite:category-gov-ru"],
            "ips": [],
            "protocols": [],
            "enable": 1
        }
    ]

    monkeypatch.setattr("backend.singbox.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.singbox.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.database.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.database.get_all_routing_rules", lambda: mock_rules)
    monkeypatch.setattr("backend.singbox.config.get_setting", lambda k: "true" if k == "block_bittorrent" else "false")

    config = generate_singbox_config_json()
    from tests.core_verifier import validate_singbox_config
    valid_sb, msg_sb = validate_singbox_config(config)
    assert valid_sb is True, f"Real sing-box binary validation failed: {msg_sb}"

    rules = config["route"]["rules"]

    # Rule 1 in Sing-box config MUST be BitTorrent Block
    assert rules[0]["outbound"] == "block"
    assert "bittorrent" in rules[0]["protocol"]

    # Rule 2 MUST be Hysteria2 VPN route for OpenAI/ChatGPT
    assert rules[1]["outbound"] == "hysteria2-vpn"
    assert "geosite-openai" in rules[1]["rule_set"]

    # Rule 3 MUST be Direct route for Gov RU
    assert rules[2]["outbound"] == "direct"
    assert "geosite-category-gov-ru" in rules[2]["rule_set"]

    # Outbounds fallback order: direct must be available for unrouted traffic
    assert config["outbounds"][0]["tag"] == "direct"


def test_outbounds_sorting_and_unused_filtering_all_cores(monkeypatch):
    """Test that outbounds sorting (direct first, blocked second) and unused outbound filtering work correctly across all cores."""
    mock_inbounds = [
        {
            "id": 1,
            "remark": "Xray Inbound VLESS",
            "port": 10001,
            "protocol": "vless",
            "enable": 1,
            "core": "xray",
            "settings": json.dumps({"clients": []}),
            "stream_settings": json.dumps({"security": "none"}),
            "sniffing": "{}"
        },
        {
            "id": 2,
            "remark": "Singbox Inbound VLESS",
            "port": 10002,
            "protocol": "vless",
            "enable": 1,
            "core": "singbox",
            "settings": json.dumps({"clients": []}),
            "stream_settings": json.dumps({"security": "none"}),
            "sniffing": "{}"
        }
    ]

    mock_outbounds = [
        {
            "id": 1,
            "remark": "Unused Hysteria 2 Outbound",
            "protocol": "hysteria2",
            "tag": "unused-hysteria-out",
            "settings": json.dumps({"address": "1.1.1.1", "port": 443, "password": "pwd"}),
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 2,
            "remark": "Direct Outbound",
            "protocol": "freedom",
            "tag": "direct",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 3,
            "remark": "Blocked Outbound",
            "protocol": "blackhole",
            "tag": "blocked",
            "settings": "{}",
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 4,
            "remark": "Used WARP Socks Outbound",
            "protocol": "socks",
            "tag": "used-warp-socks",
            "settings": json.dumps({"servers": [{"address": "127.0.0.1", "port": 40000}]}),
            "stream_settings": "{}",
            "enable": 1
        },
        {
            "id": 5,
            "remark": "Unused VLESS Outbound",
            "protocol": "vless",
            "tag": "unused-vless-out",
            "settings": json.dumps({"vnext": [{"address": "2.2.2.2", "port": 443}]}),
            "stream_settings": "{}",
            "enable": 1
        }
    ]

    mock_rules = [
        {
            "id": 1,
            "remark": "Route OpenAI to WARP Socks",
            "outbound_tag": "used-warp-socks",
            "inbound_tags": ["inbound-1"],
            "users": [],
            "domains": ["domain:openai.com"],
            "ips": [],
            "protocols": [],
            "enable": 1
        }
    ]

    # Monkeypatch for Xray
    monkeypatch.setattr("backend.xray.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.xray.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.xray.config.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.xray.config.get_all_routing_rules", lambda: mock_rules)
    monkeypatch.setattr("backend.xray.config.get_setting", lambda k: "false")

    # Monkeypatch for Singbox
    monkeypatch.setattr("backend.singbox.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.singbox.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.database.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.database.get_all_routing_rules", lambda: mock_rules)
    monkeypatch.setattr("backend.singbox.config.get_setting", lambda k: "false")

    # 1. Test Xray config generation
    xray_config = generate_xray_config_json()
    from tests.core_verifier import validate_xray_config
    valid_xray, msg_xray = validate_xray_config(xray_config)
    assert valid_xray is True, f"Real Xray binary validation failed: {msg_xray}"

    # Verify sorting: direct #0, blocked #1
    assert xray_config["outbounds"][0]["tag"] == "direct"
    assert xray_config["outbounds"][1]["tag"] == "blocked"

    # Verify filtering: used-warp-socks is present, unused outbounds are excluded
    xray_out_tags = [ob["tag"] for ob in xray_config["outbounds"]]
    assert "used-warp-socks" in xray_out_tags
    assert "unused-hysteria-out" not in xray_out_tags
    assert "unused-vless-out" not in xray_out_tags

    # 2. Test Sing-box config generation
    singbox_config = generate_singbox_config_json()
    from tests.core_verifier import validate_singbox_config
    valid_sb, msg_sb = validate_singbox_config(singbox_config)
    assert valid_sb is True, f"Real sing-box binary validation failed: {msg_sb}"

    # Verify sorting: direct #0
    assert singbox_config["outbounds"][0]["tag"] == "direct"


def test_quick_security_rules_custom_outbounds_for_all_cores(monkeypatch):
    """
    Tests that quick security / country site rules with custom destination outbounds (DIRECT, BLOCKED, WARP)
    are compiled properly and valid for both Xray and Sing-box real core binaries.
    """
    from backend.database import sync_quick_security_rules, get_all_routing_rules
    from backend.xray.config import generate_xray_config_json
    from backend.singbox.config import generate_singbox_config_json
    from tests.core_verifier import validate_xray_config, validate_singbox_config

    # Sync custom outbounds for quick rules
    sync_quick_security_rules({
        "block_ru": True,
        "block_ru_outbound": "direct",
        "block_cn": True,
        "block_cn_outbound": "blocked",
        "block_us": True,
        "block_us_outbound": "warp_out",
        "block_bittorrent": True,
        "block_bittorrent_outbound": "blocked",
        "block_ads": True,
        "block_ads_outbound": "direct"
    })

    mock_inbounds = [
        {
            "id": 1,
            "port": 10001,
            "protocol": "vless",
            "enable": 1,
            "core": "all",
            "settings": json.dumps({"decryption": "none"}),
            "stream_settings": json.dumps({"security": "none"})
        }
    ]

    mock_outbounds = [
        {"id": 1, "remark": "Direct", "protocol": "freedom", "tag": "direct", "settings": "{}", "stream_settings": "{}", "enable": 1},
        {"id": 2, "remark": "WARP", "protocol": "socks", "tag": "warp_out", "settings": json.dumps({"address": "127.0.0.1", "port": 40000}), "stream_settings": "{}", "enable": 1}
    ]

    rules = get_all_routing_rules()

    monkeypatch.setattr("backend.xray.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.xray.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.xray.config.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.xray.config.get_all_routing_rules", lambda: rules)
    monkeypatch.setattr("backend.xray.config.get_setting", lambda k: "false")

    monkeypatch.setattr("backend.singbox.config.get_all_inbounds", lambda: mock_inbounds)
    monkeypatch.setattr("backend.singbox.config.get_clients_for_inbound", lambda ib_id: [])
    monkeypatch.setattr("backend.database.get_all_outbounds", lambda: mock_outbounds)
    monkeypatch.setattr("backend.database.get_all_routing_rules", lambda: rules)
    monkeypatch.setattr("backend.singbox.config.get_setting", lambda k: "false")

    # 1. Validate Xray
    xray_cfg = generate_xray_config_json()
    valid_x, msg_x = validate_xray_config(xray_cfg)
    assert valid_x is True, f"Real Xray binary validation failed: {msg_x}"

    x_rules = xray_cfg["routing"]["rules"]
    ru_rule_x = next((r for r in x_rules if "regexp:.*\\.ru$" in r.get("domain", [])), None)
    assert ru_rule_x is not None
    assert ru_rule_x["outboundTag"] == "direct"

    cn_rule_x = next((r for r in x_rules if "geosite:cn" in r.get("domain", [])), None)
    assert cn_rule_x is not None
    assert cn_rule_x["outboundTag"] == "blocked"

    us_rule_x = next((r for r in x_rules if "regexp:.*\\.us$" in r.get("domain", [])), None)
    assert us_rule_x is not None
    assert us_rule_x["outboundTag"] == "warp_out"

    # 2. Validate Sing-box
    sb_cfg = generate_singbox_config_json()
    valid_s, msg_s = validate_singbox_config(sb_cfg)
    assert valid_s is True, f"Real Sing-box binary validation failed: {msg_s}"

    sb_rules = sb_cfg["route"]["rules"]
    ru_rule_s = next((r for r in sb_rules if ".*\\.ru$" in r.get("domain_regex", [])), None)
    assert ru_rule_s is not None
    assert ru_rule_s["outbound"] == "direct"

    cn_rule_s = next((r for r in sb_rules if "geosite-cn" in r.get("rule_set", [])), None)
    assert cn_rule_s is not None
    assert cn_rule_s["outbound"] == "block"

    us_rule_s = next((r for r in sb_rules if ".*\\.us$" in r.get("domain_regex", [])), None)
    assert us_rule_s is not None
    assert us_rule_s["outbound"] == "warp_out"


