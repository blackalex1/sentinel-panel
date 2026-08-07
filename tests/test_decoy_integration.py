import pytest
import json
import httpx
from backend.database import set_setting, get_setting, db_session, Inbound, ClientStats
from backend.hysteria.config import generate_hysteria_config
from backend.xray.config_builder.builder import generate_xray_config_json


@pytest.fixture(autouse=True)
def reset_decoy():
    yield
    set_setting("decoy_type", "none")
    set_setting("decoy_value", "company_landing")


def test_hysteria_config_inherits_central_decoy_drop():
    """Test that Hysteria 2 config generator inherits central panel 'drop' decoy setting."""
    set_setting("decoy_type", "drop")
    config = generate_hysteria_config(1, 8443, [])
    assert "masquerade" in config
    assert config["masquerade"]["type"] == "string"
    assert config["masquerade"]["string"]["statusCode"] == 444


def test_hysteria_config_inherits_central_decoy_none():
    """Test that Hysteria 2 config generator inherits central panel 'none' (404) decoy setting."""
    set_setting("decoy_type", "none")
    config = generate_hysteria_config(1, 8443, [])
    assert "masquerade" in config
    assert config["masquerade"]["type"] == "string"
    assert config["masquerade"]["string"]["statusCode"] == 404


def test_hysteria_config_inherits_central_decoy_proxy():
    """Test that Hysteria 2 config generator inherits central panel 'proxy' decoy setting."""
    set_setting("decoy_type", "proxy")
    set_setting("decoy_value", "https://example.com")
    config = generate_hysteria_config(1, 8443, [])
    assert "masquerade" in config
    assert config["masquerade"]["type"] == "proxy"
    assert config["masquerade"]["proxy"]["url"] == "https://example.com"


def test_xray_config_builder_fallbacks_central_decoy():
    """Test that Xray config builder adds default fallbacks to local panel port for VLESS TLS inbounds."""
    set_setting("decoy_type", "drop")
    with db_session() as session:
        ib = Inbound(
            remark="VLESS TLS Central Decoy Test",
            port=3443,
            protocol="vless",
            settings=json.dumps({"decryption": "none"}),
            stream_settings=json.dumps({"network": "tcp", "security": "tls"}),
            sniffing="{}",
            enable=1
        )
        session.add(ib)
        session.commit()
        ib_id = ib.id
        cs = ClientStats(inbound_id=ib_id, email="decoy_integration_user@domain.com", client_uuid_or_pwd="22222222-2222-2222-2222-222222222222", enable=1)
        session.add(cs)
        session.commit()

    config = generate_xray_config_json()
    inbounds = config.get("inbounds", [])
    vless_inbound = next((ib_item for ib_item in inbounds if ib_item.get("tag") == f"inbound-{ib_id}"), None)
    assert vless_inbound is not None
    assert "fallbacks" in vless_inbound["settings"]
    assert len(vless_inbound["settings"]["fallbacks"]) > 0
    from backend.config import settings
    expected_port = getattr(settings, "PANEL_PORT", 8000)
    assert vless_inbound["settings"]["fallbacks"][0]["dest"] == expected_port
