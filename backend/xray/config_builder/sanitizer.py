def clean_stream_settings(stream_settings: dict) -> dict:
    """Удаляет устаревшие параметры (например, allowInsecure) из streamSettings для совместимости с новыми версиями Xray"""
    if not isinstance(stream_settings, dict):
        return stream_settings
    
    # Очищаем tlsSettings
    if "tlsSettings" in stream_settings and isinstance(stream_settings["tlsSettings"], dict):
        if "allowInsecure" in stream_settings["tlsSettings"]:
            del stream_settings["tlsSettings"]["allowInsecure"]
            
    # Очищаем realitySettings
    if "realitySettings" in stream_settings and isinstance(stream_settings["realitySettings"], dict):
        reality_opts = stream_settings["realitySettings"]
        if "allowInsecure" in reality_opts:
            del reality_opts["allowInsecure"]
        if "fingerprint" in reality_opts and reality_opts["fingerprint"] in ("randomized", "random"):
            del reality_opts["fingerprint"]
        for key in ["maxTimeDiff", "max_time_difference"]:
            if key in reality_opts:
                val = reality_opts[key]
                is_valid = False
                if isinstance(val, str):
                    try:
                        clean_val = val.lower().rstrip("s").strip()
                        int_val = int(clean_val)
                        if int_val > 0:
                            reality_opts[key] = int_val
                            is_valid = True
                    except ValueError:
                        pass
                elif isinstance(val, (int, float)):
                    if int(val) > 0:
                        reality_opts[key] = int(val)
                        is_valid = True
                
                if not is_valid:
                    del reality_opts[key]
            
    # Преобразуем obfs в udpmasks для Hysteria / Hysteria 2 в Xray-core
    if stream_settings.get("network") == "hysteria" or "hysteriaSettings" in stream_settings:
        hyst_settings = stream_settings.get("hysteriaSettings")
        if isinstance(hyst_settings, dict):
            obfs_type = hyst_settings.get("obfs") or hyst_settings.get("obfs_type")
            obfs_pwd = hyst_settings.get("obfsPassword") or hyst_settings.get("obfs_password")
            
            # Удаляем устаревшие/нестандартные поля из hysteriaSettings
            for key in ["obfs", "obfs_type", "obfsPassword", "obfs_password"]:
                if key in hyst_settings:
                    del hyst_settings[key]
            
            if obfs_type:
                stream_settings["finalmask"] = {
                    "udp": [
                        {
                            "type": obfs_type,
                            "settings": {
                                "password": obfs_pwd or ""
                            }
                        }
                    ]
                }
            
    return stream_settings
