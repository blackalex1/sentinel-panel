#!/usr/bin/env bash
# ==============================================================================
# 🚀 Sentinel Universal Updater - Master Launcher
# Executes the modular Python updater for Sentinel Controller and Sentinel Panel
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Root verification
if [ "$EUID" -ne 0 ]; then
    echo -e "\033[0;31m[✖]\033[0m Для запуска обновления требуются права root (sudo)."
    echo -e "\033[1;33mПожалуйста, запустите:\033[0m sudo ./update.sh"
    exit 1
fi

export PYTHONUNBUFFERED=1

# Clean up any lingering updater proxy processes on exit / interrupt
cleanup_updater_processes() {
    pkill -9 -f "_failover_" 2>/dev/null || true
    pkill -9 -f "proxy_rotator.py" 2>/dev/null || true
    pkill -9 -f "singbox_failover" 2>/dev/null || true
    pkill -9 -f "xray_failover" 2>/dev/null || true
}
trap cleanup_updater_processes EXIT INT TERM HUP

# 2. Configure Git safe directory
git config --global --add safe.directory "$SCRIPT_DIR" 2>/dev/null || true
git config --global --add safe.directory "*" 2>/dev/null || true

# 3. Fast bootstrap: auto-update git repository if .git exists
if [ -z "${BOOTSTRAPPED:-}" ] && [ -d .git ] && command -v git &>/dev/null; then
    OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || true)
    
    # Check for proxy configuration in .env
    FETCH_ARGS=(-c "safe.directory=*" -c "http.connectTimeout=4" -c "http.timeout=8")
    for env_f in "bot/config/.env" "config/.env" ".env"; do
        if [ -f "$env_f" ]; then
            P_URL=$(grep -E '^[[:space:]]*PROXY_URL=' "$env_f" 2>/dev/null | cut -d'=' -f2- | tr -d '"'\'' ')
            if [ -n "$P_URL" ]; then
                FETCH_ARGS+=(-c "http.proxy=$P_URL" -c "https.proxy=$P_URL")
                break
            fi
        fi
    done

    FETCH_OK=0
    if timeout 10 git "${FETCH_ARGS[@]}" fetch origin main 2>/dev/null; then
        FETCH_OK=1
    elif timeout 10 git -c "safe.directory=*" -c "http.proxy=" -c "https.proxy=" fetch origin main 2>/dev/null; then
        FETCH_OK=1
    fi

    if [ "$FETCH_OK" -eq 1 ]; then
        git reset --hard FETCH_HEAD 2>/dev/null || true
    fi
    NEW_HEAD=$(git rev-parse HEAD 2>/dev/null || true)
    if [ -n "$OLD_HEAD" ] && [ -n "$NEW_HEAD" ] && [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
        echo -e "\033[0;32m[✔]\033[0m Скрипт обновления обновлен из Git (${OLD_HEAD:0:7} -> ${NEW_HEAD:0:7})."
        export SENTINEL_OLD_HEAD="$OLD_HEAD"
        export SENTINEL_NEW_HEAD="$NEW_HEAD"
        export BOOTSTRAPPED=1
        exec bash "$0" "$@"
    fi
fi

# 4. Detect Python 3.8+ interpreter
PYTHON_BIN=""
for candidate in \
    "$SCRIPT_DIR/backend/venv/bin/python" \
    "$SCRIPT_DIR/bot/venv/bin/python" \
    "$SCRIPT_DIR/.venv/bin/python" \
    python3 python /usr/bin/python3 /usr/local/bin/python3; do
    if [ -f "$candidate" ] || command -v "$candidate" &>/dev/null; then
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "\033[0;31m[✖]\033[0m Python 3.8+ не найден на системе."
    echo -e "Пожалуйста, установите Python 3: apt-get update && apt-get install -y python3 python3-venv"
    exit 1
fi

# 5. Clean proxy environment variables and run modular updater
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
BOOTSTRAP_FLAG=""
if [ -n "${BOOTSTRAPPED:-}" ]; then
    BOOTSTRAP_FLAG="--bootstrapped"
fi

export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

exec "$PYTHON_BIN" -m updater.main $BOOTSTRAP_FLAG "$@"
