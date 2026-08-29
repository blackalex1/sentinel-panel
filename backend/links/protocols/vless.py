from urllib.parse import quote
from backend.links.protocols.utils import get_cert_sha256_fingerprint, get_configured_fingerprint

def build_vless_link(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict, stream_settings: dict, network: str, security: str, flow: str) -> str:
    uid = client.get('client_uuid_or_pwd') or client.get('id')
    
    params = [
        f"type={network}",
        f"security={security}"
    ]
    
    if flow:
        params.append(f"flow={flow}")
        
    encryption = settings.get("encryption")
    if encryption:
        params.append(f"encryption={encryption}")
        
    if security == 'reality':
        reality_settings = stream_settings.get('realitySettings', {})
        inner_settings = reality_settings.get('settings', {})
        fp = get_configured_fingerprint(stream_settings, 'reality')
        pbk = inner_settings.get('publicKey') or reality_settings.get('publicKey', '')
        raw_sni = inner_settings.get('serverName') or reality_settings.get('serverName')
        if not raw_sni:
            s_names = reality_settings.get('serverNames', [''])
            raw_sni = s_names[0] if isinstance(s_names, list) and s_names else str(s_names)
        sni = raw_sni.split(',')[0].strip() if isinstance(raw_sni, str) else ''
        spx = inner_settings.get('spiderX') or reality_settings.get('spiderX', '/')
        
        params.append(f"fp={fp}")
        params.append(f"pbk={pbk}")
        if sni: params.append(f"sni={sni}")
        
        short_ids = inner_settings.get('shortIds') or reality_settings.get('shortIds', [])
        if short_ids: params.append(f"sid={short_ids[0]}")
        if spx: params.append(f"spx={quote(spx, safe='')}")
    
    elif security == 'tls':
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
            params.append("headerType=http")
            req = header.get('request', {})
            paths = req.get('path', ['/'])
            hosts = req.get('headers', {}).get('Host', [])
            if paths: params.append(f"path={quote(paths[0], safe='')}")
            if hosts: params.append(f"host={quote(hosts[0], safe='')}")
    elif network == 'ws':
        ws_settings = stream_settings.get('wsSettings', {})
        path = ws_settings.get('path', '/')
        params.append(f"path={quote(path, safe='')}")
        ws_host = ws_settings.get('headers', {}).get('Host')
        if ws_host: params.append(f"host={ws_host}")
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings', {})
        service_name = grpc_settings.get('serviceName', 'grpc')
        params.append(f"serviceName={quote(service_name, safe='')}")
    elif network == 'h2':
        h2_settings = stream_settings.get('httpSettings', {})
        path = h2_settings.get('path', '/')
        params.append(f"path={quote(path, safe='')}")
        hosts = h2_settings.get('host', [])
        if hosts: params.append(f"host={quote(hosts[0], safe='')}")
    elif network == 'mkcp':
        kcp_settings = stream_settings.get('kcpSettings', {})
        header = kcp_settings.get('header', {})
        header_type = header.get('type', 'none')
        seed = kcp_settings.get('seed', '')
        params.append(f"headerType={header_type}")
        if seed: params.append(f"seed={quote(seed, safe='')}")
    elif network == 'httpupgrade':
        hu_settings = stream_settings.get('httpupgradeSettings', {})
        path = hu_settings.get('path', '/')
        params.append(f"path={quote(path, safe='')}")
        hu_host = hu_settings.get('host', '')
        if hu_host: params.append(f"host={hu_host}")
    elif network == 'xhttp':
        xh_settings = stream_settings.get('xhttpSettings', {})
        path = xh_settings.get('path', '/')
        mode = xh_settings.get('mode', 'auto')
        params.append(f"path={quote(path, safe='')}")
        params.append(f"mode={mode}")
        
    query = "&".join(params)
    return f"vless://{uid}@{host}:{port}?{query}#{quote(display_name)}"


def build_vless_mihomo_proxy(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict, stream_settings: dict, network: str, security: str, flow: str) -> dict:
    uid = client.get('client_uuid_or_pwd') or client.get('id') or ""
    
    proxy = {
        "name": display_name,
        "type": "vless",
        "server": host,
        "port": int(port),
        "uuid": uid,
        "udp": True
    }
    
    encryption = settings.get("encryption")
    if encryption and encryption != "none":
        proxy["encryption"] = encryption

    if flow:
        proxy["flow"] = flow
        
    if security == 'reality':
        reality_settings = stream_settings.get('realitySettings', {})
        inner_settings = reality_settings.get('settings', {})
        
        fp = get_configured_fingerprint(stream_settings, 'reality')
        pbk = inner_settings.get('publicKey') or reality_settings.get('publicKey', '')
        sni = inner_settings.get('serverName') or reality_settings.get('serverName') or (reality_settings.get('serverNames', [''])[0])
        short_ids = inner_settings.get('shortIds') or reality_settings.get('shortIds', [])
        spx = inner_settings.get('spiderX') or reality_settings.get('spiderX') or reality_settings.get('spx')
        
        proxy["tls"] = True
        if sni:
            proxy["servername"] = sni
        proxy["client-fingerprint"] = fp
        proxy["reality-opts"] = {
            "public-key": pbk,
            "short-id": short_ids[0] if short_ids else ""
        }
        if spx:
            proxy["reality-opts"]["spider-x"] = spx
    elif security == 'tls':
        tls_settings = stream_settings.get('tlsSettings', {})
        sni = tls_settings.get('serverName')
        fp = get_configured_fingerprint(stream_settings, 'tls')
        
        proxy["tls"] = True
        if sni:
            proxy["servername"] = sni
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
    elif network in ('h2', 'http'):
        h2_settings = stream_settings.get('httpSettings', {})
        path = h2_settings.get('path', '/')
        hosts = h2_settings.get('host', [])
        proxy["network"] = "h2"
        proxy["h2-opts"] = {"path": path, "host": hosts if hosts else [host]}
    elif network == 'httpupgrade':
        hu_settings = stream_settings.get('httpupgradeSettings', {})
        path = hu_settings.get('path', '/')
        hu_host = hu_settings.get('host', '')
        proxy["network"] = "httpupgrade"
        proxy["httpupgrade-opts"] = {"path": path}
        if hu_host:
            proxy["httpupgrade-opts"]["host"] = hu_host
    return proxy
