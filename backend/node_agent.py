import os
import json
import time
import logging
import hashlib
import httpx
from pathlib import Path
from typing import Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519

# Set the config file to be in the folder where the app/bot runs (working directory)
CONFIG_FILE_PATH = Path("config/node_config.json")

def load_node_config() -> Optional[dict]:
    """Loads the node configuration if registered."""
    if CONFIG_FILE_PATH.exists():
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"[Node Agent] Failed to read config file: {e}")
    return None

def save_node_config(config: dict):
    """Saves the node configuration locally."""
    try:
        CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        # Protect config file permissions
        try:
            os.chmod(CONFIG_FILE_PATH, 0o600)
        except Exception:
            pass
    except Exception as e:
        logging.error(f"[Node Agent] Failed to save config file: {e}")

def generate_keypair() -> Tuple[str, str]:
    """Generates an Ed25519 keypair and returns (public_key_hex, private_key_hex)."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_hex = private_key.private_bytes_raw().hex()
    public_hex = private_key.public_key().public_bytes_raw().hex()
    return public_hex, private_hex

async def register_with_master(master_url: str, join_code: str) -> bool:
    """
    Registers this node with the Master Server using a temporary Join Code.
    Generates keys locally and uploads the Public Key.
    """
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(master_url)
        master_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    except Exception as parse_err:
        logging.warning(f"[Node Agent] Failed to parse master URL: {parse_err}")

    logging.info(f"[Node Agent] Registering with Master at {master_url}...")
    
    # Generate keys
    pub_hex, priv_hex = generate_keypair()
    
    payload = {
        "join_code": join_code,
        "public_key": pub_hex
    }
    
    register_endpoint = f"{master_url.rstrip('/')}/api/nodes/register"
    
    try:
        # Сначала пробуем безопасное подключение с проверкой SSL
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=True) as client:
                response = await client.post(register_endpoint, json=payload)
        except Exception as ssl_err:
            logging.warning(f"[Node Agent] SSL verification failed ({ssl_err}). Retrying without SSL validation...")
            async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
                response = await client.post(register_endpoint, json=payload)

        if response.status_code != 200:
            logging.error(f"[Node Agent] Registration failed with status {response.status_code}")
            return False
                
        data = response.json()
        
        # Save configuration
        config = {
            "node_id": data["node_id"],
            "node_api_token": data["node_api_token"],
            "master_url": master_url,
            "master_public_key": data["master_public_key"],
            "private_key": priv_hex,
            "public_key": pub_hex
        }
        save_node_config(config)
        logging.info(f"[Node Agent] Successfully registered! Saved Node ID: {data['node_id']}")
        return True
    except Exception as e:
        logging.error(f"[Node Agent] Exception during registration: {e}")
        return False

def sign_payload(payload_dict: dict, private_key_hex: str) -> str:
    """Signs a payload dictionary using the node's Ed25519 private key."""
    # We remove any existing signature first to ensure determinism
    data = payload_dict.copy()
    data.pop("signature", None)
    
    # Serialize to stable JSON format
    message_str = json.dumps(data, sort_keys=True)
    message_bytes = message_str.encode("utf-8")
    
    # Load private key and sign
    priv_bytes = bytes.fromhex(private_key_hex)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
    
    signature = private_key.sign(message_bytes)
    return signature.hex()

async def send_report_to_master(action: str, client_email: str, 
                                 tunnel_email: str = "", details: str = "") -> bool:
    """Sends a cryptographically signed report to the Master Server."""
    config = load_node_config()
    if not config:
        logging.error("[Node Agent] Cannot send report: Node is not registered.")
        return False
        
    incident_id = f"inc-{int(time.time())}-{secrets_hex(3)}"
    
    payload = {
        "incident_id": incident_id,
        "action": action,
        "client_email": client_email,
        "tunnel_email": tunnel_email,
        "details": details
    }
    
    # Sign the payload
    payload["signature"] = sign_payload(payload, config["private_key"])
    
    report_endpoint = f"{config['master_url'].rstrip('/')}/api/nodes/report"
    headers = {
        "X-Node-ID": config["node_id"],
        "Authorization": f"Bearer {config['node_api_token']}",
        "Content-Type": "application/json"
    }
    
    try:
        # Сначала пробуем безопасное подключение с проверкой SSL
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
                response = await client.post(report_endpoint, json=payload, headers=headers)
        except Exception as ssl_err:
            logging.warning(f"[Node Agent] SSL verification failed for report ({ssl_err}). Retrying without SSL validation...")
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                response = await client.post(report_endpoint, json=payload, headers=headers)

        if response.status_code == 200:
            logging.info(f"[Node Agent] Report sent successfully for incident {incident_id}")
            return True
        else:
            logging.error(f"[Node Agent] Master rejected report with status {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"[Node Agent] Exception sending report: {e}")
        return False

def secrets_hex(nbytes: int) -> str:
    import secrets
    return secrets.token_hex(nbytes)

async def auto_investigate_and_resolve(dst_ip: Optional[str], dst_port: int) -> Optional[str]:
    """
    Edge Node investigation:
    1. Look up the logs of Xray/Hysteria on this node to find which client email connected to dst_ip:dst_port.
    2. Disable/block the client email locally.
    3. Send a signed report to the Master to request unbanning this Edge Node.
    """
    logging.info(f"[Node Agent] Running auto-investigation for connection {dst_ip}:{dst_port}...")
    
    # Import log parsers from panel's security router
    from backend.routes.security import find_email_in_hysteria_log, find_email_in_xray_log
    
    email = None
    
    # Try finding in Hysteria 2 log first
    try:
        email = find_email_in_hysteria_log(dst_ip, dst_port)
    except Exception as e:
        logging.error(f"[Node Agent] Error reading Hysteria log: {e}")
        
    # If not found, try Xray log
    if not email:
        try:
            email = find_email_in_xray_log(None, dst_ip, dst_port)
        except Exception as e:
            logging.error(f"[Node Agent] Error reading Xray log: {e}")
            
    if not email:
        logging.warning(f"[Node Agent] Investigation failed: No client found for {dst_ip}:{dst_port}")
        return None
        
    logging.info(f"[Node Agent] Identified culprit client: {email}. Initiating local block...")
    
    # Block the client locally in this panel instance database
    try:
        from backend.database import db_session
        from backend.database.crud.clients import block_client_db
        from backend.models import ClientStats
        
        inbound_id = None
        with db_session() as session:
            client = session.query(ClientStats).filter_by(email=email).first()
            if not client:
                logging.error(f"[Node Agent] Client {email} not found in database for blocking.")
                return None
            inbound_id = client.inbound_id
            
        # Block in DB
        block_client_db(inbound_id, email, reason="Auto-ban: Distributed IPS detection")
        
        # Report the ban back to Master
        success = await send_report_to_master(
            action="client_banned",
            client_email=email,
            details=f"Auto-resolved from Edge Node for destination {dst_ip}:{dst_port}"
        )
        
        if success:
            logging.info(f"[Node Agent] Successfully reported resolution for client {email} to Master.")
        else:
            logging.error(f"[Node Agent] Failed to report resolution for client {email} to Master.")
            
        return email
    except Exception as e:
        logging.error(f"[Node Agent] Failed to block client locally or report: {e}")
        return None
