import logging
import httpx

_server_public_ip = None

async def get_geoip_info(ip: str) -> str:
    """Gets country, city, and ISP geolocation info for an IP address."""
    if not ip or ip == "unknown" or ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172.16."):
        return "Локальная сеть"
        
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"http://ip-api.com/json/{ip}")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    country = data.get("country", "")
                    city = data.get("city", "")
                    org = data.get("org", "")
                    geo_parts = []
                    if country:
                        geo_parts.append(country)
                    if city:
                        geo_parts.append(city)
                    if org:
                        geo_parts.append(f"ISP: {org}")
                    return " - ".join(geo_parts) if geo_parts else "Определено"
    except Exception as e:
        logging.warning(f"[GeoIP] Не удалось получить данные для {ip}: {e}")
    return "Неизвестно"

async def get_server_ip():
    """Gets the public IP of the host server."""
    global _server_public_ip
    if _server_public_ip:
        return _server_public_ip
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get("https://api.ipify.org")
            if res.status_code == 200:
                _server_public_ip = res.text.strip()
                return _server_public_ip
    except Exception:
        pass
    return "127.0.0.1"
