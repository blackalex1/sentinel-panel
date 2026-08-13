#!/bin/bash

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root (use sudo)"
  exit 1
fi

# Navigate to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "===================================================="
echo "🔄 MIGRATING TO SENTINEL PANEL"
echo "===================================================="

# 1. Update Git remote and pull latest main branch
echo "[+] Updating Git repository remote to sentinel-panel..."
git remote set-url origin https://github.com/blackalex1/sentinel-panel.git 2>/dev/null

echo "[+] Pulling latest code from main branch..."
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null)
if git fetch origin main && git reset --hard origin/main; then
    NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)
    if [ "$OLD_HEAD" != "$NEW_HEAD" ] && [ -n "$OLD_HEAD" ]; then
        echo "[+] Changes applied:"
        git diff --stat "$OLD_HEAD" "$NEW_HEAD"
    else
        echo "[+] Code is up to date."
    fi
    echo "[+] Git repository updated successfully."
else
    echo "[!] Git update failed. Resolving local conflicts..."
fi

# 2. Migrate Host Agent Systemd Service
echo "[+] Migrating host agent service from spectre-agent to sentinel-agent..."
if systemctl is-active --quiet spectre-agent 2>/dev/null || [ -f "/etc/systemd/system/spectre-agent.service" ]; then
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
    echo "[+] sentinel-agent service configured and started!"
else
    echo "[!] Service template host/sentinel-agent.service not found."
fi

# 3. Rebuild and restart Docker containers (Database volumes pgdata are preserved!)
echo "[+] Rebuilding and restarting Docker containers (preserving DB volume data)..."
docker compose down
if docker compose up -d --build; then
    echo "[+] Docker containers rebuilt and started successfully!"
else
    echo "[!] Failed to rebuild or start Docker containers."
fi

echo "===================================================="
echo "🎉 Migration complete! Showing logs for sentinel-panel (Ctrl+C to exit)..."
echo "===================================================="
docker logs -f sentinel-panel
