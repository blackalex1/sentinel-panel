import json
import pytest
from backend.links_generator import get_client_links, get_client_mihomo_proxy

def test_socks_http_client_links():
    """Test generating subscription links and Mihomo proxy config for SOCKS5 and HTTP."""
    inbound_socks = {"id": 1, "protocol": "socks", "port": 1080, "remark": "TestSocks"}
    inbound_http = {"id": 2, "protocol": "http", "port": 8080, "remark": "TestHttp"}
    client = {"email": "alex", "client_uuid_or_pwd": "secretpassword"}

    links_socks = get_client_links(inbound_socks, client, "1.2.3.4")
    assert links_socks[0] == "socks5://alex:secretpassword@1.2.3.4:1080#TestSocks-alex"

    links_http = get_client_links(inbound_http, client, "1.2.3.4")
    assert links_http[0] == "http://alex:secretpassword@1.2.3.4:8080#TestHttp-alex"

    mihomo_socks = get_client_mihomo_proxy(inbound_socks, client, "1.2.3.4")
    assert mihomo_socks["type"] == "socks5"
    assert mihomo_socks["username"] == "alex"
    assert mihomo_socks["password"] == "secretpassword"

    mihomo_http = get_client_mihomo_proxy(inbound_http, client, "1.2.3.4")
    assert mihomo_http["type"] == "http"
    assert mihomo_http["username"] == "alex"
    assert mihomo_http["password"] == "secretpassword"
