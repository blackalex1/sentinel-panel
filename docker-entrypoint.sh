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

# 2. Grant capabilities to Python interpreter for network binding (<1024 ports like 80/443) and raw sockets
sysctl -w net.ipv4.ip_unprivileged_port_start=0 2>/dev/null || true
echo 0 > /proc/sys/net/ipv4/ip_unprivileged_port_start 2>/dev/null || true

for py_path in "/app/.venv/bin/python" "$(command -v python3 2>/dev/null)" "$(command -v python 2>/dev/null)"; do
    if [ -n "$py_path" ] && [ -e "$py_path" ]; then
        REAL_PY="$(readlink -f "$py_path" 2>/dev/null || echo "$py_path")"
        if [ -f "$REAL_PY" ] && command -v setcap >/dev/null 2>&1; then
            setcap 'cap_net_bind_service,cap_net_admin=+ep' "$REAL_PY" 2>/dev/null || true
        fi
    fi
done

# Also grant capabilities to proxy core binaries in /app/bin if present
for bin_file in "/app/bin/sing-box" "/app/bin/xray" "/app/bin/sentinel-core"; do
    if [ -f "$bin_file" ] && command -v setcap >/dev/null 2>&1; then
        REAL_BIN="$(readlink -f "$bin_file" 2>/dev/null || echo "$bin_file")"
        setcap 'cap_net_bind_service,cap_net_admin=+ep' "$REAL_BIN" 2>/dev/null || true
    fi
done

# Grant CAP_NET_RAW to system ping utility so unprivileged appuser can send ICMP probes
if command -v ping >/dev/null 2>&1 && command -v setcap >/dev/null 2>&1; then
    PING_BIN="$(readlink -f "$(command -v ping)")"
    if [ -f "$PING_BIN" ]; then
        setcap 'cap_net_raw=+ep' "$PING_BIN" 2>/dev/null || true
    fi
fi

# 3. Drop root privileges and execute the main application as appuser
if [ "$(id -u)" = "0" ]; then
    exec gosu appuser "$@"
fi

exec "$@"
