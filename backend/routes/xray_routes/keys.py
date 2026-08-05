import subprocess
from fastapi import APIRouter, Request

from backend.config import XRAY_BIN_PATH

router = APIRouter()

@router.get("/api/xray/x25519")
async def generate_x25519_keys(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    try:
        cmd = [str(XRAY_BIN_PATH), "x25519"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)  # nosec B603
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            private_key = ""
            public_key = ""
            for line in lines:
                if ":" in line:
                    prefix, value = line.split(":", 1)
                    prefix_clean = prefix.lower().replace(" ", "")
                    if "privatekey" in prefix_clean:
                        private_key = value.strip()
                    elif "publickey" in prefix_clean:
                        public_key = value.strip()
            return {"success": True, "privateKey": private_key, "publicKey": public_key}
        return {"success": False, "msg": "Не удалось сгенерировать ключи"}
    except Exception as e:
        return {"success": False, "msg": f"Ошибка: {e}"}

@router.get("/api/xray/vlessenc")
async def generate_vlessenc_keys(request: Request):
    import backend.routes.xray as xray_facade
    if not xray_facade.check_auth(request):
        return xray_facade.decoy_response()
    try:
        cmd = [str(XRAY_BIN_PATH), "vlessenc"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=5)  # nosec B603
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            auth_type = None
            data = {
                "x25519": {"decryption": "", "encryption": ""},
                "mlkem768": {"decryption": "", "encryption": ""}
            }
            for line in lines:
                line_clean = line.strip()
                if "Authentication: X25519" in line_clean:
                    auth_type = "x25519"
                elif "Authentication: ML-KEM-768" in line_clean:
                    auth_type = "mlkem768"
                elif auth_type and ":" in line_clean:
                    parts = line_clean.split(":", 1)
                    key = parts[0].strip().replace('"', '')
                    val = parts[1].strip().replace('"', '').replace(',', '')
                    if key in ("decryption", "encryption"):
                        data[auth_type][key] = val
            return {
                "success": True,
                "x25519": data["x25519"],
                "mlkem768": data["mlkem768"]
            }
        return {"success": False, "msg": "Не удалось сгенерировать VLESS-Encryption ключи"}
    except Exception as e:
        return {"success": False, "msg": f"Ошибка: {e}"}
