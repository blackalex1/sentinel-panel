#!/usr/bin/env bash
set -e

# ==============================================================================
# Sentinel Panel - Docker Privilege Dropping & Permission Normalization
# ==============================================================================

# 1. Normalize permissions on host-mounted volumes
# Automatically adjusts ownership and permissions so appuser (UID 1000) has full read/write access
for dir in "/app/config" "/app/bin" "/app/backups" "/app/frontend/decoy"; do
    if [ -d "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || true
        chmod -R 775 "$dir" 2>/dev/null || true
    fi
done

# Ensure binary directory has executable and readable permissions for appuser
if [ -d "/app/bin" ]; then
    chown -R appuser:appuser /app/bin 2>/dev/null || true
    chmod -R 755 /app/bin 2>/dev/null || true
fi

# Ensure socket directory allows IPC communication with host agent
if [ -d "/var/run/sentinel" ]; then
    chown -R appuser:appuser /var/run/sentinel 2>/dev/null || true
    chmod 777 /var/run/sentinel 2>/dev/null || true
    if [ -e "/var/run/sentinel/agent.sock" ]; then
        chmod 666 /var/run/sentinel/agent.sock 2>/dev/null || true
    fi
fi

if [ -f "/app/config/.env" ]; then
    chown appuser:appuser "/app/config/.env" 2>/dev/null || true
    chmod 660 "/app/config/.env" 2>/dev/null || true
fi

# Ensure app directory permissions
chown -R appuser:appuser /app/updater 2>/dev/null || true

# 2. Grant capabilities to Python interpreter for network binding and raw sockets
PYTHON_BIN="/app/.venv/bin/python"
if [ -f "$PYTHON_BIN" ] && command -v setcap >/dev/null 2>&1; then
    setcap 'cap_net_bind_service,cap_net_admin=+ep' "$PYTHON_BIN" 2>/dev/null || true
fi

# Also grant capabilities to proxy core binaries in /app/bin if present
for bin_file in "/app/bin/sing-box" "/app/bin/xray" "/app/bin/sentinel-core"; do
    if [ -f "$bin_file" ] && command -v setcap >/dev/null 2>&1; then
        setcap 'cap_net_bind_service,cap_net_admin=+ep' "$bin_file" 2>/dev/null || true
    fi
done

# 3. Drop root privileges and execute the main application as appuser
if [ "$(id -u)" = "0" ]; then
    exec gosu appuser "$@"
fi

exec "$@"
