from fastapi import APIRouter, Request
from urllib.parse import urlparse

from backend.xray import get_geo_files_info, download_geo_files, restart_xray
from backend.i18n import t, get_lang

router = APIRouter()

@router.get("/api/xray/geo")
async def get_geo_info(request: Request):
    """Возвращает информацию об установленных geo-файлах и текущих URL источников."""
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    try:
        info = get_geo_files_info()
        return {"success": True, "obj": info}
    except Exception as e:
        return {"success": False, "msg": str(e)}

@router.post("/api/xray/geo/settings")
async def save_geo_settings(request: Request, payload: dict):
    """Сохраняет кастомные URL для geoip.dat и geosite.dat."""
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    lang = get_lang(request)
    try:
        from backend.database import set_setting

        geoip_url = payload.get("geoip_url", "").strip()
        geosite_url = payload.get("geosite_url", "").strip()

        for label, url in (("geoip_url", geoip_url), ("geosite_url", geosite_url)):
            if url:
                parsed = urlparse(url)
                if parsed.scheme not in ("https", "http"):
                    return {"success": False, "msg": t("xray_geo_protocol_invalid", lang=lang, category="backend", label=label)}
                if not url.lower().endswith(".dat"):
                    return {"success": False, "msg": t("xray_geo_must_point_to_dat", lang=lang, category="backend", label=label)}

        # Сохраняем (пустая строка = вернуться к дефолтному URL)
        set_setting("geo_geoip_url", geoip_url)
        set_setting("geo_geosite_url", geosite_url)

        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "update_geo_settings",
                   details=f"geoip_url:{geoip_url or 'default'}, geosite_url:{geosite_url or 'default'}")

        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": str(e)}

@router.post("/api/xray/geo/update")
async def update_geo_files(request: Request):
    """Скачивает/обновляет geoip.dat и geosite.dat по настроенным URL."""
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    lang = get_lang(request)
    try:
        result = download_geo_files()

        from backend.audit import log_action, get_actor_username
        actor = get_actor_username(request)
        log_action(actor, "update_geo_files",
                   details=f"geoip:{result['geoip']}, geosite:{result['geosite']}")

        if result["geoip"] or result["geosite"]:
            # Перезапускаем Xray чтобы применить новые geo-файлы
            restart_xray()

        msg_parts = []
        if result["geoip"]:
            msg_parts.append(t("xray_geo_geoip_updated", lang=lang, category="backend"))
        if result["geosite"]:
            msg_parts.append(t("xray_geo_geosite_updated", lang=lang, category="backend"))
        if result["errors"]:
            msg_parts.extend(result["errors"])

        success = result["geoip"] and result["geosite"]
        return {
            "success": success,
            "partial": result["geoip"] or result["geosite"],
            "msg": "; ".join(msg_parts) if msg_parts else t("xray_geo_update_error", lang=lang, category="backend"),
            "info": get_geo_files_info()
        }
    except Exception as e:
        return {"success": False, "msg": str(e)}
