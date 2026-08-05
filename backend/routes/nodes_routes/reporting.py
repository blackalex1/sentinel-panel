import json
import secrets
import hashlib
import time
import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Request
from cryptography.hazmat.primitives.asymmetric import ed25519

from backend.database import db_session
from backend.models import Node, NodeJoinCode, ClientStats, Inbound

router = APIRouter()

class NodeRegisterRequest(BaseModel):
    join_code: str
    public_key: str  # Hex-encoded Ed25519 public key

class NodeRegisterResponse(BaseModel):
    node_id: str
    node_api_token: str
    master_public_key: str  # Hex-encoded Ed25519 public key of the Master

class NodeReportRequest(BaseModel):
    incident_id: str
    action: str  # e.g., "client_banned", "investigation_result", "investigation_failed"
    client_email: str
    tunnel_email: Optional[str] = None   # email инбаунда/туннеля который был забанен мастером
    details: Optional[str] = ""
    signature: str  # Hex-encoded signature of the JSON body (excluding this field)

@router.post("/api/nodes/register", response_model=NodeRegisterResponse)
async def register_node(request: Request, body: NodeRegisterRequest):
    import backend.routes.nodes as nodes_facade
    now = int(time.time())
    try:
        with db_session() as session:
            join_code = session.query(NodeJoinCode).filter_by(code=body.join_code).first()
            if not join_code or join_code.expires_at < now:
                return nodes_facade.decoy_response()
                
            # Valid join code! Consume it
            session.delete(join_code)
            
            # Generate a Node ID
            node_id = f"node-{secrets.token_hex(4)}"
            node_name = f"Edge Node {node_id[-4:].upper()}"
            
            # Generate Node API Token
            node_token = f"node_sec_{secrets.token_urlsafe(32)}"
            token_hash = hashlib.sha256(node_token.encode("utf-8")).hexdigest()
            
            # Save Node to DB
            new_node = Node(
                id=node_id,
                name=node_name,
                api_token_hash=token_hash,
                public_key=body.public_key,
                status="active",
                registered_at=now
            )
            session.add(new_node)
            
            from backend.database import get_setting, set_setting
            master_pub = get_setting("master_public_key", "")
            master_priv = get_setting("master_private_key", "")
            if not master_pub or not master_priv:
                # Generate keypair
                master_key = ed25519.Ed25519PrivateKey.generate()
                master_pub = master_key.public_key().public_bytes_raw().hex()
                master_priv = master_key.private_bytes_raw().hex()
                set_setting("master_public_key", master_pub)
                set_setting("master_private_key", master_priv)
                
            return NodeRegisterResponse(
                node_id=node_id,
                node_api_token=node_token,
                master_public_key=master_pub
            )
    except Exception as e:
        logging.error(f"[Nodes API] Failed to register node: {e}")
        return nodes_facade.decoy_response()

@router.post("/api/nodes/report")
async def report_incident(request: Request, body: NodeReportRequest):
    import backend.routes.nodes as nodes_facade
    if not nodes_facade.verify_node_token(request):
        return nodes_facade.decoy_response()
        
    node_id = request.headers.get("X-Node-ID")
    
    try:
        with db_session() as session:
            node = session.query(Node).filter_by(id=node_id, status="active").first()
            if not node or not node.public_key:
                return nodes_facade.decoy_response()
                
            try:
                payload_dict = await request.json()
            except Exception:
                payload_dict = body.model_dump()
                
            sig_hex = payload_dict.pop("signature", "")
            
            message_str = json.dumps(payload_dict, sort_keys=True)
            message_bytes = message_str.encode("utf-8")
            
            pub_key_bytes = bytes.fromhex(node.public_key)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_key_bytes)
            
            try:
                pub_key.verify(bytes.fromhex(sig_hex), message_bytes)
            except Exception:
                logging.warning(f"[Nodes API] Cryptographic signature check failed for node {node_id}")
                return nodes_facade.decoy_response()
                
            logging.info(f"[Nodes API] Verified report from node {node_id}: {body.action} for client {body.client_email}")
            
            if body.action == "investigation_result":
                if body.client_email:
                    culprit = session.query(ClientStats).filter_by(email=body.client_email).first()
                    if culprit:
                        culprit.enable = 0
                        culprit.block_reason = f"IPS: resolved by {node_id}"
                        logging.info(f"[Nodes API] Globally banned culprit {body.client_email} on Master (reported by {node_id})")
                
                tunnel_unbanned = False
                if body.tunnel_email:
                    tunnel_clients = session.query(ClientStats).filter_by(email=body.tunnel_email).all()
                    for tc in tunnel_clients:
                        if tc.enable == 0:
                            tc.enable = 1
                            tc.block_reason = None
                            tunnel_unbanned = True
                            inbound = session.query(Inbound).filter_by(id=tc.inbound_id).first()
                            if inbound:
                                try:
                                    ib_settings = json.loads(inbound.settings or "{}")
                                    for sc in ib_settings.get("clients", []):
                                        if sc.get("email") == body.tunnel_email:
                                            sc["enable"] = True
                                            break
                                    inbound.settings = json.dumps(ib_settings)
                                except Exception as e:
                                    logging.error(f"[Nodes API] Error updating inbound settings for tunnel unban: {e}")
                    
                    if tunnel_unbanned:
                        logging.info(f"[Nodes API] Unbanned tunnel {body.tunnel_email} on Master after successful investigation by {node_id}")
                
                session.commit()
                
                try:
                    from backend.xray import restart_xray
                    from backend.hysteria import restart_hysteria
                    restart_xray()
                    restart_hysteria()
                except Exception as e:
                    logging.error(f"[Nodes API] Error restarting cores after investigation report: {e}")
                
                from backend.telegram_alerts import trigger_investigation_result_alert
                trigger_investigation_result_alert(
                    culprit=body.client_email,
                    tunnel=body.tunnel_email or "",
                    node_id=node_id,
                    details=body.details or ""
                )
                
            elif body.action == "investigation_failed":
                logging.warning(f"[Nodes API] Investigation FAILED on node {node_id} for tunnel {body.tunnel_email}")
                
                from backend.telegram_alerts import trigger_investigation_failed_alert
                trigger_investigation_failed_alert(
                    tunnel=body.tunnel_email or "",
                    node_id=node_id,
                    details=body.details or ""
                )
                
            elif body.action == "client_banned":
                client = session.query(ClientStats).filter_by(email=body.client_email).first()
                if client:
                    client.enable = 0
                    client.block_reason = f"Cooperative ban from node {node_id}"
                    inbound = session.query(Inbound).filter_by(id=client.inbound_id).first()
                    if inbound:
                        try:
                            ib_settings = json.loads(inbound.settings or "{}")
                            for sc in ib_settings.get("clients", []):
                                if sc.get("email") == body.client_email:
                                    sc["enable"] = False
                                    break
                            inbound.settings = json.dumps(ib_settings)
                        except Exception as e:
                            logging.error(f"[Nodes API] Error updating inbound settings for client ban: {e}")
                    logging.info(f"[Nodes API] Banned client {body.client_email} on Master after node resolution.")
                    
                if body.tunnel_email:
                    tunnel_clients = session.query(ClientStats).filter_by(email=body.tunnel_email).all()
                    for tc in tunnel_clients:
                        if tc.enable == 0:
                            tc.enable = 1
                            tc.block_reason = None
                            inbound = session.query(Inbound).filter_by(id=tc.inbound_id).first()
                            if inbound:
                                try:
                                    ib_settings = json.loads(inbound.settings or "{}")
                                    for sc in ib_settings.get("clients", []):
                                        if sc.get("email") == body.tunnel_email:
                                            sc["enable"] = True
                                            break
                                    inbound.settings = json.dumps(ib_settings)
                                except Exception as e:
                                    logging.error(f"[Nodes API] Error updating inbound settings for tunnel unban: {e}")
                    
                session.commit()
                
                try:
                    from backend.xray import restart_xray
                    from backend.hysteria import restart_hysteria
                    restart_xray()
                    restart_hysteria()
                except Exception as e:
                    logging.error(f"[Nodes API] Error restarting cores after client_banned report: {e}")
                
            return {"status": "success", "message": "Incident resolution report accepted."}
    except Exception as e:
        logging.error(f"[Nodes API] Error processing node report: {e}")
        return nodes_facade.decoy_response()
