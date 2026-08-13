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
docker compose down
if docker compose up -d --build; then
    echo "[+] Docker containers rebuilt and started successfully!"
else
    echo "[!] Failed to rebuild or start Docker containers."
fi

# 3. Restart sentinel-agent service
echo "[+] Restarting sentinel-agent system service..."
if systemctl is-active --quiet sentinel-agent; then
    systemctl restart sentinel-agent
    echo "[+] sentinel-agent service restarted successfully!"
else
    if [ -f "/etc/systemd/system/sentinel-agent.service" ]; then
        systemctl daemon-reload
        systemctl enable sentinel-agent
        systemctl start sentinel-agent
        echo "[+] sentinel-agent service enabled and started!"
    else
        echo "[!] sentinel-agent service is not installed on this host."
    fi
fi

echo "===================================================="
echo "[+] Update process complete! Showing logs for sentinel-panel (Ctrl+C to exit)..."
echo "===================================================="
docker logs -f sentinel-panel
