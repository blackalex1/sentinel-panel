#!/usr/bin/env bash
# ==============================================================================
# Sentinel Panel - Update Launcher
# Delegates execution to modular Python updater (installation/updater/main.py)
# ==============================================================================

set -e

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# Ensure script is run with root privileges
if [ "$EUID" -ne 0 ]; then
    echo -e "\033[0;31m[✗]\033[0m Для обновления панели требуются права root (sudo)."
    echo -e "\033[1;33mПожалуйста, запустите:\033[0m sudo ./update.sh"
    exit 1
fi

export PYTHONUNBUFFERED=1

# Configure safe.directory for Git when running under sudo
git config --global --add safe.directory "$SCRIPT_DIR" 2>/dev/null || true
git config --global --add safe.directory "*" 2>/dev/null || true

# 1. Fast bootstrap: auto-update git repository before launching updater
if [ -z "${BOOTSTRAPPED:-}" ] && [ -d .git ] && command -v git &>/dev/null; then
    echo -e "\033[0;36m[+] Проверка обновлений Git-репозитория...\033[0m"
    OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || true)
    
    # Check for proxy configuration in .env
    FETCH_ARGS=(-c "safe.directory=*" -c "http.connectTimeout=4" -c "http.timeout=8")
    for env_f in "config/.env" ".env"; do
        if [ -f "$env_f" ]; then
            P_URL=$(grep -E '^[[:space:]]*PROXY_URL=' "$env_f" 2>/dev/null | cut -d'=' -f2- | tr -d '"'\'' ')
            if [ -n "$P_URL" ]; then
                FETCH_ARGS+=(-c "http.proxy=$P_URL" -c "https.proxy=$P_URL")
                break
            fi
        fi
    done

    # Fetch directly from official GitHub repository with proxy and direct fallback
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
        echo -e "\033[0;32m[✓]\033[0m Скрипт обновления обновлен из Git (${OLD_HEAD:0:7} -> ${NEW_HEAD:0:7})."
        echo -e "\n\033[1;36m============================================================\033[0m"
        echo -e "\033[1;36m📝 СПИСОК ИЗМЕНЕНИЙ (CHANGELOG: ${OLD_HEAD:0:7}..${NEW_HEAD:0:7}):\033[0m"
        echo -e "\033[1;36m============================================================\033[0m"
        git log --color=always --pretty=format:"  %C(yellow)•%C(reset) %C(bold yellow)%h%C(reset) %C(bold white)%s%C(reset) %C(cyan)(%cr)%C(reset)" "${OLD_HEAD}..${NEW_HEAD}" 2>/dev/null || true
        echo -e "\n\033[1;36m------------------------------------------------------------\033[0m"
        echo -e "\033[1;33m📊 ИЗМЕНЕННЫЕ ФАЙЛЫ:\033[0m"
        echo -e "\033[1;36m------------------------------------------------------------\033[0m"
        git diff --stat --color=always "${OLD_HEAD}..${NEW_HEAD}" 2>/dev/null || true
        echo -e "\033[1;36m============================================================\033[0m\n"
        export BOOTSTRAPPED=1
        exec bash "$0" "$@"
    fi
fi

# 2. Detect Python 3 interpreter
PYTHON_BIN=""
if [ -f "backend/venv/bin/python" ]; then
    PYTHON_BIN="backend/venv/bin/python"
else
    for candidate in python3 python /usr/bin/python3 /usr/local/bin/python3; do
        if command -v "$candidate" &>/dev/null && "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    echo -e "\033[0;31m[✗]\033[0m Python 3.8+ не найден на системе. Установите Python 3 для продолжения."
    exit 1
fi

# 3. Clean proxy environment and launch modern modular updater
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
BOOTSTRAP_FLAG=""
if [ -n "${BOOTSTRAPPED:-}" ]; then
    BOOTSTRAP_FLAG="--bootstrapped"
fi

exec "$PYTHON_BIN" -m installation.updater.main $BOOTSTRAP_FLAG "$@"
