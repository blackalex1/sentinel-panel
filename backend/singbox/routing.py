import json
import logging

def generate_singbox_routing(get_all_routing_rules_fn=None, get_setting_fn=None) -> dict:
    """Сбор правил маршрутизации из БД и настройка rule_set для Sing-box 1.8+ / 1.12+"""
    if get_all_routing_rules_fn is None:
        from backend.database import get_all_routing_rules as get_all_routing_rules_fn
    if get_setting_fn is None:
        from backend.database import get_setting as get_setting_fn

    sb_rules = []
    sb_rule_sets = []
    registered_rule_sets = set()

    def add_singbox_rule_set(prefix: str, code: str) -> str:
        clean_code = code.lower().strip()
        tag = f"{prefix}-{clean_code}"
        if tag not in registered_rule_sets:
            registered_rule_sets.add(tag)
            url = f"https://raw.githubusercontent.com/lyc8503/sing-box-rules/rule-set-{prefix}/{prefix}-{clean_code}.srs"
            sb_rule_sets.append({
                "tag": tag,
                "type": "remote",
                "format": "binary",
                "url": url,
                "download_detour": "direct"
            })
        return tag

    # 1. Быстрая блокировка торрентов
    try:
        b_bit = get_setting_fn("block_bittorrent")
        b_tor = get_setting_fn("block_torrents")
        block_torrents = b_bit if b_bit is not None else b_tor
        if block_torrents and str(block_torrents).lower() in ("true", "1"):
            sb_rules.append({
                "protocol": ["bittorrent"],
                "outbound": "block"
            })
    except Exception as e:
        logging.error(f"Error checking torrent block setting for sing-box: {e}")

    # 2. Быстрая блокировка рекламы
    try:
        b_ads = get_setting_fn("block_ads")
        if b_ads and str(b_ads).lower() in ("true", "1"):
            sb_rules.append({
                "rule_set": [add_singbox_rule_set("geosite", "category-ads-all")],
                "outbound": "block"
            })
    except Exception as e:
        logging.error(f"Error checking ads block setting for sing-box: {e}")

    # 3. Быстрая блокировка по гео
    try:
        b_cn = get_setting_fn("block_cn")
        if b_cn and str(b_cn).lower() in ("true", "1"):
            sb_rules.append({
                "rule_set": [add_singbox_rule_set("geoip", "cn")],
                "outbound": "block"
            })
    except Exception as e:
        logging.error(f"Error checking cn block setting for sing-box: {e}")

    # 4. Пользовательские правила из БД
    try:
        db_rules = get_all_routing_rules_fn()
        for rule in db_rules:
            if not rule.get("enable"):
                continue

            target_outbound = rule.get("outbound_tag")
            if not target_outbound:
                continue

            r_obj = {"outbound": target_outbound}
            rule_sets_needed = []

            # Фильтрация по инбаундам
            inbound_tags = rule.get("inbound_tags")
            if isinstance(inbound_tags, str):
                try:
                    inbound_tags = json.loads(inbound_tags)
                except Exception:
                    inbound_tags = []
            if inbound_tags and isinstance(inbound_tags, list):
                r_obj["inbound"] = [str(t) for t in inbound_tags if t]

            # Фильтрация по пользователям
            users = rule.get("users")
            if isinstance(users, str):
                try:
                    users = json.loads(users)
                except Exception:
                    users = []
            if users and isinstance(users, list):
                r_obj["user"] = [str(u) for u in users if u]

            # Фильтрация по доменам и GeoSite
            domains = rule.get("domains")
            if isinstance(domains, str):
                try:
                    domains = json.loads(domains)
                except Exception:
                    domains = []
            if domains:
                domain_list = []
                suffix_list = []
                regex_list = []
                keyword_list = []

                for d in domains:
                    if not isinstance(d, str) or not d:
                        continue
                    if d.startswith("geosite:"):
                        gs_name = d.replace("geosite:", "").strip().lower()
                        rule_sets_needed.append(add_singbox_rule_set("geosite", gs_name))
                    elif d.startswith("geoip:"):
                        gi_name = d.replace("geoip:", "").strip().lower()
                        if gi_name == "private":
                            r_obj["ip_is_private"] = True
                        else:
                            rule_sets_needed.append(add_singbox_rule_set("geoip", gi_name))
                    elif d.startswith("domain:"):
                        domain_list.append(d.split(":", 1)[1])
                    elif d.startswith("full:"):
                        domain_list.append(d.split(":", 1)[1])
                    elif d.startswith("regexp:"):
                        regex_list.append(d.split(":", 1)[1])
                    elif d.startswith("keyword:"):
                        keyword_list.append(d.split(":", 1)[1])
                    else:
                        suffix_list.append(d)

                if domain_list:
                    r_obj["domain"] = domain_list
                if suffix_list:
                    r_obj["domain_suffix"] = suffix_list
                if regex_list:
                    r_obj["domain_regex"] = regex_list
                if keyword_list:
                    r_obj["domain_keyword"] = keyword_list

            # IP адреса и GeoIP
            ips = rule.get("ips")
            if isinstance(ips, str):
                try:
                    ips = json.loads(ips)
                except Exception:
                    ips = []
            if ips:
                cidr_list = []
                for ip in ips:
                    if not isinstance(ip, str) or not ip:
                        continue
                    if ip.startswith("geoip:"):
                        gi_name = ip.replace("geoip:", "").strip().lower()
                        if gi_name == "private":
                            r_obj["ip_is_private"] = True
                        else:
                            rule_sets_needed.append(add_singbox_rule_set("geoip", gi_name))
                    else:
                        cidr_list.append(ip)

                if cidr_list:
                    r_obj["ip_cidr"] = cidr_list

            if rule_sets_needed:
                r_obj["rule_set"] = rule_sets_needed

            # Протоколы и сети
            protocols = rule.get("protocols")
            if isinstance(protocols, str):
                try:
                    protocols = json.loads(protocols)
                except Exception:
                    protocols = []
            if protocols:
                networks = [p.lower() for p in protocols if isinstance(p, str) and p.lower() in ("tcp", "udp")]
                app_protos = [p for p in protocols if isinstance(p, str) and p.lower() not in ("tcp", "udp", "all")]
                if networks:
                    r_obj["network"] = networks
                if app_protos:
                    r_obj["protocol"] = app_protos

            if len(r_obj) > 1:
                sb_rules.append(r_obj)

    except Exception as e:
        logging.error(f"Error building sing-box routing rules: {e}")

    # 5. Системное правило API (добавляем в конец)
    sb_rules.append({
        "inbound": ["api"],
        "outbound": "api"
    })

    route_config = {
        "rules": sb_rules,
        "auto_detect_interface": True
    }
    if sb_rule_sets:
        route_config["rule_set"] = sb_rule_sets

    return route_config
