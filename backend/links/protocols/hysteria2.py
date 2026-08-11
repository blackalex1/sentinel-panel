from urllib.parse import quote
from backend.links.protocols.utils import get_cert_sha256_fingerprint, is_ip

def get_hysteria2_cert_path(inbound: dict, stream_settings: dict, sni: str) -> str:
    hysteria_opts = stream_settings.get('hysteria', {})
    cert_mode = hysteria_opts.get('certMode', 'self')
    cert_path = ""
    if cert_mode == 'custom':
        cert_path = hysteria_opts.get('certPath', '')
    else:
        if cert_mode == 'self' and sni:
            from backend.config import CONFIG_DIR
            from backend.ssl_utils import generate_custom_self_signed_cert
            custom_cert = CONFIG_DIR / f"hysteria_{inbound.get('id')}.crt"
            custom_key = CONFIG_DIR / f"hysteria_{inbound.get('id')}.key"
            
            # Ensure cert is generated to get the correct pinSHA256 fingerprint
            generate_custom_self_signed_cert(custom_cert, custom_key, sni)
            cert_path = str(custom_cert)
        else:
            from backend.ssl_utils import SSL_CERT_PATH
            if SSL_CERT_PATH.exists():
                cert_path = str(SSL_CERT_PATH)
            else:
                from backend.config import BIN_DIR
                p = BIN_DIR / "hysteria.crt"
                if p.exists():
                    cert_path = str(p)
    return cert_path


def build_hysteria2_link(inbound: dict, client: dict, host: str, port: int, display_name: str, stream_settings: dict, client_email: str) -> str:
    password = client.get('client_uuid_or_pwd') or client.get('password')
    
    hysteria_opts = stream_settings.get('hysteria', {})
    obfs_password = hysteria_opts.get('obfsPassword', '')
    hop = hysteria_opts.get('hop', '')

    up_mbps = hysteria_opts.get('upMbps') or hysteria_opts.get('up_mbps')
    down_mbps = hysteria_opts.get('downMbps') or hysteria_opts.get('down_mbps')
    ignore_bw = hysteria_opts.get('ignoreClientBandwidth', False)

    sni = hysteria_opts.get('sni') or stream_settings.get('sni')
    params = []
    
    if sni:
        params.append(f"sni={sni}")
    elif not is_ip(host):
        params.append(f"sni={host}")
        
    cert_mode = hysteria_opts.get('certMode', 'self')
    cert_path = get_hysteria2_cert_path(inbound, stream_settings, sni)
            
    fp_hash = None
    if cert_path:
        fp_hash = get_cert_sha256_fingerprint(cert_path)
        if fp_hash:
            params.append(f"pinSHA256={fp_hash}")
        
    if cert_mode == 'self' or not fp_hash:
        params.append("insecure=1")
        
    if not ignore_bw:
        try:
            if up_mbps and int(up_mbps) > 0:
                params.append(f"up={up_mbps}")
        except ValueError:
            pass
        try:
            if down_mbps and int(down_mbps) > 0:
                params.append(f"down={down_mbps}")
        except ValueError:
            pass

    if obfs_password:
        params.append("obfs=salamander")
        params.append(f"obfs-password={quote(obfs_password, safe='')}")
    if hop:
        params.append(f"hop={quote(hop, safe='')}")
        params.append(f"mport={quote(hop, safe='')}")
        params.append(f"ports={quote(hop, safe='')}")
        
    query = "&".join(params)
    username = quote(client_email, safe='')
    encoded_password = quote(password, safe='')
    return f"hysteria2://{username}:{encoded_password}@{host}:{port}?{query}#{quote(display_name)}"


def build_hysteria2_mihomo_proxy(inbound: dict, client: dict, host: str, port: int, display_name: str, stream_settings: dict, client_email: str) -> dict:
    raw_password = client.get('client_uuid_or_pwd') or client.get('password') or ""
    full_password = f"{client_email}:{raw_password}" if (client_email and ":" not in str(raw_password)) else raw_password

    hysteria_opts = stream_settings.get('hysteria', {})
    obfs_password = hysteria_opts.get('obfsPassword', '')
    hop = hysteria_opts.get('hop', '')

    up_mbps = hysteria_opts.get('upMbps') or hysteria_opts.get('up_mbps')
    down_mbps = hysteria_opts.get('downMbps') or hysteria_opts.get('down_mbps')
    ignore_bw = hysteria_opts.get('ignoreClientBandwidth', False)

    sni = hysteria_opts.get('sni') or stream_settings.get('sni')
    if not sni and not is_ip(host):
        sni = host

    proxy = {
        "name": display_name,
        "type": "hysteria2",
        "server": host,
        "port": int(port),
        "password": full_password,
        "sni": sni or host,
        "skip-cert-verify": True,
        "tfo": False
    }

    if not ignore_bw:
        try:
            if up_mbps and int(up_mbps) > 0:
                proxy["up"] = f"{up_mbps} Mbps"
        except ValueError:
            pass
        try:
            if down_mbps and int(down_mbps) > 0:
                proxy["down"] = f"{down_mbps} Mbps"
        except ValueError:
            pass

    if hop:
        proxy["ports"] = hop

    if obfs_password:
        proxy["obfs"] = "salamander"
        proxy["obfs-password"] = obfs_password

    cert_path = get_hysteria2_cert_path(inbound, stream_settings, sni)
    if cert_path:
        fp_hash = get_cert_sha256_fingerprint(cert_path)
        if fp_hash:
            proxy["ca-sha256"] = fp_hash

    return proxy

