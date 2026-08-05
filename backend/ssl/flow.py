import logging
from typing import Tuple, Optional
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from backend.ssl.acme_client import AcmeClient
from backend.ssl.challenge_server import TemporaryAcmeServer, ACME_CHALLENGES

def run_acme_flow(domain: str, email: str, use_staging: bool = False) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """Runs full Let's Encrypt HTTP-01 flow and returns (success, message, cert_pem, key_pem)."""
    
    # Start temporary HTTP server on port 80 to answer challenge
    temp_server = TemporaryAcmeServer(port=80)
    temp_server.start()
    
    try:
        client = AcmeClient(use_staging=use_staging)
        
        if not client.fetch_directory():
            return False, "Failed to connect to ACME server directory", None, None
            
        if not client.register_account(email):
            return False, "Failed to register Let's Encrypt account", None, None
            
        # Create order
        order_url, auths, finalize_url = client.create_order(domain)
        if not order_url or not auths or not finalize_url:
            return False, "Failed to create Let's Encrypt order", None, None
            
        auth_url = auths[0]
        token, chal_url, auth_status = client.get_challenge_details(auth_url)
        if not token or not chal_url:
            return False, "Failed to fetch HTTP-01 challenge token", None, None
            
        if auth_status == "valid":
            logging.info("[ACME Client] Domain already authorized.")
        else:
            # Generate Key Authorization
            key_authorization = f"{token}.{client.thumbprint}"
            
            # Publish challenge token for FastAPI router to serve
            ACME_CHALLENGES[token] = key_authorization
            logging.info(f"[ACME Client] Published challenge authorization for token: {token}")
            
            # Trigger validation
            if not client.trigger_challenge(chal_url):
                ACME_CHALLENGES.pop(token, None)
                return False, "Failed to trigger ACME challenge validation", None, None
                
            # Poll authorization status
            success = client.poll_authorization(auth_url)
            ACME_CHALLENGES.pop(token, None)
            if not success:
                return False, "ACME domain authorization validation failed (Let's Encrypt was unable to reach /.well-known/acme-challenge/ over port 80)", None, None
                
        # Finalize certificate
        domain_key = ec.generate_private_key(ec.SECP256R1())
        cert_url = client.finalize_order(finalize_url, domain, domain_key)
        if not cert_url:
            return False, "Failed to finalize certificate order", None, None
            
        # Download PEM certificate chain
        status, res_json, _ = client._sign_and_post(cert_url, None)
        if status != 200:
            return False, "Failed to download certificate chain from ACME", None, None
            
        cert_pem = res_json.get("raw")
        key_pem = domain_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        return True, "Certificate issued successfully!", cert_pem, key_pem
    finally:
        temp_server.stop()
