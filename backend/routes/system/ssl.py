from fastapi import APIRouter, Request

from backend.database import set_setting
import backend.routes.system
from backend.i18n import t, get_lang

router = APIRouter()

@router.post("/api/ssl/generate")
async def generate_ssl_api(request: Request):
    if not backend.routes.system.check_auth(request):
        return backend.routes.system.decoy_response()
    lang = get_lang(request)
    try:
        data = await request.json()
        domain = data.get("domain", "").strip()
        email = data.get("email", "").strip()
        if not domain:
            return {"success": False, "msg": t("ssl_domain_required", lang=lang, category="backend")}
        
        from backend.ssl_utils import request_ssl_cert
        success, msg = request_ssl_cert(domain, email)
        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        if success:
            set_setting("ssl_domain", domain)
            set_setting("ssl_email", email)
            log_action(actor, "generate_ssl", target=domain, details=f"email:{email}, status:success")
            
            # Restart the panel server to load the new SSL certificate.
            # Since the Docker container has 'restart: always', it will start up immediately with the new cert.
            import threading
            import time
            import os
            import sys
            import logging
            def auto_restart():
                if "pytest" in sys.modules:
                    return
                time.sleep(1.5)
                try:
                    logging.info("[SSL] Exiting panel process to trigger Docker container restart and load new SSL certificates...")
                except Exception:
                    pass
                os._exit(0)
            
            threading.Thread(target=auto_restart).start()
            return {"success": True, "msg": msg}
        else:
            log_action(actor, "generate_ssl", target=domain, details=f"email:{email}, status:failed, error:{msg}")
            return {"success": False, "msg": msg}
    except Exception as e:
        try:
            from backend.audit import log_action, get_actor_username
            actor = get_actor_username(request)
            log_action(actor, "generate_ssl", target=data.get("domain", "unknown"), details=f"status:error, error:{str(e)}")
        except Exception:
            pass
        return {"success": False, "msg": t("ssl_generate_error", lang=lang, category="backend", error=str(e))}
