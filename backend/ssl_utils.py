import os
import shutil
import subprocess
import logging
from pathlib import Path
from backend.config import CONFIG_DIR

SSL_CERT_PATH = CONFIG_DIR / "cert.pem"
SSL_KEY_PATH = CONFIG_DIR / "key.pem"

def generate_default_self_signed_cert():
    """Генерирует дефолтный самоподписанный сертификат для панели с поддержкой SAN"""
    if SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists():
        return
        
    logging.info("Generating default self-signed SSL certificate for the panel...")
    try:
        import ipaddress, datetime
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        san = x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(san, critical=False)
            .sign(key, hashes.SHA256())
        )
        SSL_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SSL_KEY_PATH, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open(SSL_CERT_PATH, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        logging.info("Default self-signed SSL certificate generated successfully with SAN.")
        return
    except Exception as e:
        logging.warning("Cryptography cert generation failed (%s), falling back to OpenSSL...", e)

    try:
        openssl_bin = shutil.which("openssl") or "/usr/bin/openssl"
        if os.name == "nt":
            openssl_bin = shutil.which("openssl") or "openssl"
            
        cmd = [
            openssl_bin, "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(SSL_KEY_PATH), "-out", str(SSL_CERT_PATH),
            "-days", "365", "-nodes", "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603
        logging.info("Default self-signed SSL certificate generated successfully via OpenSSL.")
    except Exception as e:
        logging.warning(f"Could not generate default self-signed certificate: {e}")

def request_ssl_cert(domain: str, email: str) -> tuple[bool, str]:
    """Выпускает SSL сертификат Let's Encrypt с помощью встроенного ACME HTTP-01 клиента"""
    logging.info(f"[SSL] Issuing Let's Encrypt certificate for domain {domain} via built-in ACME client...")
    from backend.acme_client import run_acme_flow
    try:
        # Выпускаем через Let's Encrypt Production
        success, msg, cert_pem, key_pem = run_acme_flow(domain, email, use_staging=False)
        if not success:
            return False, f"Ошибка выпуска сертификата: {msg}"
            
        # Записываем файлы сертификатов
        with open(SSL_CERT_PATH, "w", encoding="utf-8") as f:
            f.write(cert_pem)
        with open(SSL_KEY_PATH, "w", encoding="utf-8") as f:
            f.write(key_pem)
            
        try:
            os.chmod(SSL_CERT_PATH, 0o644)
            os.chmod(SSL_KEY_PATH, 0o600)
        except Exception as e:
            logging.error(f"Failed to set SSL certificate permissions: {e}")
            
        logging.info(f"[SSL] Certificate for {domain} successfully saved to {SSL_CERT_PATH}")
        return True, "Сертификат успешно выпущен и установлен."
    except Exception as e:
        return False, f"Исключение при выпуске сертификата: {e}"


def cert_matches_domain(cert_path: Path, domain: str) -> bool:
    """Проверяет, содержит ли SSL-сертификат указанный домен в CN или SAN (включая wildcards)"""
    if not cert_path or not cert_path.exists() or not domain:
        return False
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        
        domain_lower = domain.strip().lower()
        
        cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn_attrs and cn_attrs[0].value.lower() == domain_lower:
            return True
            
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in san_ext.value.get_values_for_type(x509.DNSName):
                name_lower = name.lower()
                if name_lower == domain_lower:
                    return True
                if name_lower.startswith("*."):
                    suffix = name_lower[1:]
                    if domain_lower.endswith(suffix) and domain_lower.count(".") == name_lower.count("."):
                        return True
        except x509.ExtensionNotFound:
            pass
    except Exception:
        pass
    return False

def generate_custom_self_signed_cert(cert_path: Path, key_path: Path, cn: str):
    """Генерирует самоподписанный SSL-сертификат для указанного домена (CN) с поддержкой SAN"""
    try:
        sni_marker_path = cert_path.with_suffix(".sni")
        if cert_path.exists() and key_path.exists() and cert_matches_domain(cert_path, cn):
            return True

        logging.info(f"Generating custom self-signed SSL certificate for CN={cn} with SAN...")
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            import ipaddress, datetime
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
            
            alt_names = [x509.DNSName(cn)]
            try:
                ip_obj = ipaddress.ip_address(cn)
                alt_names.append(x509.IPAddress(ip_obj))
            except ValueError:
                pass
                
            san = x509.SubjectAlternativeName(alt_names)
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
                .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
                .add_extension(san, critical=False)
                .sign(key, hashes.SHA256())
            )
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            with open(sni_marker_path, "w", encoding="utf-8") as f:
                f.write(cn)
            logging.info(f"Custom SSL cert with SAN generated for CN={cn}")
            return True
        except Exception as e:
            logging.warning("Failed to generate cert via cryptography (%s), trying openssl...", e)

        openssl_bin = shutil.which("openssl") or "/usr/bin/openssl"
        if os.name == "nt":
            openssl_bin = shutil.which("openssl") or "openssl"

        cmd = [
            openssl_bin, "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", "365", "-nodes", "-subj", f"/CN={cn}",
            "-addext", f"subjectAltName=DNS:{cn}"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # nosec B603
        with open(sni_marker_path, "w", encoding="utf-8") as f:
            f.write(cn)
        return True
    except Exception as e:
        logging.warning(f"Could not generate custom self-signed certificate for CN={cn}: {e}")
        return False
