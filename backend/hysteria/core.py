import os
import logging
import subprocess
import requests
import shutil
import platform
import backend.hysteria

def _get_bin_suffix():
    arch = platform.machine().lower()
    return "arm64" if ("arm64" in arch or "aarch64" in arch) else "amd64"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 SentinelPanel/1.0"}

import time
import xml.etree.ElementTree as ET

_HYSTERIA_RELEASES_CACHE = {}
CACHE_TTL = 3600  # 1 hour cache for releases

def _fetch_hysteria_releases_atom(include_prerelease: bool = False, limit: int = 20) -> list[dict]:
    try:
        url = "https://github.com/apernet/hysteria/releases.atom"
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code != 200:
            return []
        raw_content = getattr(resp, "content", None)
        if raw_content is None:
            raw_content = getattr(resp, "text", "").encode("utf-8")
        if not raw_content:
            return []
        root = ET.fromstring(raw_content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        arch = platform.machine().lower()
        is_arm = "arm64" in arch or "aarch64" in arch
        releases = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            title_text = title.text.strip() if title is not None and title.text else ""
            tag = title_text.split()[-1] if title_text else ""
            if not tag:
                continue
            if not tag.startswith("app/"):
                if tag.startswith("v"):
                    tag = "app/" + tag
                else:
                    tag = "app/v" + tag
            is_pre = any(k in tag.lower() for k in ("beta", "alpha", "rc", "pre"))
            if not include_prerelease and is_pre:
                continue
            clean_tag = tag.replace("app/", "")
            if backend.hysteria.IS_WINDOWS:
                target_name = f"hysteria-windows-arm64.exe" if is_arm else f"hysteria-windows-amd64.exe"
            else:
                target_name = f"hysteria-linux-arm64" if is_arm else f"hysteria-linux-amd64"
            download_url = f"https://github.com/apernet/hysteria/releases/download/{tag}/{target_name}"
            releases.append({
                "version": clean_tag,
                "download_url": download_url,
                "is_prerelease": is_pre
            })
            if len(releases) >= limit:
                break
        return releases
    except Exception as e:
        logging.error(f"Failed to fetch Hysteria releases atom feed: {e}")
        return []

def get_hysteria_releases(include_prerelease: bool = False, limit: int = 20) -> list[dict]:
    """Получает список всех доступных релизов Hysteria 2 с GitHub с кэшированием в памяти"""
    cache_key = f"releases_{include_prerelease}_{limit}"
    now = time.time()

    # Сначала проверяем горячий кэш
    if cache_key in _HYSTERIA_RELEASES_CACHE:
        ts, cached = _HYSTERIA_RELEASES_CACHE[cache_key]
        if now - ts < CACHE_TTL and cached:
            return cached

    url = "https://api.github.com/repos/apernet/hysteria/releases"
    releases = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=6)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list):
                target_name = backend.hysteria.HYSTERIA_BIN_NAME
                arch_suffix = _get_bin_suffix()
                os_prefix = "windows" if backend.hysteria.IS_WINDOWS else "linux"

                for item in data:
                    is_pre = bool(item.get("prerelease", False))
                    if not include_prerelease and is_pre:
                        continue
                    tag_name = item.get("tag_name", "")
                    if tag_name.startswith("app/"):
                        tag_name = tag_name[4:]
                    download_url = None
                    for asset in item.get("assets", []):
                        aname = asset.get("name", "").lower()
                        if aname == target_name.lower() or (os_prefix in aname and arch_suffix in aname):
                            download_url = asset.get("browser_download_url")
                            break
                    if not download_url and item.get("assets"):
                        download_url = item["assets"][0].get("browser_download_url")
                    if tag_name and download_url:
                        releases.append({
                            "version": tag_name,
                            "download_url": download_url,
                            "is_prerelease": is_pre
                        })
                    if len(releases) >= limit:
                        break
    except Exception as e:
        logging.error(f"Failed to fetch Hysteria releases list from GitHub API: {e}")

    if releases:
        _HYSTERIA_RELEASES_CACHE[cache_key] = (now, releases)
        return releases

    # Резервный опрос через Atom feed
    releases = _fetch_hysteria_releases_atom(include_prerelease=include_prerelease, limit=limit)
    if releases:
        _HYSTERIA_RELEASES_CACHE[cache_key] = (now, releases)
        return releases

    # Если опрос не удался, но есть устаревший кэш — отдаем его
    if cache_key in _HYSTERIA_RELEASES_CACHE:
        return _HYSTERIA_RELEASES_CACHE[cache_key][1]

    return []

def get_latest_hysteria_version_info(include_prerelease: bool = False):
    """Получает последний релиз Hysteria с GitHub с кэшированием в памяти"""
    cache_key = f"latest_{include_prerelease}"
    now = time.time()
    if cache_key in _HYSTERIA_RELEASES_CACHE:
        ts, cached = _HYSTERIA_RELEASES_CACHE[cache_key]
        if now - ts < CACHE_TTL and cached:
            return cached

    url = "https://api.github.com/repos/apernet/hysteria/releases/latest"
    try:
        response = requests.get(url, headers=HEADERS, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                tag_name = data.get("tag_name", "")
                if tag_name.startswith("app/"):
                    tag_name = tag_name[4:]
                assets = data.get("assets", [])
                target_name = backend.hysteria.HYSTERIA_BIN_NAME
                arch_suffix = _get_bin_suffix()
                os_prefix = "windows" if backend.hysteria.IS_WINDOWS else "linux"
                download_url = None
                for asset in assets:
                    aname = asset.get("name", "").lower()
                    if aname == target_name.lower() or (os_prefix in aname and arch_suffix in aname):
                        download_url = asset.get("browser_download_url")
                        break
                if not download_url and assets:
                    download_url = assets[0].get("browser_download_url")
                if tag_name:
                    res = {"version": tag_name, "download_url": download_url, "is_prerelease": False}
                    _HYSTERIA_RELEASES_CACHE[cache_key] = (now, res)
                    return res
    except Exception:
        pass

    releases = get_hysteria_releases(include_prerelease=include_prerelease, limit=1)
    if releases and len(releases) > 0:
        return releases[0]
    return None

def download_hysteria_core(download_url: str = None):
    """Скачивает и устанавливает бинарник Hysteria"""
    if not download_url:
        info = get_latest_hysteria_version_info()
        if not info or not info["download_url"]:
            raise Exception("Could not find Hysteria download URL automatically.")
        download_url = info["download_url"]
        version = info["version"]
    else:
        from urllib.parse import urlparse, unquote
        try:
            parsed = urlparse(download_url)
            path_lower = unquote(parsed.path).lower()
            is_safe = (
                parsed.scheme == "https"
                and parsed.netloc.lower() == "github.com"
                and path_lower.startswith("/apernet/hysteria/releases/download/")
            )
        except Exception:
            is_safe = False
            
        if not is_safe:
            raise ValueError("Недопустимый URL для скачивания. Разрешены только официальные релизы Hysteria на GitHub.")
            
        version = "custom"
        
    logging.info(f"Downloading Hysteria 2 from {download_url}...")
    response = requests.get(download_url, stream=True, timeout=30)
    response.raise_for_status()
    
    temp_bin_path = backend.hysteria.HYSTERIA_BIN_PATH.with_suffix(".tmp")
    try:
        with open(temp_bin_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        if not backend.hysteria.IS_WINDOWS:
            try:
                os.chmod(temp_bin_path, 0o755)  # nosec B103
                logging.info("Chmod +x set on temporary Hysteria binary.")
            except Exception as e:
                logging.error(f"Failed to set executable on temporary Hysteria binary: {e}")
                
        # Проверяем работоспособность временного бинарника
        try:
            cmd = [str(temp_bin_path), "version"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)  # nosec B603
            if result.returncode != 0:
                err_msg = result.stderr.strip() or result.stdout.strip()
                raise Exception(f"Self-test returned non-zero code {result.returncode}: {err_msg}")
        except Exception as e:
            raise Exception(f"Downloaded Hysteria binary failed self-test verification: {str(e)}")
            
        if backend.hysteria.HYSTERIA_BIN_PATH.exists():
            try:
                os.remove(backend.hysteria.HYSTERIA_BIN_PATH)
            except Exception as e:
                logging.warning(f"Could not remove old Hysteria binary before replacing: {e}")
        
        shutil.move(str(temp_bin_path), str(backend.hysteria.HYSTERIA_BIN_PATH))
        logging.info("Hysteria core successfully verified and installed.")
    finally:
        if temp_bin_path.exists():
            try:
                os.remove(temp_bin_path)
            except Exception:
                pass
                
    return version

def ensure_hysteria_installed():
    need_install = False
    if not backend.hysteria.HYSTERIA_BIN_PATH.exists():
        need_install = True
    else:
        try:
            cmd = [str(backend.hysteria.HYSTERIA_BIN_PATH), "version"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            if result.returncode != 0:
                need_install = True
        except Exception:
            need_install = True
            
    if need_install:
        logging.info("Hysteria 2 core not found or not working (wrong architecture?). Installing/Updating...")
        try:
            backend.hysteria.download_hysteria_core()
        except Exception as e:
            logging.error(f"Error installing Hysteria core: {e}")

def get_installed_hysteria_version() -> str:
    """Runs version check to get the currently installed version dynamically via sentinel-core."""
    if not backend.hysteria.HYSTERIA_BIN_PATH.exists():
        return "Not Installed"
    try:
        from backend.sentinel_core_bridge import get_core_version
        v = get_core_version("hysteria2", str(backend.hysteria.HYSTERIA_BIN_PATH))
        if v and v != "Unknown":
            return v
    except Exception as e:
        logging.error(f"Error getting hysteria2 version via sentinel-core: {e}")
    return "Unknown"

def generate_self_signed_cert(force: bool = False):
    """Генерирует самоподписанный сертификат для Hysteria, если его нет. При force=True принудительно перевыпускает."""
    if not force and backend.hysteria.HYSTERIA_CERT_PATH.exists() and backend.hysteria.HYSTERIA_KEY_PATH.exists():
        if backend.hysteria.HYSTERIA_CERT_PATH.stat().st_size > 0 and backend.hysteria.HYSTERIA_KEY_PATH.stat().st_size > 0:
            return
        
    logging.info("Generating self-signed SSL certificate for Hysteria 2...")
    
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime

        import ipaddress
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        
        from backend.database import get_setting
        server_ip = get_setting("server_ip") or ""
        server_domain = get_setting("server_domain") or ""
        
        # Собираем SNI из всех Hysteria инбаундов
        custom_snis = set()
        try:
            from backend.inbounds import get_all_inbounds
            for ib in get_all_inbounds():
                if ib.get("protocol") == "hysteria2":
                    import json
                    st = json.loads(ib.get("stream_settings") or "{}")
                    h_opt = st.get("hysteria", {})
                    s = h_opt.get("sni") or st.get("sni") or ""
                    if s:
                        custom_snis.add(s.strip())
        except Exception:
            pass

        primary_cn = sorted(list(custom_snis))[0] if custom_snis else (server_domain.strip() if server_domain else "localhost")

        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, primary_cn)])
        
        san_set = {"localhost"}
        for s in custom_snis:
            san_set.add(s)
            if "." in s and not s.startswith("*."):
                parts = s.split(".")
                if len(parts) >= 2:
                    san_set.add(f"*.{'.'.join(parts[1:])}")

        if server_domain:
            san_set.add(server_domain.strip())

        san_list = []
        for name in san_set:
            if name:
                try:
                    san_list.append(x509.DNSName(name))
                except Exception:
                    pass

        san_list.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
        if server_ip:
            try:
                san_list.append(x509.IPAddress(ipaddress.ip_address(server_ip.strip())))
            except Exception:
                pass
                
        san = x509.SubjectAlternativeName(san_list)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
            .add_extension(san, critical=False)
            .sign(key, hashes.SHA256())
        )
        backend.hysteria.HYSTERIA_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(backend.hysteria.HYSTERIA_KEY_PATH, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open(backend.hysteria.HYSTERIA_CERT_PATH, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        logging.info("Self-signed SSL certificate generated successfully.")
        return True
    except Exception as e:
        logging.warning("Failed to generate cert via cryptography (%s), trying openssl...", e)

    try:
        openssl_path = shutil.which("openssl") or ("openssl" if backend.hysteria.IS_WINDOWS else "/usr/bin/openssl")
        cmd = [
            openssl_path, "req", "-x509", "-newkey", "rsa:2048", 
            "-keyout", str(backend.hysteria.HYSTERIA_KEY_PATH), "-out", str(backend.hysteria.HYSTERIA_CERT_PATH), 
            "-days", "3650", "-nodes", "-subj", f"/CN={primary_cn}",
            "-addext", f"subjectAltName=DNS:localhost,DNS:{primary_cn},IP:127.0.0.1"
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603
        if res.returncode == 0 and backend.hysteria.HYSTERIA_CERT_PATH.exists():
            logging.info("Self-signed SSL certificate generated via OpenSSL.")
            return True
    except Exception:
        pass
    return False

def get_hysteria_cert_status() -> dict:
    """Проверяет состояние SSL-сертификата Hysteria 2: валидность, срок, хеш, соответствие ключу и SNI."""
    cert_path = backend.hysteria.HYSTERIA_CERT_PATH
    key_path = backend.hysteria.HYSTERIA_KEY_PATH

    status = {
        "exists": False,
        "valid": False,
        "fingerprint_sha256": "",
        "common_name": "",
        "sans": [],
        "key_matches": False,
        "expires_at": "",
        "days_left": 0,
        "is_expired": False,
        "needs_reissue": False,
        "reissue_reasons": []
    }

    if not cert_path.exists() or not key_path.exists() or cert_path.stat().st_size == 0 or key_path.stat().st_size == 0:
        status["needs_reissue"] = True
        status["reissue_reasons"].append("Файлы сертификата или приватного ключа отсутствуют или пусты.")
        return status

    status["exists"] = True

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        import hashlib
        import datetime

        # 1. Загружаем сертификат и ключ
        with open(cert_path, "rb") as f:
            cert_bytes = f.read()
            cert = x509.load_pem_x509_certificate(cert_bytes)

        with open(key_path, "rb") as f:
            key_bytes = f.read()
            private_key = serialization.load_pem_private_key(key_bytes, password=None)

        # 2. SHA-256 Fingerprint (в DER-формате)
        der_bytes = cert.public_bytes(serialization.Encoding.DER)
        status["fingerprint_sha256"] = hashlib.sha256(der_bytes).hexdigest()

        # 3. Common Name и SAN
        from cryptography.x509.oid import NameOID
        cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn_attrs:
            status["common_name"] = cn_attrs[0].value

        sans = []
        try:
            ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in ext.value:
                if isinstance(name, x509.DNSName):
                    sans.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    sans.append(str(name.value))
        except Exception:
            pass
        status["sans"] = sans

        # 4. Проверка совпадения ключа и сертификата
        cert_pub = cert.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        key_pub = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        status["key_matches"] = (cert_pub == key_pub)
        if not status["key_matches"]:
            status["needs_reissue"] = True
            status["reissue_reasons"].append("Приватный ключ не соответствует публичному сертификату.")

        # 5. Срок действия
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        expires_at = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
        status["expires_at"] = expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        days_left = (expires_at - now_utc).days
        status["days_left"] = days_left
        if days_left <= 0:
            status["is_expired"] = True
            status["needs_reissue"] = True
            status["reissue_reasons"].append(f"Срок действия сертификата истек ({status['expires_at']}).")

        # 6. Сверка со всеми активными инбаундами Hysteria 2
        try:
            from backend.inbounds import get_all_inbounds
            inbounds = get_all_inbounds()
            for ib in inbounds:
                if ib.get("protocol") == "hysteria2" and ib.get("enable"):
                    stream_settings = {}
                    try:
                        import json
                        stream_settings = json.loads(ib.get("stream_settings") or "{}")
                    except Exception:
                        pass
                    h_opts = stream_settings.get("hysteria", {})
                    sni = h_opts.get("sni") or stream_settings.get("sni") or ""
                    if sni:
                        matched = False
                        for san_name in sans:
                            if san_name == sni or (san_name.startswith("*.") and sni.endswith(san_name[2:])):
                                matched = True
                                break
                        if not matched:
                            status["needs_reissue"] = True
                            status["reissue_reasons"].append(f"В сертификате отсутствует SNI '{sni}' из настроек подключения #{ib.get('id')}.")
        except Exception as ex:
            logging.debug(f"Error checking inbounds SNI for Hysteria cert status: {ex}")

        status["valid"] = (status["key_matches"] and not status["is_expired"] and not status["needs_reissue"])
    except Exception as e:
        status["valid"] = False
        status["needs_reissue"] = True
        status["reissue_reasons"].append(f"Ошибка чтения/валидации сертификата: {e}")

    return status

def reissue_hysteria_cert() -> tuple[bool, str]:
    """Принудительно перевыпускает SSL-сертификат Hysteria 2 с поддержкой всех SNI и перезапускает ядро"""
    success = generate_self_signed_cert(force=True)
    if not success:
        return False, "Не удалось сгенерировать сертификат."
    
    # Если Hysteria запущена, перезапускаем для применения новых сертификатов
    try:
        from backend.hysteria.service import is_hysteria_running, restart_hysteria
        if is_hysteria_running():
            restart_hysteria()
    except Exception as e:
        logging.error(f"Error restarting Hysteria after cert reissue: {e}")
        
    return True, "SSL-сертификат Hysteria 2 успешно перевыпущен."
