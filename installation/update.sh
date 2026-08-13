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
echo "🔄 UPDATING SENTINEL PANEL"
echo "===================================================="

# 1. Pull latest updates from Git
echo "[+] Pulling latest updates from Git..."
git remote set-url origin https://github.com/blackalex1/sentinel-panel.git 2>/dev/null
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null)
if git fetch origin main && git reset --hard origin/main; then
    NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)
    if [ "$OLD_HEAD" != "$NEW_HEAD" ] && [ -n "$OLD_HEAD" ]; then
        echo "[+] Changes pulled:"
        git diff --stat "$OLD_HEAD" "$NEW_HEAD"
    else
        echo "[+] Already up to date."
    fi
    echo "[+] Git update completed successfully."
else
    echo "[!] Git update failed. If you have local changes, stash them or resolve conflicts."
fi

# 2. Rebuild and restart Docker containers
echo "[+] Rebuilding and restarting Docker containers..."
docker ps -a --filter "name=spectre" -q | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=sentinel" -q | xargs -r docker rm -f 2>/dev/null || true
docker compose down --remove-orphans 2>/dev/null || true
if docker compose up -d --build; then
    echo "[+] Docker containers rebuilt and started successfully!"
else
    echo "[!] Failed to rebuild or start Docker containers."
fi

# 3. Update and restart host agent system service (sentinel-agent)
echo "[+] Configuring and restarting sentinel-agent system service..."
if systemctl is-active --quiet spectre-agent 2>/dev/null || [ -f "/etc/systemd/system/spectre-agent.service" ]; then
    echo "[+] Cleaning up legacy spectre-agent service..."
    systemctl stop spectre-agent 2>/dev/null || true
    systemctl disable spectre-agent 2>/dev/null || true
    rm -f /etc/systemd/system/spectre-agent.service
fi

SERVICE_TEMPLATE="$SCRIPT_DIR/host/sentinel-agent.service"
SERVICE_DEST="/etc/systemd/system/sentinel-agent.service"

if [ -f "$SERVICE_TEMPLATE" ]; then
    sed "s|/opt/sentinel-panel|$SCRIPT_DIR|g" "$SERVICE_TEMPLATE" > "$SERVICE_DEST"
    systemctl daemon-reload
    systemctl enable sentinel-agent
    systemctl restart sentinel-agent
    echo "[+] sentinel-agent service configured and started successfully!"
else
    echo "[!] Service template $SERVICE_TEMPLATE not found."
fi

echo "===================================================="
echo "[+] Update process complete! Showing logs for sentinel-panel (Ctrl+C to exit)..."
echo "===================================================="
docker logs -f sentinel-panel
