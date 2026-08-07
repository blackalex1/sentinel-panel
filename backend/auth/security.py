import socket
import ipaddress
from urllib.parse import urlparse

def is_safe_url(url: str) -> bool:
    """Проверяет URL на безопасность от SSRF-атак"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        
        # Разрешаем имя хоста во все IP адреса
        try:
            ips = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # Если имя не разрешается в DNS контексте, считаем хост не подтвержденным (deny по умолчанию для защиты от SSRF)
            return False
            
        for family, _, _, _, sockaddr in ips:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_loopback or ip.is_private or ip.is_multicast or ip.is_link_local or ip.is_unspecified:
                return False
        return True
    except Exception:
        return False
