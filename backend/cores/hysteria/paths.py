import platform
from backend.config import BIN_DIR, IS_WINDOWS, HYSTERIA_LOG_PATH


def _get_bin_suffix() -> str:
    arch = platform.machine().lower()
    return "arm64" if ("arm64" in arch or "aarch64" in arch) else "amd64"


HYSTERIA_BIN_NAME = f"hysteria-windows-{_get_bin_suffix()}.exe" if IS_WINDOWS else f"hysteria-linux-{_get_bin_suffix()}"
HYSTERIA_BIN_PATH = BIN_DIR / HYSTERIA_BIN_NAME
HYSTERIA_CERT_PATH = BIN_DIR / "hysteria.crt"
HYSTERIA_KEY_PATH = BIN_DIR / "hysteria.key"
