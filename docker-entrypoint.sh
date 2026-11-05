#!/usr/bin/env bash
set -e

# ==============================================================================
# Sentinel Panel - Docker Privilege Dropping & Permission Normalization
# ==============================================================================

# 1. Normalize permissions on host-mounted volumes
# Automatically adjusts ownership and permissions so appuser (UID 1000) has full read/write access
for dir in "/app/config" "/app/bin" "/app/backups" "/var/run/sentinel" "/app/frontend/decoy"; do
    if [ -d "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || true
        chmod 775 "$dir" 2>/dev/null || true
    fi
done

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
