import json
import logging
from typing import Dict, Any

from backend.sentinel_core_bridge.ffi import (
    _ffi_call_json,
    get_sentinel_lib,
    run_core_command,
)

logger = logging.getLogger(__name__)


def generate_x25519_keypair() -> Dict[str, str]:
    """Generates standard X25519 keypair for VLESS Reality via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelGenerateX25519Keys")
        if isinstance(res, dict) and "privateKey" in res and "publicKey" in res:
            return res
    except Exception as e:
        logger.debug("FFI generate_x25519_keypair error: %s", e)

    res = run_core_command(["keypair"])
    if isinstance(res, dict) and "privateKey" in res and "publicKey" in res:
        return res
    return {"privateKey": "", "publicKey": ""}


def generate_vlessenc_keypair() -> Dict[str, Any]:
    """Generates X25519 and ML-KEM-768 key pairs for VLESS Encryption via sentinel-core."""
    lib = get_sentinel_lib()
    if lib is not None:
        try:
            res = _ffi_call_json("SentinelGenerateVlessEncKeys")
            if isinstance(res, dict) and res.get("success") is True:
                mlkem = res.get("mlkem768", {})
                dec_val = mlkem.get("decryption", "")
                dec_payload = dec_val.split(".")[-1] if "." in dec_val else dec_val
                if len(dec_payload) <= 86:
                    return res
        except Exception as e:
            logger.debug("FFI generate_vlessenc_keypair error: %s", e)

    res = run_core_command(["vlessenc"])
    if isinstance(res, dict) and res.get("success") is True:
        return res

    return {
        "success": False,
        "x25519": {"decryption": "", "encryption": ""},
        "mlkem768": {"decryption": "", "encryption": ""}
    }


def encrypt_payload(data: str, secret: str) -> str:
    """Encrypts a payload with authenticated AEAD via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelEncrypt", data, secret)
        if isinstance(res, dict) and "payload" in res:
            return str(res["payload"])
    except Exception as e:
        logger.debug("FFI encrypt_payload error: %s", e)

    res = run_core_command(["encrypt", "--secret", secret, "--data", data])
    if isinstance(res, dict) and "payload" in res:
        return res["payload"]
    return ""


def decrypt_payload(encrypted_payload: str, secret: str) -> str:
    """Decrypts an authenticated AEAD payload via sentinel-core."""
    try:
        res = _ffi_call_json("SentinelDecrypt", encrypted_payload, secret)
        if isinstance(res, dict) and "plaintext" in res:
            return str(res["plaintext"])
    except Exception as e:
        logger.debug("FFI decrypt_payload error: %s", e)

    res = run_core_command(["decrypt", "--secret", secret, "--payload", encrypted_payload])
    if isinstance(res, dict) and "plaintext" in res:
        return res["plaintext"]
    return ""
