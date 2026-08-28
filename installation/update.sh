#!/bin/bash

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root (use sudo)"
  exit 1
fi

# Navigate to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

PROXY_URL=""
NO_PROXY=0
AUTO_MODE=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --proxy|-p)
            PROXY_URL="$2"
            shift 2
            ;;
        --no-proxy)
            NO_PROXY=1
            shift
            ;;
        --auto|-y)
            AUTO_MODE=1
            shift
            ;;
        --help|-h)
            echo "Использование: sudo ./update.sh [опции]"
            echo "Опции:"
            echo "  --proxy <URL>   Использовать HTTP/HTTPS/SOCKS5 прокси (например, socks5://127.0.0.1:10808 или http://127.0.0.1:7890)"
            echo "  --no-proxy      Игнорировать прокси из .env и окружения"
            echo "  --auto, -y      Автоматический режим обновления без интерактива"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Check PROXY_URL from .env if not specified via CLI
if [ -z "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
    for env_file in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/config/.env"; do
        if [ -f "$env_file" ]; then
            ENV_P=$(grep -E '^[[:space:]]*PROXY_URL=' "$env_file" 2>/dev/null | cut -d'=' -f2- | tr -d '"'\'' ')
            if [ -n "$ENV_P" ]; then
                PROXY_URL="$ENV_P"
                break
            fi
        fi
    done
    if [ -z "$PROXY_URL" ]; then
        PROXY_URL="${HTTPS_PROXY:-${HTTP_PROXY:-${ALL_PROXY:-${https_proxy:-${http_proxy:-${all_proxy:-}}}}}}"
    fi
fi

# Interactive Proxy Choice Menu (if in TTY terminal and not in auto mode)
if [ -t 0 ] && [ "$AUTO_MODE" -eq 0 ] && [ -z "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
    echo "===================================================="
    echo "🌐 НАСТРОЙКА СЕТИ И ПРОКСИ ДЛЯ ОБНОВЛЕНИЯ"
    echo "===================================================="
    echo "Выберите режим подключения к GitHub для загрузки релизов и обновлений:"
    echo "  1) 🟢 Прямое соединение + быстрые CDN-зеркала [Рекомендуется / По умолчанию]"
    echo "  2) 🔌 Использовать HTTP / SOCKS5 прокси (например, socks5://127.0.0.1:10808)"
    echo "  3) ⏹️  Только прямое соединение (без зеркал и без прокси)"
    read -t 15 -p "Выберите вариант [1-3] (по умолчанию 1): " NET_CHOICE || NET_CHOICE="1"
    NET_CHOICE="${NET_CHOICE:-1}"
    echo ""
    case "$NET_CHOICE" in
        2)
            read -p "Введите адрес прокси (например socks5://127.0.0.1:10808): " USER_P
            if [ -n "$USER_P" ]; then
                PROXY_URL="$USER_P"
            fi
            ;;
        3)
            NO_PROXY=1
            ;;
        *)
            ;;
    esac
fi

VALID_PROXY=""
FETCH_ARGS=()
if [ -n "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
    if [[ "$PROXY_URL" =~ ^(http|https|socks4|socks5|socks5h):// ]]; then
        VALID_PROXY="$PROXY_URL"
        echo "[+] Настроено подключение через прокси: $VALID_PROXY"
        export http_proxy="$VALID_PROXY"
        export https_proxy="$VALID_PROXY"
        export all_proxy="$VALID_PROXY"
        export HTTP_PROXY="$VALID_PROXY"
        export HTTPS_PROXY="$VALID_PROXY"
        export ALL_PROXY="$VALID_PROXY"
        FETCH_ARGS+=("--proxy" "$VALID_PROXY")
    else
        echo "[ℹ️] В конфигурации указана VPN-нода (${PROXY_URL%%:*}:...). Будут задействованы быстрые зеркала и прямые соединения."
    fi
fi

if [ "$AUTO_MODE" -eq 1 ]; then
    FETCH_ARGS+=("--auto")
fi

echo "===================================================="
echo "🔄 UPDATING SENTINEL PANEL"
echo "===================================================="

# 1. Pull latest updates from Git
echo "[+] Pulling latest updates from Git..."
git remote set-url origin https://github.com/blackalex1/sentinel-panel.git 2>/dev/null
OLD_HEAD=$(git rev-parse HEAD 2>/dev/null)

pull_panel_git() {
    if [ -n "$VALID_PROXY" ]; then
        git -c "http.proxy=$VALID_PROXY" -c "https.proxy=$VALID_PROXY" fetch origin main && git reset --hard origin/main
    else
        git fetch origin main && git reset --hard origin/main
    fi
}

PULL_OK=0
if pull_panel_git; then
    PULL_OK=1
else
    echo "[!] Прямое подключение к GitHub не удалось. Пробуем через быстрое зеркало..."
    if git fetch "https://ghproxy.net/https://github.com/blackalex1/sentinel-panel.git" main 2>/dev/null && git reset --hard FETCH_HEAD; then
        echo "[+] Git успешно обновлен через быстрое зеркало!"
        PULL_OK=1
    elif git fetch "https://gh-proxy.com/https://github.com/blackalex1/sentinel-panel.git" main 2>/dev/null && git reset --hard FETCH_HEAD; then
        echo "[+] Git успешно обновлен через зеркало gh-proxy.com!"
        PULL_OK=1
    fi
fi

if [ "$PULL_OK" -eq 1 ]; then
    NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)
    if [ "$OLD_HEAD" != "$NEW_HEAD" ] && [ -n "$OLD_HEAD" ]; then
        echo "[+] Changes pulled:"
        git diff --stat "$OLD_HEAD" "$NEW_HEAD"
    else
        echo "[+] Already up to date."
    fi
    echo "[+] Git update completed successfully."
else
    echo "[!] Git update failed. Continuing with local codebase..."
fi

# 2. Update Sentinel-Core engine binary from sentinel-core repository
echo "[+] Updating sentinel-core engine..."
if [ -f "$SCRIPT_DIR/installation/fetch_core.sh" ]; then
    chmod +x "$SCRIPT_DIR/installation/fetch_core.sh"
    bash "$SCRIPT_DIR/installation/fetch_core.sh" "$SCRIPT_DIR/bin" "${FETCH_ARGS[@]}"
fi

# 3. Rebuild and restart Docker containers
echo "[+] Rebuilding and restarting Docker containers..."
pkill -9 -f "sing-box" 2>/dev/null || true
pkill -9 -f "xray" 2>/dev/null || true
docker ps -a --filter "name=spectre" -q | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=sentinel" -q | xargs -r docker rm -f 2>/dev/null || true
docker compose down --remove-orphans 2>/dev/null || true

# Auto-migrate legacy database volume (spectre-panel_pgdata / panel_pgdata / installation_pgdata -> sentinel-panel_pgdata)
for v in spectre-panel_pgdata panel_pgdata installation_pgdata; do
    if docker volume inspect "$v" &>/dev/null; then
        echo "[+] Found legacy database volume '$v'."
        if ! docker volume inspect sentinel-panel_pgdata &>/dev/null; then
            echo "[+] Migrating data from '$v' to 'sentinel-panel_pgdata'..."
            docker volume create --label "com.docker.compose.project=sentinel-panel" --label "com.docker.compose.volume=pgdata" sentinel-panel_pgdata >/dev/null 2>&1
            docker run --rm -v "$v":/from -v sentinel-panel_pgdata:/to postgres:16-alpine sh -c "rm -rf /to/* 2>/dev/null || true; cp -a /from/. /to/"
            echo "[+] Original database volume migrated to sentinel-panel_pgdata successfully!"
        fi
        echo "[+] Cleaning up legacy volume '$v'..."
        docker volume rm -f "$v" >/dev/null 2>&1 || true
    fi
done

# Ensure sentinel-panel_pgdata has compose labels to eliminate 'not created by Docker Compose' warning
if docker volume inspect sentinel-panel_pgdata &>/dev/null; then
    LABEL_CHECK=$(docker volume inspect sentinel-panel_pgdata --format '{{index .Labels "com.docker.compose.volume"}}' 2>/dev/null || true)
    if [ "$LABEL_CHECK" != "pgdata" ]; then
        echo "[+] Adding Docker Compose labels to 'sentinel-panel_pgdata'..."
        docker volume create --label "com.docker.compose.project=sentinel-panel" --label "com.docker.compose.volume=pgdata" sentinel-panel_pgdata_migrated >/dev/null 2>&1
        docker run --rm -v sentinel-panel_pgdata:/from -v sentinel-panel_pgdata_migrated:/to postgres:16-alpine sh -c "cp -a /from/. /to/"
        docker volume rm -f sentinel-panel_pgdata >/dev/null 2>&1
        docker volume create --label "com.docker.compose.project=sentinel-panel" --label "com.docker.compose.volume=pgdata" sentinel-panel_pgdata >/dev/null 2>&1
        docker run --rm -v sentinel-panel_pgdata_migrated:/from -v sentinel-panel_pgdata:/to postgres:16-alpine sh -c "cp -a /from/. /to/"
        docker volume rm -f sentinel-panel_pgdata_migrated >/dev/null 2>&1
    fi
fi

if docker compose up -d --build; then
    echo "[+] Docker containers rebuilt and started successfully!"
else
    echo "[!] Failed to rebuild or start Docker containers."
fi

# 4. Update and restart host agent system service (sentinel-agent)
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
fi

echo "===================================================="
echo "[+] Update process complete! Checking services status..."
echo "===================================================="
docker compose ps
systemctl status sentinel-agent --no-pager -n 5 2>/dev/null || true
