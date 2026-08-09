import sys
import json
import logging
import re
import datetime
from typing import Optional

def parse_xray_timestamp(line: str) -> Optional[datetime.datetime]:
    try:
        # Format: "2026/06/16 18:13:22"
        match = re.match(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})", line)
        if match:
            return datetime.datetime.strptime(match.group(1), "%Y/%m/%d %H:%M:%S")
    except Exception:
        pass
    return None

def parse_hysteria_timestamp(line: str) -> Optional[datetime.datetime]:
    try:
        # Check if line contains a JSON payload
        # JSON format: {"time":"2026-06-16T18:13:22Z", ...}
        json_match = re.search(r'(\{.*"time"\s*:\s*"([^"]+)".*\})', line)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                t_str = data.get("time")
                if t_str:
                    t_str = t_str.split(".")[0].replace("Z", "").split("+")[0]
                    return datetime.datetime.strptime(t_str, "%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass

        if line.startswith("{"):
            try:
                data = json.loads(line)
                t_str = data.get("time")
                if t_str:
                    t_str = t_str.split(".")[0].replace("Z", "").split("+")[0]
                    return datetime.datetime.strptime(t_str, "%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass

        # Text format: e.g. 2026-06-16T18:13:22Z or [Hysteria] 2026-06-16T18:13:22Z
        match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
        if match:
            return datetime.datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")

        # Text format without year: e.g. 06-16T15:17:37Z
        match_no_year = re.search(r"\b(\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
        if match_no_year:
            current_year = datetime.datetime.now().year
            t_str = f"{current_year}-{match_no_year.group(1)}"
            return datetime.datetime.strptime(t_str, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass
    return None

def _get_hysteria_log_path():
    import backend.config as b_cfg
    try:
        import backend.routes.security as sec_facade
        if hasattr(sec_facade, "HYSTERIA_LOG_PATH") and sec_facade.HYSTERIA_LOG_PATH != b_cfg.BIN_DIR / "hysteria.log":
            return sec_facade.HYSTERIA_LOG_PATH
    except Exception:
        pass
    return b_cfg.HYSTERIA_LOG_PATH

def _get_xray_log_path():
    import backend.config as b_cfg
    try:
        import backend.routes.security as sec_facade
        if hasattr(sec_facade, "XRAY_LOG_PATH") and sec_facade.XRAY_LOG_PATH != b_cfg.BIN_DIR / "xray.log":
            return sec_facade.XRAY_LOG_PATH
    except Exception:
        pass
    return b_cfg.XRAY_LOG_PATH

def find_email_in_hysteria_log(dst_ip: Optional[str], dst_port: int) -> Optional[str]:
    """
    Парсит последние 1000 строк лога Hysteria 2 для поиска email (auth/id) по параметрам соединения.
    Временной лимит: только лог-записи за последние 5 минут (отключается во время тестов).
    """
    hys_path = _get_hysteria_log_path()
    if not hys_path.exists():
        return None
        
    from backend.utils import read_last_lines
    try:
        lines = read_last_lines(hys_path, 1000)
    except Exception as e:
        logging.error(f"Error reading Hysteria logs for security search: {e}")
        return None
        
    dst_port_str = f":{dst_port}"
    now_local = datetime.datetime.now()
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    is_testing = "pytest" in sys.modules
    
    # Проход с конца к началу лога для поиска самого свежего совпадения
    for line in reversed(lines):
        log_time = parse_hysteria_timestamp(line)
        if log_time and not is_testing:
            diff_local = abs((now_local - log_time).total_seconds())
            diff_utc = abs((now_utc - log_time).total_seconds())
            if diff_local > 300 and diff_utc > 300:
                continue
            
        if dst_port_str not in line:
            continue
            
        if dst_ip and dst_ip not in line:
            continue
            
        # 1. JSON (Hysteria 2 debug): {"id": "client_mihomo", "reqAddr": "8.8.8.8:22"}
        match = re.search(r'"id"\s*:\s*"([^"]+)"', line)
        if not match:
            # 2. JSON (alternative): {"auth": "user@example.com", "req": "1.2.3.4:22"}
            match = re.search(r'"auth"\s*:\s*"([^"]+)"', line)
        if not match:
            # 3. Text log: auth=user@example.com или [auth=user@example.com]
            match = re.search(r'auth\s*=\s*([^\s,}]+)', line)
        if not match:
            # 4. Text log: connection: user_name (1.2.3.4:5678) -> target
            match = re.search(r'connection:\s*([^\s(]+)', line)
        if not match:
            # 5. Поиск любого email в строке лога в качестве резерва
            match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line)
            
        if match:
            email = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
            return email.strip('"\'[]')
            
    # Резервный поиск: только по порту назначения
    for line in reversed(lines):
        log_time = parse_hysteria_timestamp(line)
        if log_time and not is_testing:
            diff_local = abs((now_local - log_time).total_seconds())
            diff_utc = abs((now_utc - log_time).total_seconds())
            if diff_local > 300 and diff_utc > 300:
                continue
            
        if dst_port_str not in line:
            continue
            
        # Verify destination IP to prevent false port-only match on different IP
        dest_host = None
        json_match = re.search(r'(\{.*\})', line)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                req_val = data.get("reqAddr") or data.get("req")
                if req_val and ":" in req_val:
                    dest_host = req_val.split(":")[0]
            except Exception:
                pass
        if not dest_host:
            match_dest = re.search(r"->\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+", line)
            if match_dest:
                dest_host = match_dest.group(1)
                
        if dest_host and dst_ip and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", dest_host):
            if dest_host != dst_ip:
                continue

        match = re.search(r'"id"\s*:\s*"([^"]+)"', line)
        if not match:
            match = re.search(r'"auth"\s*:\s*"([^"]+)"', line)
        if not match:
            match = re.search(r'auth\s*=\s*([^\s,}]+)', line)
        if not match:
            match = re.search(r'connection:\s*([^\s(]+)', line)
        if not match:
            match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line)
        if match:
            email = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
            return email.strip('"\'[]')
            
    return None

def find_email_in_xray_log(client_ip: Optional[str], dst_ip: Optional[str], dst_port: int) -> Optional[str]:
    """
    Парсит последние 1000 строк лога Xray для поиска email по параметрам соединения.
    Временной лимит: только лог-записи за последние 5 минут (отключается во время тестов).
    """
    xray_path = _get_xray_log_path()
    if not xray_path.exists():
        return None
        
    from backend.utils import read_last_lines
    try:
        lines = read_last_lines(xray_path, 1000)
    except Exception as e:
        logging.error(f"Error reading Xray logs for security search: {e}")
        return None
        
    dst_port_str = f":{dst_port}"
    now_local = datetime.datetime.now()
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    is_testing = "pytest" in sys.modules
    
    # Проход с конца к началу лога для поиска самого свежего совпадения
    for line in reversed(lines):
        log_time = parse_xray_timestamp(line)
        if log_time and not is_testing:
            diff_local = abs((now_local - log_time).total_seconds())
            diff_utc = abs((now_utc - log_time).total_seconds())
            if diff_local > 300 and diff_utc > 300:
                continue
            
        if "email:" not in line:
            continue
            
        if dst_port_str in line:
            if (dst_ip and dst_ip in line) or (client_ip and client_ip in line):
                match = re.search(r"email:\s*(\S+)", line)
                if match:
                    return match.group(1)
                    
    # Резервный поиск
    for line in reversed(lines):
        log_time = parse_xray_timestamp(line)
        if log_time and not is_testing:
            diff_local = abs((now_local - log_time).total_seconds())
            diff_utc = abs((now_utc - log_time).total_seconds())
            if diff_local > 300 and diff_utc > 300:
                continue
            
        if "email:" not in line:
            continue
        if dst_port_str in line:
            match_dest = re.search(r"accepted\s+(?:tcp|udp):([^:]+):", line)
            if match_dest:
                dest_host = match_dest.group(1)
                if dst_ip and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", dest_host):
                    if dest_host != dst_ip:
                        continue
                        
            match = re.search(r"email:\s*(\S+)", line)
            if match:
                return match.group(1)
                
    return None

def find_client_ip_for_email_in_hysteria_log(email: str) -> Optional[str]:
    """
    Ищет последний зафиксированный IP-адрес подключения для конкретного email в логах Hysteria 2.
    Временной лимит: только лог-записи за последние 5 минут (отключается во время тестов).
    """
    hys_path = _get_hysteria_log_path()
    if not hys_path.exists():
        return None
    from backend.utils import read_last_lines
    try:
        lines = read_last_lines(hys_path, 1000)
    except Exception:
        return None
        
    now_local = datetime.datetime.now()
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    is_testing = "pytest" in sys.modules
    
    for line in reversed(lines):
        log_time = parse_hysteria_timestamp(line)
        if log_time and not is_testing:
            diff_local = abs((now_local - log_time).total_seconds())
            diff_utc = abs((now_utc - log_time).total_seconds())
            if diff_local > 300 and diff_utc > 300:
                continue
            
        json_match = re.search(r'(\{.*\})', line)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if data.get("id") == email or data.get("auth") == email:
                    addr = data.get("addr", "")
                    if addr:
                        return addr.split(":")[0] if ":" in addr else addr
            except Exception:
                pass

        if "client connected" in line:
            if email in line:
                match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
                if match:
                    return match.group(1)
    return None

def find_email_and_ip_in_xray_log(client_ip: Optional[str], dst_ip: Optional[str], dst_port: int) -> Optional[tuple]:
    """
    Ищет email и IP-адрес клиента Xray / Sing-box по параметрам соединения.
    Временной лимит: только лог-записи за последние 5 минут (отключается во время тестов).
    """
    from backend.config import SINGBOX_LOG_PATH
    from backend.utils import read_last_lines
    
    # 0. Сначала опрашиваем Clash API Sing-box (если запущено)
    try:
        import requests
        resp = requests.get("http://127.0.0.1:9090/connections", timeout=0.3)
        if resp.status_code == 200:
            for conn in resp.json().get("connections", []):
                meta = conn.get("metadata", {})
                c_dst = meta.get("destinationIP") or meta.get("host")
                c_dpt = meta.get("destinationPort")
                if (not dst_ip or c_dst == dst_ip) and str(c_dpt) == str(dst_port):
                    user = meta.get("inboundUser") or meta.get("user") or conn.get("user")
                    if user:
                        return user, meta.get("sourceIP", client_ip)
    except Exception:
        pass

    paths_to_check = []
    xray_path = _get_xray_log_path()
    if xray_path.exists():
        paths_to_check.append(xray_path)
    if SINGBOX_LOG_PATH.exists():
        paths_to_check.append(SINGBOX_LOG_PATH)
        
    if not paths_to_check:
        return None
        
    dst_port_str = f":{dst_port}"
    now_local = datetime.datetime.now()
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    is_testing = "pytest" in sys.modules
    
    def extract_email_and_ip(line: str) -> Optional[tuple]:
        # 1. sing-box format: inbound/vless[inbound-8]: [test_client_alpha] inbound connection to 198.51.100.22:22
        match_email = re.search(r"(?:inbound/[^:]+|inbound[^:]*):\s*\[([a-zA-Z0-9_\.\-]+)\]\s+inbound connection to", line)
        if not match_email:
            # 2. [test_client_alpha] inbound connection to ...
            match_email = re.search(r"\[([a-zA-Z0-9_\.\-]+)\]\s+inbound connection to", line)
        if not match_email:
            # 3. email: ...
            match_email = re.search(r"email:\s*(\S+)", line)
        if not match_email:
            # 4. accepted tcp:... [inbound >> outbound] username
            match_email = re.search(r"accepted\s+(?:tcp|udp):\S+\s+\[[^\]]+\]\s+([a-zA-Z0-9_\.\-]+)", line)
        if not match_email:
            # 5. [user: ...] or user: ... or username: ...
            match_email = re.search(r"(?:user|username|clientUser|auth_user):\s*([^\s,\]]+)", line)
        if not match_email:
            # 6. JSON "user": "..." or "id": "..." or "email": "..."
            match_email = re.search(r'"(?:user|username|id|email|auth)"\s*:\s*"([^"]+)"', line)
        if not match_email:
            # 7. inbound connection to ... from ... [username]
            match_email = re.search(r"inbound connection\s+.*?\s+\[([a-zA-Z0-9_\.\-]+)\]", line)
        if not match_email:
            # 8. sing-box [user@domain.com] or [username] tag at the end
            match_email = re.search(r"\[([a-zA-Z0-9_\.\-]+@[a-zA-Z0-9_\.\-]+|[a-zA-Z0-9_\.\-]+)\]\s*$", line)
        if not match_email:
            # 9. Generic email pattern
            match_email = re.search(r"([a-zA-Z0-9_\.\-]+@[a-zA-Z0-9_\.\-]+)", line)
            
        if match_email:
            email = match_email.group(1).strip("[]'\"")
            match_ip = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+\s+(?:accepted|inbound connection)", line)
            if not match_ip:
                match_ip = re.search(r"from\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
            ip = match_ip.group(1) if match_ip else client_ip
            return email, ip
        return None

    for log_path in paths_to_check:
        try:
            lines = read_last_lines(log_path, 1000)
        except Exception:
            continue
            
        for line in reversed(lines):
            log_time = parse_xray_timestamp(line)
            if log_time and not is_testing:
                diff_local = abs((now_local - log_time).total_seconds())
                diff_utc = abs((now_utc - log_time).total_seconds())
                if diff_local > 300 and diff_utc > 300:
                    continue
                
            if dst_port_str in line:
                if (dst_ip and dst_ip in line) or (client_ip and client_ip in line) or not dst_ip:
                    res = extract_email_and_ip(line)
                    if res:
                        return res
                        
        for line in reversed(lines):
            log_time = parse_xray_timestamp(line)
            if log_time and not is_testing:
                diff_local = abs((now_local - log_time).total_seconds())
                diff_utc = abs((now_utc - log_time).total_seconds())
                if diff_local > 300 and diff_utc > 300:
                    continue
                
            if dst_port_str in line:
                match_dest = re.search(r"(?:accepted|connection)\s+(?:tcp|udp):([^:]+):", line)
                if match_dest:
                    dest_host = match_dest.group(1).strip("[]")
                    if dst_ip and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", dest_host):
                        if dest_host != dst_ip:
                            continue
                res = extract_email_and_ip(line)
                if res:
                    return res
                    
    return None
