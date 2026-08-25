#!/bin/bash

# ==============================================================================
# Sentinel-Core Binary & Library Downloader
# Fetches compiled sentinel-core engine for current OS/Arch with interactive version selector
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"
AUTO_MODE=0

for arg in "$@"; do
    case "$arg" in
        --auto|-y) AUTO_MODE=1 ;;
        -*) ;;
        *) BIN_DIR="$arg" ;;
    esac
done

mkdir -p "$BIN_DIR"

# 1. Detect OS
OS_TYPE="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$OS_TYPE" in
    linux*)   OS="linux" ;;
    darwin*)  OS="darwin" ;;
    msys*|mingw*|cygwin*) OS="windows" ;;
    *)        OS="linux" ;;
esac

# 2. Detect Architecture
ARCH_RAW="$(uname -m | tr '[:upper:]' '[:lower:]')"
case "$ARCH_RAW" in
    x86_64|amd64)   ARCH="amd64" ;;
    aarch64|arm64)  ARCH="arm64" ;;
    armv7*|armhf)   ARCH="armv7" ;;
    *)              ARCH="amd64" ;;
esac

REPO="blackalex1/sentinel-core"

# Determine target binary & library names
if [ "$OS" = "windows" ]; then
    BIN_NAME="sentinel-core-windows-${ARCH}.exe"
    DEST_BIN="$BIN_DIR/sentinel-core.exe"
    LIB_NAME="sentinel-core-windows-${ARCH}.dll"
    DEST_LIB="$BIN_DIR/sentinel-core.dll"
else
    BIN_NAME="sentinel-core-${OS}-${ARCH}"
    DEST_BIN="$BIN_DIR/sentinel-core"
    LIB_NAME="libsentinel-core-${OS}-${ARCH}.so"
    DEST_LIB="$BIN_DIR/libsentinel-core.so"
fi

# 3. Detect currently installed version
CURRENT_VER="Не установлено (Not installed)"
IS_INSTALLED=0
if [ -x "$DEST_BIN" ] || [ -f "$DEST_BIN" ]; then
    IS_INSTALLED=1
    DETECTED_RAW=$("$DEST_BIN" version 2>/dev/null || "$DEST_BIN" --version 2>/dev/null || true)
    if [ -n "$DETECTED_RAW" ]; then
        CURRENT_VER=$(echo "$DETECTED_RAW" | head -n 1)
    else
        CURRENT_VER="Установлено (версия не определена)"
    fi
fi

# 4. Fetch available releases from GitHub API
STABLE_VER=""
PRERELEASE_VER=""
LATEST_ANY=""

echo "[+] Опрос GitHub Releases для $REPO..."

# Use python3 to fetch and categorize releases safely
if command -v python3 &>/dev/null; then
    RELEASE_DATA=$(python3 -c "
import urllib.request, json, sys
try:
    req = urllib.request.Request('https://api.github.com/repos/$REPO/releases', headers={'User-Agent': 'SentinelPanel'})
    with urllib.request.urlopen(req, timeout=6) as response:
        releases = json.loads(response.read().decode('utf-8'))
        stable = next((r['tag_name'] for r in releases if not r.get('prerelease')), '')
        prerelease = next((r['tag_name'] for r in releases if r.get('prerelease')), '')
        latest_any = releases[0]['tag_name'] if releases else ''
        print(f'{stable}|{prerelease}|{latest_any}')
except Exception:
    print('||')
" 2>/dev/null || echo "||")
    STABLE_VER=$(echo "$RELEASE_DATA" | cut -d'|' -f1)
    PRERELEASE_VER=$(echo "$RELEASE_DATA" | cut -d'|' -f2)
    LATEST_ANY=$(echo "$RELEASE_DATA" | cut -d'|' -f3)
fi

# Fallback with curl if python didn't get results
if [ -z "$LATEST_ANY" ] && command -v curl &>/dev/null; then
    LATEST_ANY=$(curl -fsSL --connect-timeout 5 "https://api.github.com/repos/$REPO/releases" 2>/dev/null | grep -m1 '"tag_name":' | cut -d'"' -f4 | tr -d '\r\n ')
fi

# 5. Interactive version selection UI
SELECTED_TAG=""

# Check if running interactively in a TTY terminal
if [ -t 0 ] && [ "$AUTO_MODE" -eq 0 ]; then
    echo ""
    echo "===================================================="
    echo "🛡️  ВЫБОР ВЕРСИИ ЯДРА SENTINEL-CORE"
    echo "===================================================="
    echo "📌 Текущая версия:              $CURRENT_VER"
    echo "🟢 Последняя стабильная (Stable): ${STABLE_VER:-Отсутствует (нет стабильного релиза)}"
    echo "🟡 Пре-релиз / Бета (Pre-release): ${PRERELEASE_VER:-Отсутствует}"
    echo "===================================================="

    CURRENT_VER_TAG=$(echo "$CURRENT_VER" | grep -o -E 'v[0-9]+\.[0-9]+(\.[0-9]+)*(-[a-zA-Z0-9.]+)?' | head -n 1)

    # Smart default: If current version is already the latest stable, default is Skip (3).
    # If current version is older, a beta, or missing, default is Update to Stable (1).
    if [ "$IS_INSTALLED" -eq 1 ] && [ -n "$STABLE_VER" ] && [ "$CURRENT_VER_TAG" = "$STABLE_VER" ]; then
        DEFAULT_CHOICE="3"
    else
        DEFAULT_CHOICE="1"
    fi

    if [ -n "$PRERELEASE_VER" ] && [ -n "$STABLE_VER" ]; then
        echo "Варианты установки:"
        if [ "$DEFAULT_CHOICE" = "1" ]; then
            echo "  1) 🟢 Установить стабильную версию ($STABLE_VER) [Рекомендуется / По умолчанию]"
            echo "  2) 🟡 Установить пре-релиз / бету ($PRERELEASE_VER) [Экспериментальная]"
            echo "  3) ⏹️  Оставить текущую версию (пропустить обновление ядра)"
        else
            echo "  1) 🟢 Установить стабильную версию ($STABLE_VER)"
            echo "  2) 🟡 Установить пре-релиз / бету ($PRERELEASE_VER) [Экспериментальная]"
            echo "  3) ⏹️  Оставить текущую версию (пропустить обновление ядра) [По умолчанию]"
        fi
        echo "  4) ✏️  Ввести тег/версию вручную"
        read -t 15 -p "Выберите вариант [1-4] (по умолчанию $DEFAULT_CHOICE): " USER_CHOICE || USER_CHOICE="$DEFAULT_CHOICE"
        USER_CHOICE="${USER_CHOICE:-$DEFAULT_CHOICE}"
        echo ""
        case "$USER_CHOICE" in
            1) SELECTED_TAG="$STABLE_VER" ;;
            2) SELECTED_TAG="$PRERELEASE_VER" ;;
            3) echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0 ;;
            4) read -p "Введите тег релиза (например $PRERELEASE_VER): " SELECTED_TAG ;;
            *) [ "$DEFAULT_CHOICE" = "3" ] && { echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0; } || SELECTED_TAG="$STABLE_VER" ;;
        esac
    elif [ -n "$PRERELEASE_VER" ]; then
        echo "⚠️  Внимание: Стабильный релиз пока отсутствует (проект на стадии беты/пре-релиза)."
        echo "  1) 🟡 Установить бета-версию ($PRERELEASE_VER) [Экспериментальная]"
        if [ "$IS_INSTALLED" -eq 1 ]; then
            echo "  2) ⏹️  Оставить текущую версию (пропустить обновление) [По умолчанию]"
        else
            echo "  2) ⏹️  Пропустить установку ядра"
        fi
        echo "  3) ✏️  Ввести тег/версию вручную"
        read -t 15 -p "Выберите вариант [1-3] (по умолчанию ${IS_INSTALLED:+2}${IS_INSTALLED:-1}): " USER_CHOICE || USER_CHOICE="${IS_INSTALLED:+2}${IS_INSTALLED:-1}"
        USER_CHOICE="${USER_CHOICE:-${IS_INSTALLED:+2}${IS_INSTALLED:-1}}"
        echo ""
        case "$USER_CHOICE" in
            1) SELECTED_TAG="$PRERELEASE_VER" ;;
            2) echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0 ;;
            3) read -p "Введите тег релиза (например $PRERELEASE_VER): " SELECTED_TAG ;;
            *) echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0 ;;
        esac
    elif [ -n "$STABLE_VER" ]; then
        echo "  1) 🟢 Установить стабильную версию ($STABLE_VER)"
        if [ "$IS_INSTALLED" -eq 1 ]; then
            echo "  2) ⏹️  Оставить текущую версию (пропустить обновление) [По умолчанию]"
        else
            echo "  2) ⏹️  Пропустить установку"
        fi
        echo "  3) ✏️  Ввести тег/версию вручную"
        read -t 15 -p "Выберите вариант [1-3] (по умолчанию ${IS_INSTALLED:+2}${IS_INSTALLED:-1}): " USER_CHOICE || USER_CHOICE="${IS_INSTALLED:+2}${IS_INSTALLED:-1}"
        USER_CHOICE="${USER_CHOICE:-${IS_INSTALLED:+2}${IS_INSTALLED:-1}}"
        echo ""
        case "$USER_CHOICE" in
            1) SELECTED_TAG="$STABLE_VER" ;;
            2) echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0 ;;
            3) read -p "Введите тег релиза (например $STABLE_VER): " SELECTED_TAG ;;
            *) echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0 ;;
        esac
    else
        echo "[-] Не удалось получить список версий через API."
        echo "  1) Попробовать скачать последний релиз напрямую"
        echo "  2) Ввести версию вручную"
        echo "  3) Пропустить"
        read -t 15 -p "Выберите вариант [1-3] (по умолчанию 3): " USER_CHOICE || USER_CHOICE="3"
        USER_CHOICE="${USER_CHOICE:-3}"
        echo ""
        case "$USER_CHOICE" in
            1) SELECTED_TAG="" ;;
            2) read -p "Введите тег релиза вручную: " SELECTED_TAG ;;
            *) echo "[+] Обновление ядра пропущено."; exit 0 ;;
        esac
    fi
else
    # Non-interactive / unattended automated mode: skip re-download if installed version matches
    if [ -n "$STABLE_VER" ]; then
        SELECTED_TAG="$STABLE_VER"
    elif [ -n "$PRERELEASE_VER" ]; then
        SELECTED_TAG="$PRERELEASE_VER"
    else
        SELECTED_TAG="$LATEST_ANY"
    fi

    if [ "$IS_INSTALLED" -eq 1 ] && [ -n "$SELECTED_TAG" ] && echo "$CURRENT_VER" | grep -q "$SELECTED_TAG"; then
        echo "[+] Текущая версия ядра ($CURRENT_VER) уже актуальна ($SELECTED_TAG). Обновление не требуется."
        exit 0
    fi
fi

echo "[+] Выбранная версия для загрузки: ${SELECTED_TAG:-latest}"

# 6. Build Candidate Download URLs
URL_CANDIDATES=()
if [ -n "$SELECTED_TAG" ]; then
    URL_CANDIDATES+=("https://github.com/$REPO/releases/download/$SELECTED_TAG")
fi
URL_CANDIDATES+=("https://github.com/$REPO/releases/latest/download")

# Helper function to download asset
download_asset() {
    local ASSET_NAME="$1"
    local DEST_PATH="$2"
    local IS_EXEC="$3"
    local SUCCESS=0

    for BASE_URL in "${URL_CANDIDATES[@]}"; do
        local URL="$BASE_URL/$ASSET_NAME"
        local TMP_FILE="/tmp/${ASSET_NAME}.$$"
        rm -f "$TMP_FILE"

        if command -v curl &>/dev/null; then
            curl -fsSL --connect-timeout 10 --retry 2 "$URL" -o "$TMP_FILE" 2>/dev/null
        elif command -v wget &>/dev/null; then
            wget -q -T 10 -t 2 "$URL" -O "$TMP_FILE" 2>/dev/null
        elif command -v python3 &>/dev/null; then
            python3 -c "import urllib.request; urllib.request.urlretrieve('$URL', '$TMP_FILE')" 2>/dev/null || true
        fi

        if [ -s "$TMP_FILE" ]; then
            # Verify it is not an HTML error response
            if ! head -n 1 "$TMP_FILE" | grep -iq "<!DOCTYPE html>"; then
                mv "$TMP_FILE" "$DEST_PATH"
                if [ "$IS_EXEC" = "1" ]; then
                    chmod +x "$DEST_PATH" 2>/dev/null || true
                fi
                echo "[+] Успешно установлен $ASSET_NAME -> $DEST_PATH"
                SUCCESS=1
                break
            fi
        fi
        rm -f "$TMP_FILE"
    done

    if [ "$SUCCESS" -eq 0 ]; then
        if [ -f "$DEST_PATH" ]; then
            echo "[-] Не удалось загрузить $ASSET_NAME из релиза. Сохранена текущая локальная версия."
        else
            echo "[!] Ошибка: Не удалось скачать $ASSET_NAME."
        fi
    fi
}

# 7. Download CLI binary
echo "[+] Загрузка бинарника $BIN_NAME..."
download_asset "$BIN_NAME" "$DEST_BIN" 1

# 8. Download C-Shared library
echo "[+] Загрузка библиотеки $LIB_NAME..."
download_asset "$LIB_NAME" "$DEST_LIB" 0

# 9. Download header file
download_asset "sentinel-core.h" "$BIN_DIR/sentinel-core.h" 0

# 10. Verification
if [ -x "$DEST_BIN" ] || [ -f "$DEST_BIN" ]; then
    echo "[+] Проверка работоспособности sentinel-core..."
    if "$DEST_BIN" version &>/dev/null || "$DEST_BIN" --help &>/dev/null || "$DEST_BIN" preset list &>/dev/null; then
        echo "[+] sentinel-core успешно проверен и готов к работе!"
    fi
fi

exit 0
