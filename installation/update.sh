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
USE_ROTATOR=1
TUNNEL_PID=""

cleanup_tunnel() {
    if [ -n "$TUNNEL_PID" ]; then
        kill -TERM "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
        TUNNEL_PID=""
    fi
    fuser -k -9 10818/tcp 10819/tcp 2>/dev/null || true
    pkill -9 -f "(proxy_rotator|sing-box.*failover|xray.*failover)" 2>/dev/null || true
}
trap cleanup_tunnel EXIT INT TERM

# Ensure standard unencrypted DNS resolution (UDP 53) without DoH blocking
ensure_unencrypted_dns() {
    local RESOLVE_OK=0

    # 1. Quick check if github.com resolves via system
    if command -v getent &>/dev/null && getent hosts github.com &>/dev/null; then
        RESOLVE_OK=1
    elif command -v nslookup &>/dev/null && nslookup github.com &>/dev/null; then
        RESOLVE_OK=1
    elif command -v python3 &>/dev/null && python3 -c "import socket; socket.gethostbyname('github.com')" &>/dev/null; then
        RESOLVE_OK=1
    elif command -v curl &>/dev/null && curl -s --connect-timeout 2 -I https://github.com &>/dev/null; then
        RESOLVE_OK=1
    fi

    if [ "$RESOLVE_OK" -eq 1 ]; then
        return 0
    fi

    echo -e "\033[0;33m[!] Системный DNS не смог разрешить github.com (возможно заблокирован DoH/DoT).\033[0m"
    echo -e "\033[0;36m[+] Переключение на стандартный нешифрованный DNS (8.8.8.8, 1.1.1.1, 8.8.4.4, UDP:53)...\033[0m"

    if [ "$EUID" -eq 0 ] && [ -w "/etc/resolv.conf" ]; then
        [ ! -f "/etc/resolv.conf.sentinel.bak" ] && cp -L /etc/resolv.conf /etc/resolv.conf.sentinel.bak 2>/dev/null || true

        if command -v resolvectl &>/dev/null; then
            resolvectl dnsovertls no 2>/dev/null || true
            resolvectl dns 8.8.8.8 1.1.1.1 8.8.4.4 2>/dev/null || true
        fi

        cat << 'EOF' > /tmp/resolv.conf.sentinel
nameserver 8.8.8.8
nameserver 1.1.1.1
nameserver 8.8.4.4
options timeout:2 attempts:2
EOF
        if [ -f "/etc/resolv.conf" ]; then
            grep -E '^(search|domain)' /etc/resolv.conf >> /tmp/resolv.conf.sentinel 2>/dev/null || true
            cp -f /tmp/resolv.conf.sentinel /etc/resolv.conf 2>/dev/null || true
            rm -f /tmp/resolv.conf.sentinel
        fi

        if command -v python3 &>/dev/null && python3 -c "import socket; socket.gethostbyname('github.com')" &>/dev/null; then
            echo -e "\033[0;32m[✓] DNS успешно переведен на стандартный нешифрованный режим (UDP:53). github.com доступен!\033[0m"
            return 0
        fi
    fi

    # Fallback: direct unencrypted DNS socket query via python
    if command -v python3 &>/dev/null; then
        local GH_IP
        GH_IP=$(python3 -c "
import socket
def query_dns(domain, dns_server='8.8.8.8'):
    packet = b'\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
    for part in domain.split('.'):
        packet += bytes([len(part)]) + part.encode('ascii')
    packet += b'\x00\x00\x01\x00\x01'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.5)
    sock.sendto(packet, (dns_server, 53))
    data, _ = sock.recvfrom(1024)
    sock.close()
    if len(data) > 12:
        for i in range(len(data) - 4):
            if data[i:i+2] == b'\x00\x01' and data[i+2:i+4] == b'\x00\x01':
                ip = socket.inet_ntoa(data[-4:])
                return ip
    return ''

for s in ['8.8.8.8', '1.1.1.1', '8.8.4.4', '9.9.9.9']:
    try:
        ip = query_dns('github.com', s)
        if ip and not ip.startswith('127.'):
            print(ip)
            break
    except Exception:
        continue
" 2>/dev/null || true)
        if [ -n "$GH_IP" ] && [ "$EUID" -eq 0 ] && [ -w "/etc/hosts" ]; then
            echo -e "\033[0;32m[✓] Разрешен IP github.com через прямой UDP DNS ($GH_IP). Запись в /etc/hosts...\033[0m"
            sed -i '/github.com/d' /etc/hosts 2>/dev/null || true
            echo "$GH_IP github.com api.github.com raw.githubusercontent.com" >> /etc/hosts
        fi
    fi
}

# Free ports 10818 and 10819 on startup
fuser -k -9 10818/tcp 10819/tcp 2>/dev/null || true
pkill -9 -f "(proxy_rotator|sing-box.*failover|xray.*failover)" 2>/dev/null || true

# Detect best python interpreter (.venv -> venv -> system python3)
PYTHON_BIN="python3"
for py_cand in "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/venv/bin/python3" "/opt/sentinel-panel/.venv/bin/python3" "$(command -v python3 2>/dev/null)"; do
    if [ -x "$py_cand" ]; then
        PYTHON_BIN="$py_cand"
        break
    fi
done

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --proxy|-p)
            PROXY_URL="$2"
            USE_ROTATOR=0
            shift 2
            ;;
        --no-proxy)
            NO_PROXY=1
            USE_ROTATOR=0
            shift
            ;;
        --auto|-y)
            AUTO_MODE=1
            shift
            ;;
        --help|-h)
            echo "Использование: sudo ./update.sh [опции]"
            echo "Опции:"
            echo "  --proxy <URL>   Использовать HTTP/HTTPS/SOCKS5 прокси (например, socks5://127.0.0.1:10808)"
            echo "  --no-proxy      Прямое подключение без прокси и ротатора"
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
fi

# Interactive Proxy Choice Menu (if in TTY terminal and not in auto mode)
if [ -t 0 ] && [ "$AUTO_MODE" -eq 0 ] && [ "$NO_PROXY" -eq 0 ]; then
    echo "===================================================="
    echo "🌐 НАСТРОЙКА СЕТИ И ПРОКСИ ДЛЯ ОБНОВЛЕНИЯ ПАНЕЛИ"
    echo "===================================================="
    echo "Выберите режим подключения к GitHub для загрузки релизов:"
    echo "  1) 🟢 Автоматический VPN / Прокси ротатор [Рекомендуется / По умолчанию]"
    echo "  2) 🌐 Прямое соединение + быстрые CDN-зеркала"
    echo "  3) 🔌 Использовать существующий HTTP / SOCKS5 прокси"
    echo "  4) ⏹️  Только прямое соединение (без прокси и без ротатора)"
    read -t 15 -p "Выберите вариант [1-4] (по умолчанию 1): " NET_CHOICE || NET_CHOICE="1"
    NET_CHOICE="${NET_CHOICE:-1}"
    echo ""
    case "$NET_CHOICE" in
        1)
            USE_ROTATOR=1
            ;;
        2)
            USE_ROTATOR=0
            ;;
        3)
            USE_ROTATOR=0
            read -p "Введите адрес прокси (например socks5://127.0.0.1:10808): " USER_P
            if [ -n "$USER_P" ]; then
                PROXY_URL="$USER_P"
            fi
            ;;
        4)
            USE_ROTATOR=0
            NO_PROXY=1
            ;;
        *)
            USE_ROTATOR=1
            ;;
    esac
fi

# Ensure standard unencrypted DNS resolution
ensure_unencrypted_dns

# Pre-fetch Sing-box / Xray proxy engine if needed for rotator
if [ "$USE_ROTATOR" -eq 1 ] && [ "$NO_PROXY" -eq 0 ]; then
    if [ ! -f "$SCRIPT_DIR/bin/sing-box" ] && [ ! -f "$SCRIPT_DIR/bin/xray" ] && ! command -v sing-box &>/dev/null && ! command -v xray &>/dev/null; then
        if [ -f "$SCRIPT_DIR/installation/fetch_proxy_core.sh" ]; then
            chmod +x "$SCRIPT_DIR/installation/fetch_proxy_core.sh"
            bash "$SCRIPT_DIR/installation/fetch_proxy_core.sh" "$SCRIPT_DIR/bin" --auto || true
        fi
    fi
fi

# Launch Rotator tunnel if requested
ROTATOR_ACTIVE_PROXY=""
if [ "$USE_ROTATOR" -eq 1 ] && [ "$NO_PROXY" -eq 0 ]; then
    echo -e "\033[0;36m[+] Запуск Sentinel Proxy Rotator для поиска рабочего VPN...\033[0m"
    ROTATOR_CMD=("$PYTHON_BIN" -m backend.proxy_rotator --port 10818)
    if [ -n "$PROXY_URL" ] && [[ "$PROXY_URL" =~ ^(ss|vless|vmess|trojan|hysteria2):// ]]; then
        ROTATOR_CMD+=(--node "$PROXY_URL")
    else
        ROTATOR_CMD+=(--find-and-start)
    fi

    # Launch in background and monitor PROXY_READY with real-time logs
    TEMP_ROTATOR_LOG="/tmp/panel_rotator_start.log"
    rm -f "$TEMP_ROTATOR_LOG"
    "${ROTATOR_CMD[@]}" > "$TEMP_ROTATOR_LOG" 2>&1 &
    TUNNEL_PID=$!

    LAST_LINE_COUNT=0
    for ((i=0; i<60; i++)); do
        if [ -f "$TEMP_ROTATOR_LOG" ]; then
            CURRENT_LINE_COUNT=$(wc -l < "$TEMP_ROTATOR_LOG" 2>/dev/null || echo 0)
            if [ "$CURRENT_LINE_COUNT" -gt "$LAST_LINE_COUNT" ]; then
                tail -n +"$((LAST_LINE_COUNT + 1))" "$TEMP_ROTATOR_LOG" 2>/dev/null | grep -v "PROXY_READY:" | while read -r line; do
                    [ -n "$line" ] && echo "    $line"
                done
                LAST_LINE_COUNT="$CURRENT_LINE_COUNT"
            fi
        fi

        if grep -q "PROXY_READY:" "$TEMP_ROTATOR_LOG" 2>/dev/null; then
            ROTATOR_ACTIVE_PROXY=$(grep -m1 "PROXY_READY:" "$TEMP_ROTATOR_LOG" | cut -d':' -f2- | tr -d '\r\n ')
            echo -e "\033[0;32m[✓] VPN-туннель успешно поднят на $ROTATOR_ACTIVE_PROXY!\033[0m"
            break
        fi

        if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
            echo -e "\033[0;31m[-] Процесс ротатора завершился до установления соединения. Лог:\033[0m"
            cat "$TEMP_ROTATOR_LOG" 2>/dev/null
            break
        fi
        sleep 0.5
    done

    if [ -z "$ROTATOR_ACTIVE_PROXY" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo -e "\033[0;33m[!] Превышено время ожидания ответа от VPN-нод. Продолжаем обновление без ротатора...\033[0m"
        kill -TERM "$TUNNEL_PID" 2>/dev/null || true
        TUNNEL_PID=""
    fi
fi

VALID_PROXY=""
FETCH_ARGS=()

if [ -n "$ROTATOR_ACTIVE_PROXY" ]; then
    VALID_PROXY="$ROTATOR_ACTIVE_PROXY"
elif [ -n "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
    if [[ "$PROXY_URL" =~ ^(http|https|socks4|socks5|socks5h):// ]]; then
        VALID_PROXY="$PROXY_URL"
    fi
fi

if [ -n "$VALID_PROXY" ]; then
    echo -e "\033[0;32m[✓] Активное прокси-соединение для обновления: $VALID_PROXY\033[0m"
    export http_proxy="$VALID_PROXY"
    export https_proxy="$VALID_PROXY"
    export all_proxy="$VALID_PROXY"
    export HTTP_PROXY="$VALID_PROXY"
    export HTTPS_PROXY="$VALID_PROXY"
    export ALL_PROXY="$VALID_PROXY"
    FETCH_ARGS+=("--proxy" "$VALID_PROXY")
else
    echo -e "\033[0;33m[ℹ️] Прокси не активен. Будут задействованы быстрые CDN-зеркала и прямые соединения.\033[0m"
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
    if git -c "http.proxy=" -c "https.proxy=" fetch "https://ghproxy.net/https://github.com/blackalex1/sentinel-panel.git" main 2>/dev/null && git reset --hard FETCH_HEAD; then
        echo "[+] Git успешно обновлен через быстрое зеркало ghproxy.net!"
        PULL_OK=1
    elif git -c "http.proxy=" -c "https.proxy=" fetch "https://gh-proxy.com/https://github.com/blackalex1/sentinel-panel.git" main 2>/dev/null && git reset --hard FETCH_HEAD; then
        echo "[+] Git успешно обновлен через зеркало gh-proxy.com!"
        PULL_OK=1
    elif git -c "http.proxy=" -c "https.proxy=" fetch "https://mirror.ghproxy.com/https://github.com/blackalex1/sentinel-panel.git" main 2>/dev/null && git reset --hard FETCH_HEAD; then
        echo "[+] Git успешно обновлен через mirror.ghproxy.com!"
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
# Kill old background server cores, but preserve active rotator tunnel
if [ -n "$TUNNEL_PID" ]; then
    pgrep -f "sing-box.*singbox_server" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
    pgrep -f "xray.*xray_server" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
else
    pkill -9 -f "sing-box" 2>/dev/null || true
    pkill -9 -f "xray" 2>/dev/null || true
fi

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

# Clean up proxy environment variables before running docker compose to allow direct build and pip install
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY

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
echo -e "\033[0;32m[✓] Обновление успешно завершено!\033[0m"
echo -e "[ℹ️] Подключение к живому потоку логов панели (Нажмите \033[1mCTRL+C\033[0m для выхода в терминал):"
echo "===================================================="
docker compose logs -f --tail 30 sentinel-panel
