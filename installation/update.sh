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
echo "🔄 UPDATING SPECTRE PANEL"
echo "===================================================="

# 1. Pull latest updates from Git
echo "[+] Pulling latest updates from Git..."
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

# 3. Restart spectre-agent service
echo "[+] Restarting spectre-agent system service..."
if systemctl is-active --quiet spectre-agent; then
    systemctl restart spectre-agent
    echo "[+] spectre-agent service restarted successfully!"
else
    # If the service is not active, try starting it or warn if not installed
    if [ -f "/etc/systemd/system/spectre-agent.service" ]; then
        systemctl daemon-reload
        systemctl enable spectre-agent
        systemctl start spectre-agent
        echo "[+] spectre-agent service enabled and started!"
    else
        echo "[!] spectre-agent service is not installed on this host."
    fi
fi

echo "===================================================="
echo "[+] Update process complete! Showing logs for spectre-panel (Ctrl+C to exit)..."
echo "===================================================="
docker logs -f spectre-panel
