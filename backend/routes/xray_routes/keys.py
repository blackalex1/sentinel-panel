from fastapi import APIRouter, Request
from backend.sentinel_core_bridge import generate_x25519_keypair, generate_vlessenc_keypair
from backend.i18n import t, get_lang

router = APIRouter()

@router.get("/api/xray/x25519")
async def generate_x25519_keys(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    lang = get_lang(request)
    try:
        kp = generate_x25519_keypair()
        if kp.get("privateKey") and kp.get("publicKey"):
            return {"success": True, "privateKey": kp["privateKey"], "publicKey": kp["publicKey"]}
        return {"success": False, "msg": t("xray_keys_generate_failed", lang=lang, category="backend")}
    except Exception as e:
        return {"success": False, "msg": t("xray_keys_error", lang=lang, category="backend", error=str(e))}

@router.get("/api/xray/vlessenc")
async def generate_vlessenc_keys(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    lang = get_lang(request)
    try:
        res = generate_vlessenc_keypair()
        if res.get("success") is True:
            return res
        return {"success": False, "msg": t("xray_keys_vlessenc_generate_failed", lang=lang, category="backend")}
    except Exception as e:
        return {"success": False, "msg": t("xray_keys_error", lang=lang, category="backend", error=str(e))}
