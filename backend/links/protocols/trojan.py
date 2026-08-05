from urllib.parse import quote
from backend.links.protocols.utils import get_cert_sha256_fingerprint, get_configured_fingerprint

def build_trojan_link(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict, stream_settings: dict, network: str, security: str) -> str:
    password = client.get('client_uuid_or_pwd') or client.get('password')
    
    params = [f"security={security}"]
    if security == 'tls':
        tls_settings = stream_settings.get('tlsSettings', {})
        sni = tls_settings.get('serverName')
        if sni: params.append(f"sni={sni}")
        
        alpn = tls_settings.get('alpn', [])
        if alpn:
            params.append(f"alpn={quote(','.join(alpn), safe='')}")
        
        fp = get_configured_fingerprint(stream_settings, 'tls')
        if fp: params.append(f"fp={fp}")
        
        certs = tls_settings.get('certificates', [])
        cert_path = ""
        if certs and isinstance(certs, list):
            cert_path = certs[0].get('certificateFile', '')
        if not cert_path:
            from backend.config import CONFIG_DIR
            p = CONFIG_DIR / "cert.pem"
            if p.exists():
                cert_path = str(p)
        
        if cert_path:
            fp_hash = get_cert_sha256_fingerprint(cert_path)
            if fp_hash:
                params.append(f"pcs={fp_hash}")
    
    # Transport parameters
    if network == 'tcp':
        tcp_settings = stream_settings.get('tcpSettings', {})
        header = tcp_settings.get('header', {})
        if header.get('type') == 'http':
            params.append("type=tcp")
            params.append("headerType=http")
            req = header.get('request', {})
            paths = req.get('path', ['/'])
            hosts = req.get('headers', {}).get('Host', [])
            if paths: params.append(f"path={quote(paths[0], safe='')}")
            if hosts: params.append(f"host={quote(hosts[0], safe='')}")
        else:
            params.append("type=tcp")
    elif network == 'ws':
        ws_settings = stream_settings.get('wsSettings', {})
        path = ws_settings.get('path', '/')
        params.append(f"type=ws")
        params.append(f"path={quote(path, safe='')}")
        ws_host = ws_settings.get('headers', {}).get('Host')
        if ws_host: params.append(f"host={ws_host}")
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings', {})
        service_name = grpc_settings.get('serviceName', 'grpc')
        params.append(f"type=grpc")
        params.append(f"serviceName={quote(service_name, safe='')}")
    elif network == 'h2':
        h2_settings = stream_settings.get('httpSettings', {})
        path = h2_settings.get('path', '/')
        params.append(f"type=h2")
        params.append(f"path={quote(path, safe='')}")
        hosts = h2_settings.get('host', [])
        if hosts: params.append(f"host={quote(hosts[0], safe='')}")
    elif network == 'mkcp':
        kcp_settings = stream_settings.get('kcpSettings', {})
        header = kcp_settings.get('header', {})
        header_type = header.get('type', 'none')
        seed = kcp_settings.get('seed', '')
        params.append(f"type=kcp")
        params.append(f"headerType={header_type}")
        if seed: params.append(f"seed={quote(seed, safe='')}")
    elif network == 'httpupgrade':
        hu_settings = stream_settings.get('httpupgradeSettings', {})
        path = hu_settings.get('path', '/')
        params.append(f"type=httpupgrade")
        params.append(f"path={quote(path, safe='')}")
        hu_host = hu_settings.get('host')
        if hu_host: params.append(f"host={hu_host}")
    elif network == 'xhttp':
        xhttp_settings = stream_settings.get('xhttpSettings', {})
        path = xhttp_settings.get('path', '/')
        params.append(f"type=xhttp")
        params.append(f"path={quote(path, safe='')}")
        xhttp_host = xhttp_settings.get('host')
        if xhttp_host: params.append(f"host={xhttp_host}")

    # Mux parameters
    from backend.database import get_setting
    mux_enabled = get_setting("mux_enabled", "false") == "true"
    if mux_enabled:
        mux_concurrency = get_setting("mux_concurrency", "8")
        params.append("mux=1")
        if mux_concurrency:
            params.append(f"muxConcurrency={mux_concurrency}")
        mux_xver = get_setting("mux_xver", "0")
        if mux_xver and mux_xver != "0":
            params.append(f"xver={mux_xver}")

    query = "&".join(params)
    return f"trojan://{password}@{host}:{port}?{query}#{quote(display_name)}"


def build_trojan_mihomo_proxy(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict, stream_settings: dict, network: str, security: str) -> dict:
    password = client.get('client_uuid_or_pwd') or client.get('password') or ""
    
    proxy = {
        "name": display_name,
        "type": "trojan",
        "server": host,
        "port": int(port),
        "password": password,
        "udp": True
    }

    if security == 'tls':
        tls_settings = stream_settings.get('tlsSettings', {})
        sni = tls_settings.get('serverName')
        fp = get_configured_fingerprint(stream_settings, 'tls')
        if sni:
            proxy["sni"] = sni
        if fp:
            proxy["client-fingerprint"] = fp
        proxy["skip-cert-verify"] = True

    if network == 'ws':
        ws_settings = stream_settings.get('wsSettings', {})
        path = ws_settings.get('path', '/')
        ws_host = ws_settings.get('headers', {}).get('Host')
        proxy["network"] = "ws"
        proxy["ws-opts"] = {"path": path}
        if ws_host:
            proxy["ws-opts"]["headers"] = {"Host": ws_host}
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings', {})
        service_name = grpc_settings.get('serviceName', 'grpc')
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {"grpc-service-name": service_name}

    return proxy

