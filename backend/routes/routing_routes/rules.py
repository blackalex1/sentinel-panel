from fastapi import APIRouter, Request
from backend.database import (
    get_all_routing_rules, get_routing_rule_by_id, add_routing_rule,
    update_routing_rule, delete_routing_rule, update_rules_priority
)
from backend.auth_utils import check_auth, decoy_response
from backend.audit import log_action, get_actor_username
from backend.utils.service_restart import restart_services_background

router = APIRouter()

@router.get("/api/routing/rules")
async def list_rules_api(request: Request):
    """Lists all configured routing rules."""
    if not check_auth(request):
        return decoy_response()
    return {"success": True, "obj": get_all_routing_rules()}

@router.post("/api/routing/rules/create")
async def create_rule_api(request: Request, payload: dict):
    """Creates a new routing rule."""
    if not check_auth(request):
        return decoy_response()
        
    remark = payload.get("remark", "").strip()
    outbound_tag = payload.get("outbound_tag", "").strip()
    inbound_tags = payload.get("inbound_tags", [])
    users = payload.get("users", [])
    domains = payload.get("domains", [])
    ips = payload.get("ips", [])
    protocols = payload.get("protocols", [])
    enable = int(payload.get("enable", 1))
    
    if not outbound_tag:
        return {"success": False, "msg": "Тег назначения (Outbound Tag) обязателен"}
        
    if not inbound_tags and not users and not domains and not ips and not protocols:
        return {"success": False, "msg": "Необходимо указать хотя бы одно условие (домены, IP, протоколы, пользователи или входящие теги)"}
        
    rule_id = add_routing_rule(remark, outbound_tag, inbound_tags, users, domains, ips, protocols, enable)

    restart_services_background()

    actor = get_actor_username(request)
    log_action(actor, "create_routing_rule", target=remark or f"rule-{rule_id}", details=f"outbound:{outbound_tag}")
    
    return {"success": True, "id": rule_id}

@router.post("/api/routing/rules/update/{id}")
async def update_rule_api(request: Request, id: int, payload: dict):
    """Updates an existing routing rule by ID."""
    if not check_auth(request):
        return decoy_response()
        
    remark = payload.get("remark", "").strip()
    outbound_tag = payload.get("outbound_tag", "").strip()
    inbound_tags = payload.get("inbound_tags", [])
    users = payload.get("users", [])
    domains = payload.get("domains", [])
    ips = payload.get("ips", [])
    protocols = payload.get("protocols", [])
    enable = int(payload.get("enable", 1))
    sort_order = payload.get("sort_order")
    
    if not outbound_tag:
        return {"success": False, "msg": "Тег назначения (Outbound Tag) обязателен"}
        
    if not inbound_tags and not users and not domains and not ips and not protocols:
        return {"success": False, "msg": "Необходимо указать хотя бы одно условие"}
        
    success = update_routing_rule(id, remark, outbound_tag, inbound_tags, users, domains, ips, protocols, enable, sort_order)
    if not success:
        return {"success": False, "msg": "Правило маршрутизации не найдено"}

    # Синхронизируем настройки быстрых правил, если редактировалось одно из них
    try:
        from backend.database.crud.routing import QUICK_SECURITY_RULES_SPECS, find_quick_rule
        from backend.database import set_setting, db_session
        with db_session() as session:
            for key, spec in QUICK_SECURITY_RULES_SPECS.items():
                q_rule = find_quick_rule(session, key)
                if q_rule and q_rule.id == id:
                    set_setting(key, "true" if enable == 1 else "false")
                    set_setting(f"{key}_outbound", outbound_tag)
                    break
    except Exception:
        pass
        
    restart_services_background()

    actor = get_actor_username(request)
    log_action(actor, "update_routing_rule", target=remark or f"rule-{id}", details=f"outbound:{outbound_tag}, enable:{enable}")
    
    return {"success": True}

@router.post("/api/routing/rules/delete/{id}")
async def delete_rule_api(request: Request, id: int):
    """Deletes a routing rule by ID."""
    if not check_auth(request):
        return decoy_response()
        
    rule = get_routing_rule_by_id(id)
    if not rule:
        return {"success": False, "msg": "Правило маршрутизации не найдено"}
        
    if "api" in rule.get("inbound_tags", []) and rule.get("outbound_tag") == "api":
         return {"success": False, "msg": "Нельзя удалять системное правило трафика API"}
         
    success = delete_routing_rule(id)
    if not success:
        return {"success": False, "msg": "Не удалось удалить правило маршрутизации"}

    restart_services_background()

    actor = get_actor_username(request)
    log_action(actor, "delete_routing_rule", target=rule.get("remark") or f"rule-{id}")
    
    return {"success": True}

@router.post("/api/routing/rules/sort")
async def sort_rules_api(request: Request, payload: dict):
    """Updates sorting orders priorities for routing rules."""
    if not check_auth(request):
        return decoy_response()
        
    rule_ids = payload.get("rule_ids", [])
    if not rule_ids:
        return {"success": False, "msg": "Список ID правил пуст"}
        
    success = update_rules_priority(rule_ids)

    restart_services_background()

    actor = get_actor_username(request)
    log_action(actor, "sort_routing_rules", details=f"order:{rule_ids}")
    
    return {"success": True}

@router.get("/api/routing/rules/export")
async def export_rules_preset_api(request: Request):
    """Exports all configured routing rules as a JSON preset file."""
    if not check_auth(request):
        return decoy_response()

    rules = get_all_routing_rules()
    export_data = {
        "version": 1,
        "generator": "Sentinel-Panel",
        "description": "Routing Rules Preset Template",
        "rules": rules
    }

    actor = get_actor_username(request)
    log_action(actor, "export_routing_rules_preset", details=f"count:{len(rules)}")

    return {"success": True, "preset": export_data}

@router.post("/api/routing/rules/import")
async def import_rules_preset_api(request: Request, payload: dict):
    """Imports routing rules from a JSON preset payload with validation and sanitization."""
    if not check_auth(request):
        return decoy_response()

    mode = payload.get("mode", "append")  # "append" or "overwrite"
    preset_data = payload.get("preset", {})
    if isinstance(preset_data, str):
        try:
            preset_data = json.loads(preset_data)
        except Exception:
            return {"success": False, "msg": "Невалидный формат JSON пресета"}

    rules = preset_data.get("rules") if isinstance(preset_data, dict) else None
    if not isinstance(rules, list) or not rules:
        return {"success": False, "msg": "Файл пресета не содержит списка правил"}

    if mode == "overwrite":
        all_existing = get_all_routing_rules()
        for r in all_existing:
            # Do not delete system API rule
            if "api" in r.get("inbound_tags", []) and r.get("outbound_tag") == "api":
                continue
            delete_routing_rule(r["id"])

    imported_count = 0
    for r in rules:
        if not isinstance(r, dict):
            continue
        remark = str(r.get("remark") or "").strip()
        outbound_tag = str(r.get("outbound_tag") or "").strip()
        inbound_tags = r.get("inbound_tags") if isinstance(r.get("inbound_tags"), list) else []
        users = r.get("users") if isinstance(r.get("users"), list) else []
        domains = r.get("domains") if isinstance(r.get("domains"), list) else []
        ips = r.get("ips") if isinstance(r.get("ips"), list) else []
        protocols = r.get("protocols") if isinstance(r.get("protocols"), list) else []
        enable = int(r.get("enable", 1))

        if not outbound_tag:
            continue

        add_routing_rule(
            remark=remark or "Imported Rule",
            outbound_tag=outbound_tag,
            inbound_tags=inbound_tags,
            users=users,
            domains=domains,
            ips=ips,
            protocols=protocols,
            enable=enable
        )
        imported_count += 1

    restart_services_background()

    actor = get_actor_username(request)
    log_action(actor, "import_routing_rules_preset", details=f"mode:{mode}, count:{imported_count}")

    return {"success": True, "imported": imported_count, "msg": f"Успешно импортировано правил: {imported_count}"}

