#!/bin/bash

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root (use sudo)"
  exit 1
fi

# Get the absolute path of the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Ensure required host dependencies are installed on Debian/Ubuntu
if command -v apt-get &>/dev/null; then
    MISSING_PKGS=""
    for pkg_cmd in "git:git" "curl:curl" "python3:python3" "tar:tar" "unzip:unzip" "openssl:openssl"; do
        cmd="${pkg_cmd%%:*}"
        pkg="${pkg_cmd##*:}"
        if ! command -v "$cmd" &>/dev/null; then
            MISSING_PKGS="$MISSING_PKGS $pkg"
        fi
    done
    if [ -n "$MISSING_PKGS" ]; then
        echo "[+] Installing missing host packages:$MISSING_PKGS..."
        apt-get update -y && apt-get install -y $MISSING_PKGS
    fi
fi

# If run via curl pipe (BASH_SOURCE is /dev/fd/..), check if current directory or /opt/sentinel-panel has the repo
if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    if [ -f "./docker-compose.yml" ]; then
        SCRIPT_DIR="$(pwd)"
    elif [ -f "/opt/sentinel-panel/docker-compose.yml" ]; then
        SCRIPT_DIR="/opt/sentinel-panel"
    else
        echo "[+] Installing git if missing..."
        which git &>/dev/null || (apt-get update && apt-get install -y git)
        SCRIPT_DIR="/opt/sentinel-panel"
        echo "[+] Cloning sentinel-panel into $SCRIPT_DIR..."
        git clone https://github.com/blackalex1/sentinel-panel.git "$SCRIPT_DIR"
    fi
fi
cd "$SCRIPT_DIR" || exit 1
echo "[+] Project directory detected: $SCRIPT_DIR"

# Ensure git remote URL points to the repository
git -C "$SCRIPT_DIR" remote set-url origin https://github.com/blackalex1/sentinel-panel.git 2>/dev/null

# 1. Update sentinel-agent.service configuration dynamically
SERVICE_TEMPLATE="$SCRIPT_DIR/host/sentinel-agent.service"
SERVICE_DEST="/etc/systemd/system/sentinel-agent.service"

if [ -f "$SERVICE_TEMPLATE" ] && command -v systemctl &>/dev/null && [ -d "/etc/systemd/system" ]; then
    echo "[+] Configuring systemd service at $SERVICE_DEST..."
    sed "s|/opt/sentinel-panel|$SCRIPT_DIR|g" "$SERVICE_TEMPLATE" > "$SERVICE_DEST"

    echo "[+] Reloading systemd..."
    systemctl daemon-reload
    echo "[+] Enabling sentinel-agent service..."
    systemctl enable sentinel-agent
    echo "[+] Starting sentinel-agent service..."
    systemctl restart sentinel-agent

    if systemctl is-active --quiet sentinel-agent; then
        echo "[+] sentinel-agent service started successfully!"
    else
        echo "[!] Failed to start sentinel-agent service. Check logs: journalctl -u sentinel-agent"
    fi
fi

# 2. Interactive Configuration for config/.env
ENV_FILE="$SCRIPT_DIR/config/.env"
mkdir -p "$SCRIPT_DIR/config"
chmod 700 "$SCRIPT_DIR/config"

EXISTING_ADMIN_USER=""
EXISTING_ADMIN_PASS=""
if [ -f "$ENV_FILE" ]; then
    EXISTING_ADMIN_USER=$(grep -E "^ADMIN_USERNAME=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '\r\n ')
    EXISTING_ADMIN_PASS=$(grep -E "^ADMIN_PASSWORD=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '\r\n ')
    read -p "[?] Existing configuration found at config/.env. Do you want to reconfigure it? (y/N): " RECONFIRM
    if [[ "$RECONFIRM" =~ ^[yY]$ ]]; then
        echo "[+] Removing old configuration..."
        rm -f "$ENV_FILE"
        EXISTING_ADMIN_USER=""
        EXISTING_ADMIN_PASS=""
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "===================================================="
    echo "⚙️  Interactive Configuration of VPN Panel Settings"
    echo "===================================================="

    # 1. Telegram Bot Token (Optional)
    read -p "Enter Telegram Bot Token (e.g. 123456:ABC...) [leave empty to configure later]: " TG_TOKEN

    # 2. Telegram Admin IDs (Optional)
    read -p "Enter Telegram Admin IDs (comma-separated, e.g. 1234567890) [leave empty to configure later]: " TG_IDS

    # 3. Web Admin Username
    read -p "Enter Web Panel Admin Username [leave empty to auto-generate]: " ADMIN_USER
    if [ -z "$ADMIN_USER" ]; then
        ADMIN_USER="admin_$(openssl rand -hex 3 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(3))" 2>/dev/null || echo "user$$")"
        echo "[+] Auto-generated Admin Username: $ADMIN_USER"
    fi

    # 4. Web Admin Password
    read -s -p "Enter Web Panel Admin Password [leave empty to auto-generate]: " ADMIN_PASS
    echo ""
    if [ -z "$ADMIN_PASS" ]; then
        ADMIN_PASS=$(openssl rand -hex 10 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(10))" 2>/dev/null || echo "pass$$")
        echo "[+] Auto-generated Admin Password: $ADMIN_PASS"
    fi

    # 5. Web Panel Port
    read -p "Enter Web Panel Port [leave empty to auto-generate]: " PORT
    if [ -z "$PORT" ]; then
        PORT=$(( 10000 + RANDOM % 50000 ))
        echo "[+] Auto-generated Panel Port: $PORT"
    fi

    # Auto-generate API Token, Secret Path, and DB passwords for security
    RAND_API_TOKEN=$(openssl rand -hex 24 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(24))" 2>/dev/null || echo "tok$$")
    RAND_SECRET_PATH="ui_$(openssl rand -hex 6 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(6))" 2>/dev/null || echo "path$$")"
    DB_ADMIN_PASS=$(openssl rand -hex 12 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(12))" 2>/dev/null || echo "dbadmin$$")
    DB_APP_PASS=$(openssl rand -hex 12 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(12))" 2>/dev/null || echo "dbapp$$")

    # Write config file
    cat <<EOF > "$ENV_FILE"
# Настройки веб-панели
PANEL_PORT=$PORT
PANEL_SECRET_PATH=$RAND_SECRET_PATH

# Учетные данные по умолчанию
ADMIN_USERNAME=$ADMIN_USER
ADMIN_PASSWORD=$ADMIN_PASS

# Токен для интеграции с контроллером
API_TOKEN=$RAND_API_TOKEN

# Настройки СУБД PostgreSQL (Параметры безопасности)
POSTGRES_DB=sentinel_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$DB_ADMIN_PASS

DB_APP_USER=sentinel_app
DB_APP_PASSWORD=$DB_APP_PASS

# Строки подключения к БД (Администратор DDL / Приложение DML)
DATABASE_ADMIN_URL=postgresql://postgres:$DB_ADMIN_PASS@127.0.0.1:5432/sentinel_db
DATABASE_URL=postgresql://sentinel_app:$DB_APP_PASS@127.0.0.1:5432/sentinel_db
EOF
    chmod 600 "$ENV_FILE"

    echo "----------------------------------------------------"
    echo "[+] config/.env successfully configured!"
    echo "[+] Auto-generated Panel Secret Path: /$RAND_SECRET_PATH/"
    echo "[+] Auto-generated Controller API Token: $RAND_API_TOKEN"
    echo "===================================================="
else
    echo "[+] Existing configuration found at config/.env. Skipping interactive configuration."
fi

# Pre-cache credentials and ports BEFORE container starts
# (as seeding.py securely wipes plaintext admin credentials from .env)
FINAL_PORT=$(grep -E "^PANEL_PORT=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '\r\n ')
FINAL_SECRET_PATH=$(grep -E "^PANEL_SECRET_PATH=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '\r\n ')
FINAL_ADMIN_USER=$(grep -E "^ADMIN_USERNAME=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '\r\n ')
FINAL_ADMIN_PASS=$(grep -E "^ADMIN_PASSWORD=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '\r\n ')

[ -z "$FINAL_PORT" ] && FINAL_PORT="${PORT:-2053}"
[ -z "$FINAL_SECRET_PATH" ] && FINAL_SECRET_PATH="${RAND_SECRET_PATH:-ui}"
[ -z "$FINAL_ADMIN_USER" ] && FINAL_ADMIN_USER="${ADMIN_USER:-${EXISTING_ADMIN_USER:-admin}}"
[ -z "$FINAL_ADMIN_PASS" ] && FINAL_ADMIN_PASS="${ADMIN_PASS:-${EXISTING_ADMIN_PASS}}"

# 3. Check for Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    echo "[!] Docker is not installed. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm -f get-docker.sh
fi

if ! docker compose version &> /dev/null; then
    echo "[!] docker compose command not found. Installing docker-compose-plugin..."
    if command -v apt-get &>/dev/null; then
        apt-get update && apt-get install -y docker-compose-plugin
    fi
fi

# 4. Fetch latest Sentinel-Core engine (Go binary + C-FFI shared library)
echo "[+] Fetching latest Sentinel-Core engine..."
if [ -f "$SCRIPT_DIR/installation/fetch_core.sh" ]; then
    bash "$SCRIPT_DIR/installation/fetch_core.sh" "$SCRIPT_DIR/bin" --auto
else
    echo "[!] Warning: installation/fetch_core.sh not found."
fi

# 5. Fetch latest proxy engines (Sing-box, Xray-core, Hysteria 2, and geodata)
echo "[+] Fetching latest proxy engines (Sing-box, Xray-core, Hysteria 2)..."
if [ -f "$SCRIPT_DIR/installation/fetch_proxy_core.sh" ]; then
    bash "$SCRIPT_DIR/installation/fetch_proxy_core.sh" "$SCRIPT_DIR/bin" --auto
else
    echo "[!] Warning: installation/fetch_proxy_core.sh not found."
fi

# Ensure executable permissions for all binaries in bin/
chmod +x "$SCRIPT_DIR/bin"/* 2>/dev/null || true

# Verify installed core components
echo "[+] Verifying core binaries in $SCRIPT_DIR/bin..."
for comp in "sentinel-core" "sing-box" "xray"; do
    if [ -f "$SCRIPT_DIR/bin/$comp" ] || [ -f "$SCRIPT_DIR/bin/$comp.exe" ]; then
        echo "  [✓] $comp found"
    else
        echo "  [!] Notice: $comp not found in $SCRIPT_DIR/bin"
    fi
done
if [ -f "$SCRIPT_DIR/bin/libsentinel-core.so" ] || [ -f "$SCRIPT_DIR/bin/sentinel-core.dll" ] || [ -f "$SCRIPT_DIR/bin/sentinel-core.so" ]; then
    echo "  [✓] libsentinel-core shared library found"
else
    echo "  [!] Notice: libsentinel-core shared library not found in $SCRIPT_DIR/bin"
fi

# 6. Build and run Docker containers
echo "[+] Starting Docker Compose..."
cd "$SCRIPT_DIR" || exit 1
docker compose build
docker compose up -d

# 7. Seed Telegram settings in the database after container startup if provided
if [ -n "$TG_TOKEN" ] || [ -n "$TG_IDS" ]; then
    echo "[+] Saving Telegram settings to the database..."
    for i in {1..10}; do
        if docker compose exec -T sentinel-panel python -c "from backend.database import set_setting; set_setting('telegram_bot_token', '$TG_TOKEN'); set_setting('telegram_admin_ids', '$TG_IDS')" &>/dev/null; then
            echo "[+] Telegram settings successfully saved to database."
            break
        fi
        echo "[-] Waiting for database initialization ($i/10)..."
        sleep 3
    done
fi

# Query backup password from database (wait up to 30s for database readiness if needed)
FINAL_BACKUP_PASS=""
for i in {1..15}; do
    FINAL_BACKUP_PASS=$(docker compose exec -T sentinel-panel python -c "from backend.database import get_setting; print(get_setting('backup_password', ''))" 2>/dev/null | tr -d '\r\n ')
    if [ -n "$FINAL_BACKUP_PASS" ]; then
        break
    fi
    sleep 2
done

# Try to get public IP, fallback to primary interface IP or placeholder
SERVER_IP=$(curl -s https://ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || ip route get 1 2>/dev/null | awk 'BEGIN {found=0} {for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); found=1; exit}} END {if(!found) exit 1}' 2>/dev/null || echo "YOUR_SERVER_IP")

echo ""
echo "===================================================="
echo "🎉 Installation complete! Services started."
echo "===================================================="
echo "🌐 Access Web Panel UI:"
echo "   Link:     https://${SERVER_IP}:${FINAL_PORT}/${FINAL_SECRET_PATH}/"
echo "   (or:      https://127.0.0.1:${FINAL_PORT}/${FINAL_SECRET_PATH}/)"
echo ""
echo "👤 Administrator Credentials:"
echo "   Username: ${FINAL_ADMIN_USER}"
if [ -n "$FINAL_ADMIN_PASS" ]; then
    echo "   Password: ${FINAL_ADMIN_PASS}"
else
    echo "   Password: (kept existing password)"
fi
if [ -n "$FINAL_BACKUP_PASS" ]; then
    echo "   Backup Password: ${FINAL_BACKUP_PASS}"
fi
echo "===================================================="
echo "⚠️  Please copy and save these credentials securely!"
echo "   Use 'docker compose logs -f' to view logs."
echo "   Use 'systemctl status sentinel-agent' for agent status."
echo "===================================================="
