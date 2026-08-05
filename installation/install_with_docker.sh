#!/bin/bash

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root (use sudo)"
  exit 1
fi

# Get the absolute path of the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[+] Project directory detected: $SCRIPT_DIR"

# 1. Update spectre-agent.service configuration dynamically
SERVICE_TEMPLATE="$SCRIPT_DIR/host/spectre-agent.service"
SERVICE_DEST="/etc/systemd/system/spectre-agent.service"

echo "[+] Configuring systemd service at $SERVICE_DEST..."

# Create service file using sed to replace the default /opt/spectre/host paths with SCRIPT_DIR
sed "s|/opt/spectre|$SCRIPT_DIR|g" "$SERVICE_TEMPLATE" > "$SERVICE_DEST"

# 2. Reload systemd and start Host Agent
echo "[+] Reloading systemd..."
systemctl daemon-reload
echo "[+] Enabling spectre-agent service..."
systemctl enable spectre-agent
echo "[+] Starting spectre-agent service..."
systemctl restart spectre-agent

# Verify Host Agent
if systemctl is-active --quiet spectre-agent; then
    echo "[+] spectre-agent service started successfully!"
else
    echo "[!] Failed to start spectre-agent service. Check logs: journalctl -u spectre-agent"
fi

# 3. Interactive Configuration for config/.env
ENV_FILE="$SCRIPT_DIR/config/.env"
mkdir -p "$SCRIPT_DIR/config"
chmod 700 "$SCRIPT_DIR/config"

if [ -f "$ENV_FILE" ]; then
    read -p "[?] Existing configuration found at config/.env. Do you want to reconfigure it? (y/N): " RECONFIRM
    if [[ "$RECONFIRM" =~ ^[yY]$ ]]; then
        echo "[+] Removing old configuration..."
        rm -f "$ENV_FILE"
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
        ADMIN_USER="admin_$(openssl rand -hex 3 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(3))")"
        echo "[+] Auto-generated Admin Username: $ADMIN_USER"
    fi

    # 4. Web Admin Password
    read -s -p "Enter Web Panel Admin Password [leave empty to auto-generate]: " ADMIN_PASS
    echo ""
    if [ -z "$ADMIN_PASS" ]; then
        ADMIN_PASS=$(openssl rand -hex 10 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(10))")
        echo "[+] Auto-generated Admin Password: $ADMIN_PASS"
    fi

    # 5. Web Panel Port
    read -p "Enter Web Panel Port [leave empty to auto-generate]: " PORT
    if [ -z "$PORT" ]; then
        PORT=$(( 10000 + RANDOM % 50000 ))
        echo "[+] Auto-generated Panel Port: $PORT"
    fi

    # Auto-generate API Token, Secret Path, and DB passwords for security
    RAND_API_TOKEN=$(openssl rand -hex 24 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(24))")
    RAND_SECRET_PATH="ui_$(openssl rand -hex 6 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(6))")"
    DB_ADMIN_PASS=$(openssl rand -hex 12 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(12))")
    DB_APP_PASS=$(openssl rand -hex 12 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(12))")

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
POSTGRES_DB=spectre_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$DB_ADMIN_PASS

DB_APP_USER=spectre_app
DB_APP_PASSWORD=$DB_APP_PASS

# Строки подключения к БД (Администратор DDL / Приложение DML)
DATABASE_ADMIN_URL=postgresql://postgres:$DB_ADMIN_PASS@127.0.0.1:5432/spectre_db
DATABASE_URL=postgresql://spectre_app:$DB_APP_PASS@127.0.0.1:5432/spectre_db
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

# 4. Check for Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    echo "[!] Docker is not installed. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

if ! docker compose version &> /dev/null; then
    echo "[!] docker compose command not found. Installing docker-compose-plugin..."
    apt-get update && apt-get install -y docker-compose-plugin
fi

# 5. Build and run Docker containers
echo "[+] Starting Docker Compose..."
cd "$SCRIPT_DIR"
docker compose build
docker compose up -d

# 5.5. Seed Telegram settings in the database after container startup
if [ -n "$TG_TOKEN" ] || [ -n "$TG_IDS" ]; then
    echo "[+] Saving Telegram settings to the database..."
    for i in {1..10}; do
        if docker compose exec -T spectre-panel python -c "from backend.database import set_setting; set_setting('telegram_bot_token', '$TG_TOKEN'); set_setting('telegram_admin_ids', '$TG_IDS')" &>/dev/null; then
            echo "[+] Telegram settings successfully saved to database."
            break
        fi
        echo "[-] Waiting for database initialization ($i/10)..."
        sleep 3
    done
fi

# Read actual settings from .env to print the final summary card
FINAL_PORT=$(grep -E "^PANEL_PORT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '\r')
FINAL_SECRET_PATH=$(grep -E "^PANEL_SECRET_PATH=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '\r')
FINAL_ADMIN_USER=$(grep -E "^ADMIN_USERNAME=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '\r')
FINAL_ADMIN_PASS=$(grep -E "^ADMIN_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '\r')

# Query backup password from database (wait up to 30s for database readiness if needed)
FINAL_BACKUP_PASS=""
for i in {1..15}; do
    FINAL_BACKUP_PASS=$(docker compose exec -T spectre-panel python -c "from backend.database import get_setting; print(get_setting('backup_password', ''))" 2>/dev/null | tr -d '\r\n ')
    if [ -n "$FINAL_BACKUP_PASS" ]; then
        break
    fi
    sleep 2
done

# Try to get public IP, fallback to primary interface IP or placeholder
SERVER_IP=$(curl -s https://ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || ip route get 1 | awk 'BEGIN {found=0} {for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); found=1; exit}} END {if(!found) exit 1}' 2>/dev/null || echo "YOUR_SERVER_IP")

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
echo "   Password: ${FINAL_ADMIN_PASS}"
if [ -n "$FINAL_BACKUP_PASS" ]; then
    echo "   Backup Password: ${FINAL_BACKUP_PASS}"
fi
echo "===================================================="
echo "⚠️  Please copy and save these credentials securely!"
echo "   Use 'docker compose logs -f' to view logs."
echo "   Use 'systemctl status spectre-agent' for agent status."
echo "===================================================="
