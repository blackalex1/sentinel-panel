import json
import base64
from backend.links.protocols.utils import get_cert_sha256_fingerprint, get_configured_fingerprint

def build_vmess_link(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict, stream_settings: dict, network: str, security: str, security_cipher: str, alter_id: int) -> str:
    uid = client.get('client_uuid_or_pwd') or client.get('id')
    
    vmess_obj = {
        "v": "2",
        "ps": display_name,
        "add": host,
        "port": port,
        "id": uid,
        "aid": alter_id,
        "scy": security_cipher,
        "net": network,
        "type": "none",
        "host": "",
        "path": "",
        "tls": security if security in ('tls', 'reality') else "none",
        "sni": "",
        "fp": ""
    }
    
    if security == 'tls':
        tls_settings = stream_settings.get('tlsSettings', {})
        vmess_obj["sni"] = tls_settings.get('serverName', '')
        
        alpn = tls_settings.get('alpn', [])
        if alpn:
            vmess_obj["alpn"] = ','.join(alpn)
        
        fp = get_configured_fingerprint(stream_settings, 'tls')
        if fp:
            vmess_obj["fp"] = fp
        
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
                vmess_obj["pcs"] = fp_hash
    elif security == 'reality':
        reality_settings = stream_settings.get('realitySettings', {})
        vmess_obj["sni"] = reality_settings.get('serverName') or (reality_settings.get('serverNames', [''])[0])
        vmess_obj["fp"] = get_configured_fingerprint(stream_settings, 'reality')

    if network == 'tcp':
        tcp_settings = stream_settings.get('tcpSettings', {})
        header = tcp_settings.get('header', {})
        if header.get('type') == 'http':
            vmess_obj["type"] = "http"
            req = header.get('request', {})
            paths = req.get('path', ['/'])
            hosts = req.get('headers', {}).get('Host', [])
            if paths: vmess_obj["path"] = paths[0]
            if hosts: vmess_obj["host"] = hosts[0]
    elif network == 'ws':
        ws_settings = stream_settings.get('wsSettings', {})
        vmess_obj["path"] = ws_settings.get('path', '/')
        vmess_obj["host"] = ws_settings.get('headers', {}).get('Host', '')
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings', {})
        vmess_obj["path"] = grpc_settings.get('serviceName', 'grpc')
    elif network == 'h2':
        h2_settings = stream_settings.get('httpSettings', {})
        vmess_obj["path"] = h2_settings.get('path', '/')
        hosts = h2_settings.get('host', [])
        if hosts: vmess_obj["host"] = hosts[0]
    elif network == 'mkcp':
        kcp_settings = stream_settings.get('kcpSettings', {})
        header = kcp_settings.get('header', {})
        vmess_obj["type"] = header.get('type', 'none')
        vmess_obj["path"] = kcp_settings.get('seed', '')
    elif network == 'httpupgrade':
        hu_settings = stream_settings.get('httpupgradeSettings', {})
        vmess_obj["path"] = hu_settings.get('path', '/')
        vmess_obj["host"] = hu_settings.get('host', '')
    elif network == 'xhttp':
        xhttp_settings = stream_settings.get('xhttpSettings', {})
        vmess_obj["path"] = xhttp_settings.get('path', '/')
        vmess_obj["host"] = xhttp_settings.get('host', '')

    # Mux parameters
    from backend.database import get_setting
    mux_enabled = get_setting("mux_enabled", "false") == "true"
    if mux_enabled:
        mux_concurrency = get_setting("mux_concurrency", "8")
        vmess_obj["mux"] = 1
        try:
            vmess_obj["muxConcurrency"] = int(mux_concurrency)
        except ValueError:
            vmess_obj["muxConcurrency"] = 8
        mux_xver = get_setting("mux_xver", "0")
        if mux_xver and mux_xver != "0":
            try:
                vmess_obj["xver"] = int(mux_xver)
            except ValueError:
                pass

    json_str = json.dumps(vmess_obj)
    b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    return f"vmess://{b64_str}"


def build_vmess_mihomo_proxy(inbound: dict, client: dict, host: str, port: int, display_name: str, settings: dict, stream_settings: dict, network: str, security: str, security_cipher: str, alter_id: int) -> dict:
    uid = client.get('client_uuid_or_pwd') or client.get('id') or ""
    
    proxy = {
        "name": display_name,
        "type": "vmess",
        "server": host,
        "port": int(port),
        "uuid": uid,
        "alterId": alter_id,
        "cipher": security_cipher or "auto",
        "udp": True
    }

    if security in ('tls', 'reality'):
        tls_settings = stream_settings.get('tlsSettings', {})
        sni = tls_settings.get('serverName', '')
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

    return proxy

