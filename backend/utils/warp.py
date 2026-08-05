import os
import json
import base64
import urllib.request
import logging
from typing import Dict, Optional
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization

def register_warp() -> Optional[Dict]:
    """
    Registers a new Cloudflare WARP account.
    Returns a dictionary containing:
      - private_key: Base64-encoded Curve25519 client private key
      - public_key: Base64-encoded Curve25519 client public key
      - address_v4: IPv4 interface address (typically 172.16.0.2/32)
      - address_v6: IPv6 interface address
      - peer_public_key: Cloudflare peer public key
      - endpoint: Cloudflare endpoint host:port (engage.cloudflareclient.com:2408)
      - reserved: List of 3 integers representing client identity bytes (reserved bytes)
    """
    # 1. Generate Curve25519 client key pair
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    priv_b64 = base64.b64encode(private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )).decode('utf-8')
    
    pub_b64 = base64.b64encode(public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )).decode('utf-8')
    
    # 2. Register with Cloudflare API
    url = "https://api.cloudflareclient.com/v0a2158/reg"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": "okhttp/3.12.1"
    }
    payload = {
        "key": pub_b64,
        "install_id": "",
        "fcm_token": "",
        "referrer": "",
        "warp_enabled": True,
        "tos": "2020-06-30T00:00:00.000+02:00",
        "type": "Android",
        "locale": "en_US"
    }
    
    try:
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        
        # We disable verification in case of local networking/proxy issues, but standard SSL context is fine
        with urllib.request.urlopen(req, timeout=15) as response:
            status = response.status
            body = response.read().decode('utf-8')
            
            if status not in (200, 201):
                logging.error(f"[WARP Registration] Server returned status {status}: {body}")
                return None
                
            res_json = json.loads(body)
            
            # Extract config parameters
            config = res_json.get("config", {})
            interface = config.get("interface", {})
            addresses = interface.get("addresses", {})
            
            address_v4 = addresses.get("v4", "172.16.0.2/32")
            address_v6 = addresses.get("v6", "")
            
            peers = config.get("peers", [])
            peer_pub_key = "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wRl3gA=" # fallback
            endpoint = "engage.cloudflareclient.com:2408" # fallback
            
            if peers:
                peer = peers[0]
                peer_pub_key = peer.get("public_key", peer_pub_key)
                peer_endpoint = peer.get("endpoint", {})
                endpoint = peer_endpoint.get("host", endpoint)
                
            # Extract client identity / reserved bytes
            reserved_bytes = [0, 0, 0]
            client_identity = res_json.get("client_identity") or config.get("client_identity") or interface.get("client_identity")
            if client_identity:
                try:
                    # Could be base64 string
                    decoded = base64.b64decode(client_identity)
                    if len(decoded) >= 3:
                        reserved_bytes = list(decoded[:3])
                except Exception:
                    pass
            else:
                # Some API versions return config.client_id
                client_id = config.get("client_id")
                if client_id:
                    try:
                        decoded = base64.b64decode(client_id)
                        if len(decoded) >= 3:
                            reserved_bytes = list(decoded[:3])
                    except Exception:
                        pass
                        
            return {
                "private_key": priv_b64,
                "public_key": pub_b64,
                "address_v4": address_v4,
                "address_v6": address_v6,
                "peer_public_key": peer_pub_key,
                "endpoint": endpoint,
                "reserved": reserved_bytes
            }
            
    except Exception as e:
        logging.error(f"[WARP Registration] Failed to register: {e}")
        return None
