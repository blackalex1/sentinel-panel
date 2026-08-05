#!/bin/bash

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root (use sudo)"
  exit 1
fi

# Navigate to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "===================================================="
echo "⚠️  WARNING: COMPLETE RESET OF SPECTRE PANEL"
echo "===================================================="
echo "This script will completely erase:"
echo " 1. All PostgreSQL database data (users, clients, history)"
echo " 2. All configuration settings and Telegram tokens (config/.env)"
echo " 3. Host agent service configurations"
echo " 4. Docker images and volumes"
echo "----------------------------------------------------"
read -p "Are you absolutely sure you want to proceed? (y/N): " CONFIRM

if [[ ! "$CONFIRM" =~ ^[yY]$ ]]; then
    echo "Reset cancelled."
    exit 0
fi

echo "[+] Stopping Docker containers and removing volumes/images..."
docker compose down -v --rmi all --remove-orphans

echo "[+] Stopping and disabling spectre-agent service..."
systemctl stop spectre-agent 2>/dev/null
systemctl disable spectre-agent 2>/dev/null
rm -f /etc/systemd/system/spectre-agent.service
systemctl daemon-reload

echo "[+] Deleting configurations and database files..."
rm -f config/.env
rm -f panel.db test_panel.db
rm -rf /var/run/spectre

echo "[+] Cleanup complete!"
echo "===================================================="
read -p "Would you like to start a clean installation now? (y/N): " START_INSTALL

if [[ "$START_INSTALL" =~ ^[yY]$ ]]; then
    if [ -f "./installation/install_with_docker.sh" ]; then
        chmod +x ./installation/install_with_docker.sh
        ./installation/install_with_docker.sh
    else
        echo "[!] installation/install_with_docker.sh not found."
    fi
else
    echo "Done. You can start the installation later using: sudo ./installation/install_with_docker.sh"
fi
