import secrets
import time
import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Request, HTTPException

from backend.database import db_session
from backend.models import Node, NodeJoinCode

router = APIRouter()

class JoinCodeResponse(BaseModel):
    code: str
    expires_at: int
    master_url: Optional[str] = None

class NodeOut(BaseModel):
    id: str
    name: str
    public_key: Optional[str]
    status: str
    registered_at: int

@router.post("/api/nodes/join-code", response_model=JoinCodeResponse)
async def generate_join_code(request: Request):
    import backend.routes.nodes as nodes_facade
    if not nodes_facade.check_auth(request):
        return nodes_facade.decoy_response()
        
    code = f"JOIN-{secrets.token_hex(4).upper()}"
    created_at = int(time.time())
    expires_at = created_at + 3600  # Valid for 1 hour
    
    from backend.database import get_setting
    ssl_domain = get_setting("ssl_domain", "").strip()
    master_url = None
    if ssl_domain:
        port = settings.PANEL_PORT
        secret = settings.PANEL_SECRET_PATH
        if port == 443:
            master_url = f"https://{ssl_domain}/{secret}"
        else:
            master_url = f"https://{ssl_domain}:{port}/{secret}"
            
    try:
        with db_session() as session:
            join_code_entry = NodeJoinCode(
                code=code,
                expires_at=expires_at,
                created_at=created_at
            )
            session.add(join_code_entry)
        return JoinCodeResponse(code=code, expires_at=expires_at, master_url=master_url)
    except Exception as e:
        logging.error(f"[Nodes API] Failed to generate join code: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/api/nodes", response_model=List[NodeOut])
async def list_nodes(request: Request):
    import backend.routes.nodes as nodes_facade
    if not nodes_facade.check_auth(request):
        return nodes_facade.decoy_response()
        
    try:
        with db_session() as session:
            nodes = session.query(Node).all()
            return [
                NodeOut(
                    id=n.id,
                    name=n.name,
                    public_key=n.public_key,
                    status=n.status,
                    registered_at=n.registered_at
                ) for n in nodes
            ]
    except Exception as e:
        logging.error(f"[Nodes API] Failed to list nodes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/api/nodes/{node_id}")
async def revoke_node(request: Request, node_id: str):
    import backend.routes.nodes as nodes_facade
    if not nodes_facade.check_auth(request):
        return nodes_facade.decoy_response()
        
    try:
        with db_session() as session:
            node = session.query(Node).filter_by(id=node_id).first()
            if not node:
                raise HTTPException(status_code=404, detail="Node not found")
            session.delete(node)
        return {"status": "success", "message": f"Node {node_id} successfully revoked."}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[Nodes API] Failed to revoke node: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
