import os
import sys
import shutil
import subprocess
import re
import logging
import json
import urllib.request
import urllib.error
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [WarpAgent] - %(levelname)s - %(message)s")

def is_warp_installed() -> bool:
    """Checks if the warp-cli binary is present in the host system's PATH."""
    return shutil.which("warp-cli") is not None

def load_reg_credentials() -> tuple[str, str]:
    """Reads registration ID and API token from reg.json."""
    reg_path = "/var/lib/cloudflare-warp/reg.json"
    if not os.path.exists(reg_path):
        return "", ""
    try:
        with open(reg_path, "r") as f:
            data = json.load(f)
            reg_id = data.get("id") or data.get("registration_id") or ""
            token = data.get("token") or data.get("api_token") or ""
            return reg_id, token
    except Exception as e:
        logging.error(f"Error reading WARP credentials from reg.json: {e}")
    return "", ""

def get_warp_quota(reg_id: str, token: str) -> tuple[int, int]:
    """Queries Cloudflare API to get premium data quota and usage in bytes."""
    url = f"https://api.cloudflareclient.com/v1/reg/{reg_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "okhttp/3.12.1")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                resp_data = json.loads(response.read().decode("utf-8"))
                account = resp_data.get("account", {})
                quota = account.get("quota", 0)
                premium_data = account.get("premium_data", 0)
                usage = account.get("usage", 0)
                total_quota = max(quota, premium_data)
                return total_quota, usage
    except Exception as e:
        logging.error(f"Error querying WARP quota from Cloudflare API: {e}")
    return 0, 0

def get_warp_status() -> dict:
    """Returns the current status of Cloudflare WARP client on the host."""
    if not is_warp_installed():
        return {
            "installed": False,
            "connected": False,
            "registration": None,
            "type": "free",
            "license": "",
            "socks_port": 40000,
            "quota": 0,
            "usage": 0
        }

    connected = False
    registration_type = "free"
    license_key = ""
    socks_port = 40000

    # 1. Check connection status
    try:
        res = subprocess.run(["warp-cli", "status"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            output = res.stdout.lower()
            if "status update: connected" in output or "connected" in output:
                connected = True
    except Exception as e:
        logging.error(f"Error checking warp status: {e}")

    # 2. Check registration info
    try:
        # Try modern command syntax first
        res = subprocess.run(["warp-cli", "registration", "show"], capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            # Fallback to older command syntax
            res = subprocess.run(["warp-cli", "registration-show"], capture_output=True, text=True, timeout=5)

        if res.returncode == 0:
            output = res.stdout
            if "Account type" in output:
                acc_type_match = re.search(r"Account type:\s*(.*)", output)
                if acc_type_match:
                    registration_type = acc_type_match.group(1).strip()
            
            if "Warp+" in output or "Premium" in output:
                registration_type = "plus"
            
            license_match = re.search(r"License:\s*(.*)", output)
            if license_match:
                license_key = license_match.group(1).strip()
    except Exception as e:
        logging.error(f"Error checking warp registration: {e}")

    quota = 0
    usage = 0
    reg_id, token = load_reg_credentials()
    if reg_id and token:
        quota, usage = get_warp_quota(reg_id, token)

    return {
        "installed": True,
        "connected": connected,
        "registration": registration_type,
        "type": "plus" if "plus" in registration_type.lower() or "premium" in registration_type.lower() else "free",
        "license": license_key,
        "socks_port": socks_port,
        "quota": quota,
        "usage": usage
    }

def register_warp(license_key: str = None) -> tuple[bool, str]:
    """Registers a new WARP client or updates/validates a license key."""
    if not is_warp_installed():
        return False, "Cloudflare WARP is not installed."

    # 1. Register a new account if needed
    try:
        p = subprocess.run(["warp-cli", "--accept-tos", "registration", "new"], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            p = subprocess.run(["warp-cli", "--accept-tos", "register"], capture_output=True, text=True, timeout=15)
        
        # If still failed, check if output contains "already registered"
        if p.returncode != 0 and "already" not in p.stdout.lower() and "already" not in p.stderr.lower():
            return False, f"Failed to register WARP account: {p.stderr or p.stdout}"
    except Exception as e:
        return False, f"Error registering WARP: {str(e)}"

    # 2. Configure proxy mode and default port (40000)
    try:
        p = subprocess.run(["warp-cli", "mode", "proxy"], capture_output=True, text=True, timeout=5)
        if p.returncode != 0:
            subprocess.run(["warp-cli", "set-mode", "proxy"], capture_output=True, text=True, timeout=5)
    except Exception as e:
        logging.warning(f"Failed to set mode proxy: {e}")

    try:
        p = subprocess.run(["warp-cli", "settings", "set", "proxy.port", "40000"], capture_output=True, text=True, timeout=5)
        if p.returncode != 0:
            subprocess.run(["warp-cli", "set-proxy-port", "40000"], capture_output=True, text=True, timeout=5)
    except Exception as e:
        logging.warning(f"Failed to set proxy port: {e}")

    # 3. Apply license key if provided (and validate it via warp-cli)
    if license_key:
        license_key = license_key.strip()
        try:
            # Modern command
            p = subprocess.run(["warp-cli", "registration", "license", license_key], capture_output=True, text=True, timeout=15)
            if p.returncode != 0:
                # Older command
                p = subprocess.run(["warp-cli", "set-license", license_key], capture_output=True, text=True, timeout=15)

            if p.returncode != 0:
                err_msg = p.stderr.strip() or p.stdout.strip()
                # If key is rejected by warp-cli
                return False, f"License key validation failed: {err_msg}"
        except Exception as e:
            return False, f"Error validating license key: {str(e)}"

    return True, "Registered successfully."

def connect_warp() -> tuple[bool, str]:
    """Connects the WARP client."""
    if not is_warp_installed():
        return False, "WARP is not installed."

    try:
        # Ensure registration exists on connect
        reg_id, _ = load_reg_credentials()
        if not reg_id:
            logging.info("[WarpAgent] No registration found. Attempting auto-registration first...")
            success, reg_msg = register_warp()
            if not success:
                return False, f"WARP not registered and registration failed: {reg_msg}"

        # Double check mode is proxy before connecting
        subprocess.run(["warp-cli", "--accept-tos", "mode", "proxy"], capture_output=True, timeout=5)
        subprocess.run(["warp-cli", "--accept-tos", "set-mode", "proxy"], capture_output=True, timeout=5)
        subprocess.run(["warp-cli", "--accept-tos", "settings", "set", "proxy.port", "40000"], capture_output=True, timeout=5)
        subprocess.run(["warp-cli", "--accept-tos", "set-proxy-port", "40000"], capture_output=True, timeout=5)

        p = subprocess.run(["warp-cli", "--accept-tos", "connect"], capture_output=True, text=True, timeout=10)
        if p.returncode == 0:
            return True, "WARP connected successfully."
        else:
            return False, f"Failed to connect WARP: {p.stderr or p.stdout}"
    except Exception as e:
        return False, f"Error connecting WARP: {str(e)}"

def disconnect_warp() -> tuple[bool, str]:
    """Disconnects the WARP client."""
    if not is_warp_installed():
        return False, "WARP is not installed."

    try:
        p = subprocess.run(["warp-cli", "disconnect"], capture_output=True, text=True, timeout=10)
        if p.returncode == 0:
            return True, "WARP disconnected successfully."
        else:
            return False, f"Failed to disconnect WARP: {p.stderr or p.stdout}"
    except Exception as e:
        return False, f"Error disconnecting WARP: {str(e)}"

def install_warp() -> tuple[bool, str]:
    """Installs Cloudflare WARP client on Debian/Ubuntu hosts."""
    if is_warp_installed():
        return True, "WARP is already installed."

    if sys.platform != "linux":
        return False, "WARP installation is only supported on Linux host systems."

    try:
        os_release = ""
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r") as f:
                os_release = f.read()

        is_debian_ubuntu = "debian" in os_release.lower() or "ubuntu" in os_release.lower()
        if not is_debian_ubuntu:
            return False, "WARP automatic installation is only supported on Debian/Ubuntu host systems."

        # Ensure gnupg and curl are installed on host before importing key
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        subprocess.run("apt-get update && apt-get install -y gnupg curl", shell=True, env=env, capture_output=True, timeout=90)

        # 1. Download and import Cloudflare GPG key
        gpg_key_cmd = "curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg"
        p = subprocess.run(gpg_key_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return False, f"Failed to import Cloudflare GPG key: {p.stderr or p.stdout}"

        # 2. Add apt repository
        codename_cmd = "lsb_release -cs"
        cp = subprocess.run(codename_cmd, shell=True, capture_output=True, text=True, timeout=10)
        codename = cp.stdout.strip()
        if not codename or cp.returncode != 0:
            match = re.search(r'VERSION_CODENAME=(.*)', os_release)
            if match:
                codename = match.group(1).strip().strip('"')
            else:
                codename = "bookworm" # Safe default fallback

        repo_line = f"deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ {codename} main"
        with open("/etc/apt/sources.list.d/cloudflare-warp.list", "w") as f:
            f.write(repo_line + "\n")

        # 3. Update repositories and install cloudflare-warp package
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        
        # apt-get update can exit with 1 if there are minor repo issues, so we ignore it
        subprocess.run("apt-get -o Acquire::Retries=5 update", shell=True, capture_output=True, text=True, timeout=60, env=env)

        p = subprocess.run("apt-get -o Acquire::Retries=5 install -y cloudflare-warp", shell=True, capture_output=True, text=True, timeout=180, env=env)
        if p.returncode != 0:
            return False, f"Failed to install cloudflare-warp package: {p.stderr or p.stdout}"

        if not is_warp_installed():
            return False, "cloudflare-warp package was installed but warp-cli was not found in PATH."

        # 4. Automatically register free account and connect
        register_warp()
        connect_warp()

        return True, "Cloudflare WARP installed and registered successfully."
    except Exception as e:
        return False, f"Error installing WARP: {str(e)}"

def uninstall_warp() -> tuple[bool, str]:
    """Uninstalls Cloudflare WARP client from host."""
    if not is_warp_installed():
        return True, "WARP is not installed."

    try:
        # Disconnect client first
        subprocess.run(["warp-cli", "disconnect"], capture_output=True, timeout=10)

        # Remove package
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        p = subprocess.run("apt-get remove -y cloudflare-warp", shell=True, capture_output=True, text=True, timeout=120, env=env)
        if p.returncode != 0:
            return False, f"Failed to remove cloudflare-warp package: {p.stderr or p.stdout}"

        # Clean up files
        list_file = Path("/etc/apt/sources.list.d/cloudflare-warp.list")
        if list_file.exists():
            list_file.unlink()

        return True, "Cloudflare WARP uninstalled successfully."
    except Exception as e:
        return False, f"Error uninstalling WARP: {str(e)}"
