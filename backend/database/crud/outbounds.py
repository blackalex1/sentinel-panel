import json
from backend.models import Outbound
import backend.database

def outbound_to_dict(ob: Outbound) -> dict:
    if not ob:
        return None
    return {
        "id": ob.id,
        "remark": ob.remark,
        "protocol": ob.protocol,
        "tag": ob.tag,
        "settings": ob.settings,
        "stream_settings": ob.stream_settings,
        "enable": ob.enable,
        "is_system": ob.is_system,
        "up": ob.up or 0,
        "down": ob.down or 0
    }

def get_all_outbounds():
    with backend.database.db_session() as session:
        obs = session.query(Outbound).all()
        return [backend.database.outbound_to_dict(ob) for ob in obs]

def get_outbound_by_id(outbound_id: int):
    with backend.database.db_session() as session:
        ob = session.query(Outbound).filter_by(id=outbound_id).first()
        return backend.database.outbound_to_dict(ob)

def add_outbound(remark: str, protocol: str, tag: str, settings_dict: dict, stream_settings_dict: dict = None, enable: int = 1, is_system: int = 0):
    with backend.database.db_session() as session:
        existing = session.query(Outbound).filter_by(tag=tag).first()
        if existing:
            return None
        ob = Outbound(
            remark=remark,
            protocol=protocol,
            tag=tag,
            settings=json.dumps(settings_dict),
            stream_settings=json.dumps(stream_settings_dict or {}),
            enable=enable,
            is_system=is_system
        )
        session.add(ob)
        session.flush()
        return ob.id

def update_outbound(outbound_id: int, remark: str, protocol: str, tag: str, settings_dict: dict, stream_settings_dict: dict = None, enable: int = 1):
    with backend.database.db_session() as session:
        # Check tag uniqueness among other outbounds
        tag_owner = session.query(Outbound).filter_by(tag=tag).first()
        if tag_owner and tag_owner.id != outbound_id:
            return False
            
        ob = session.query(Outbound).filter_by(id=outbound_id).first()
        if not ob:
            return False
            
        ob.remark = remark
        ob.protocol = protocol
        ob.tag = tag
        ob.settings = json.dumps(settings_dict)
        ob.stream_settings = json.dumps(stream_settings_dict or {})
        ob.enable = enable
        return True

def delete_outbound(outbound_id: int):
    with backend.database.db_session() as session:
        ob = session.query(Outbound).filter_by(id=outbound_id).first()
        if not ob or ob.is_system == 1:
            return False
        
        ob_tag = ob.tag
        from backend.models import RoutingRule
        session.query(RoutingRule).filter_by(outbound_tag=ob_tag).delete(synchronize_session=False)

        # Clean up backup_outbounds references in other outbounds
        all_obs = session.query(Outbound).all()
        for other_ob in all_obs:
            if other_ob.id == outbound_id:
                continue
            try:
                s_dict = json.loads(other_ob.settings or "{}")
                backups = s_dict.get("backup_outbounds")
                if isinstance(backups, list) and ob_tag in backups:
                    s_dict["backup_outbounds"] = [b for b in backups if b != ob_tag]
                    other_ob.settings = json.dumps(s_dict)
            except Exception:
                pass

        session.delete(ob)
        return True

def update_outbound_traffic(tag: str, up_add: int, down_add: int):
    with backend.database.db_session() as session:
        ob = session.query(Outbound).filter_by(tag=tag).first()
        if ob:
            ob.up = (ob.up or 0) + up_add
            ob.down = (ob.down or 0) + down_add

