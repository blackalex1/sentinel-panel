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

# 1. Fast bootstrap: auto-update git repository before launching updater
if [ -z "${BOOTSTRAPPED:-}" ] && [ -d .git ] && command -v git &>/dev/null; then
    OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || true)
    for remote in origin "https://github.com/blackalex1/sentinel-panel.git" "https://gh-proxy.com/https://github.com/blackalex1/sentinel-panel.git" "https://ghfast.top/https://github.com/blackalex1/sentinel-panel.git"; do
        if git fetch "$remote" main 2>/dev/null; then
            git reset --hard FETCH_HEAD 2>/dev/null || true
            break
        fi
    done
    NEW_HEAD=$(git rev-parse HEAD 2>/dev/null || true)
    if [ -n "$OLD_HEAD" ] && [ -n "$NEW_HEAD" ] && [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
        echo -e "\033[0;32m[✓]\033[0m Скрипт обновления обновлен из Git (${OLD_HEAD:0:7} -> ${NEW_HEAD:0:7})."
        echo -e "\n\033[1;36m============================================================\033[0m"
        echo -e "\033[1;36m📝 СПИСОК ИЗМЕНЕНИЙ (CHANGELOG: ${OLD_HEAD:0:7}..${NEW_HEAD:0:7}):\033[0m"
        echo -e "\033[1;36m============================================================\033[0m"
        git log --pretty=format:"  \033[1;33m•\033[0m \033[0;33m%h\033[0m \033[1;37m%s\033[0m \033[0;36m(%cr)\033[0m" "${OLD_HEAD}..${NEW_HEAD}" 2>/dev/null || true
        echo -e "\n\033[1;36m============================================================\033[0m\n"
        export BOOTSTRAPPED=1
        exec bash "$0" "$@"
    fi
fi

# Detect Python 3 interpreter
PYTHON_BIN=""
for candidate in python3 python /usr/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" &>/dev/null && "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "\033[0;31m[✗]\033[0m Python 3.8+ не найден на системе. Установите Python 3 для продолжения."
    exit 1
fi

# Execute Python Modular Updater
exec "$PYTHON_BIN" -m installation.updater.main "$@"
