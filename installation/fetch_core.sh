#!/bin/bash

# ==============================================================================
# Sentinel-Core Binary & Library Downloader for Sentinel-Panel
# Fetches compiled sentinel-core engine for current OS/Arch with mirror & proxy support
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"
AUTO_MODE=0
FORCE_MODE=0
PROXY_URL=""
NO_PROXY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --auto|-y)
            AUTO_MODE=1
            shift
            ;;
        --force|-f)
            FORCE_MODE=1
            shift
            ;;
        --proxy|-p)
            PROXY_URL="$2"
            shift 2
            ;;
        --no-proxy)
            NO_PROXY=1
            shift
            ;;
        -*)
            shift
            ;;
        *)
            BIN_DIR="$1"
            shift
            ;;
    esac
done

mkdir -p "$BIN_DIR"

# 0. Check proxy from .env if not specified via CLI
if [ -z "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
    for env_f in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/config/.env"; do
        if [ -f "$env_f" ]; then
            P_VAL=$(grep -E '^[[:space:]]*PROXY_URL=' "$env_f" 2>/dev/null | cut -d'=' -f2- | tr -d '"'\'' ')
            if [ -n "$P_VAL" ]; then
                PROXY_URL="$P_VAL"
                break
            fi
        fi
    done
    if [ -z "$PROXY_URL" ]; then
        PROXY_URL="${HTTPS_PROXY:-${HTTP_PROXY:-${ALL_PROXY:-${https_proxy:-${http_proxy:-${all_proxy:-}}}}}}"
    fi
fi

VALID_PROXY=""
CURL_OPTS=(-fsSL --connect-timeout 8 --max-time 60)
if [ -n "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
    if [[ "$PROXY_URL" =~ ^(http|https|socks4|socks5|socks5h):// ]]; then
        VALID_PROXY="$PROXY_URL"
        CURL_OPTS+=("-x" "$VALID_PROXY")
        echo "[+] Использование прокси для загрузки: $VALID_PROXY"
    fi
fi

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

# Use python3 to fetch and categorize releases safely with proxy/mirror support
if command -v python3 &>/dev/null; then
    RELEASE_DATA=$(python3 -c "
import urllib.request, json, sys, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

urls = [
    'https://api.github.com/repos/$REPO/releases',
    'https://ghproxy.net/https://api.github.com/repos/$REPO/releases',
    'https://gh-proxy.com/https://api.github.com/repos/$REPO/releases'
]
proxy = '$VALID_PROXY'
handlers = [urllib.request.ProxyHandler({'http': proxy, 'https': proxy})] if proxy else []
opener = urllib.request.build_opener(*handlers)

for u in urls:
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'SentinelPanel'})
        with opener.open(req, timeout=6) as response:
            releases = json.loads(response.read().decode('utf-8'))
            if isinstance(releases, list) and len(releases) > 0:
                stable = next((r['tag_name'] for r in releases if not r.get('prerelease')), '')
                prerelease = releases[0]['tag_name'] if releases[0].get('prerelease') else ''
                latest_any = releases[0]['tag_name'] if releases else ''
                print(f'{stable}|{prerelease}|{latest_any}')
                sys.exit(0)
    except Exception:
        continue
print('||')
" 2>/dev/null || echo "||")
    STABLE_VER=$(echo "$RELEASE_DATA" | cut -d'|' -f1)
    PRERELEASE_VER=$(echo "$RELEASE_DATA" | cut -d'|' -f2)
    LATEST_ANY=$(echo "$RELEASE_DATA" | cut -d'|' -f3)
fi

# Fallback with curl if python didn't get results
if [ -z "$LATEST_ANY" ] && command -v curl &>/dev/null; then
    for api_url in "https://api.github.com/repos/$REPO/releases" "https://ghproxy.net/https://api.github.com/repos/$REPO/releases" "https://gh-proxy.com/https://api.github.com/repos/$REPO/releases"; do
        LATEST_ANY=$(curl "${CURL_OPTS[@]}" "$api_url" 2>/dev/null | grep -m1 '"tag_name":' | cut -d'"' -f4 | tr -d '\r\n ')
        if [ -n "$LATEST_ANY" ]; then
            [ -z "$STABLE_VER" ] && STABLE_VER="$LATEST_ANY"
            break
        fi
    done
fi

# 5. Interactive version selection UI
SELECTED_TAG=""

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
        [ "$IS_INSTALLED" -eq 1 ] && DEFAULT_CHOICE="2"
        read -t 15 -p "Выберите вариант [1-3] (по умолчанию $DEFAULT_CHOICE): " USER_CHOICE || USER_CHOICE="$DEFAULT_CHOICE"
        USER_CHOICE="${USER_CHOICE:-$DEFAULT_CHOICE}"
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
            echo "  2) ⏹️  Оставить текущую версию (пропустить) [По умолчанию]"
        else
            echo "  2) ⏹️  Пропустить установку"
        fi
        echo "  3) ✏️  Ввести тег/версию вручную"
        [ "$IS_INSTALLED" -eq 1 ] && DEFAULT_CHOICE="2"
        read -t 15 -p "Выберите вариант [1-3] (по умолчанию $DEFAULT_CHOICE): " USER_CHOICE || USER_CHOICE="$DEFAULT_CHOICE"
        USER_CHOICE="${USER_CHOICE:-$DEFAULT_CHOICE}"
        echo ""
        case "$USER_CHOICE" in
            1) SELECTED_TAG="$STABLE_VER" ;;
            2) echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0 ;;
            3) read -p "Введите тег релиза (например $STABLE_VER): " SELECTED_TAG ;;
            *) echo "[+] Обновление ядра пропущено (оставлена текущая версия)."; exit 0 ;;
        esac
    else
        echo "[-] Не удалось получить список версий через API."
        echo "  1) 🟢 Скачать последний стабильный релиз (через зеркало)"
        echo "  2) ✏️  Ввести версию вручную (например v0.0.7)"
        echo "  3) ⏹️  Оставить текущую версию (пропустить) [По умолчанию]"
        DEFAULT_CHOICE="1"
        read -t 15 -p "Выберите вариант [1-3] (по умолчанию $DEFAULT_CHOICE): " USER_CHOICE || USER_CHOICE="$DEFAULT_CHOICE"
        USER_CHOICE="${USER_CHOICE:-$DEFAULT_CHOICE}"
        echo ""
        case "$USER_CHOICE" in
            1) SELECTED_TAG="v0.0.7" ;;
            2) read -p "Введите тег релиза вручную: " SELECTED_TAG ;;
            3) echo "[+] Обновление ядра пропущено."; exit 0 ;;
            *) SELECTED_TAG="v0.0.7" ;;
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

    if [ "$FORCE_MODE" -eq 0 ] && [ "$IS_INSTALLED" -eq 1 ] && [ -n "$SELECTED_TAG" ] && echo "$CURRENT_VER" | grep -q "$SELECTED_TAG"; then
        echo "[+] Текущая версия ядра ($CURRENT_VER) уже актуальна ($SELECTED_TAG). Обновление не требуется."
        exit 0
    fi
fi

echo "[+] Выбранная версия для загрузки: ${SELECTED_TAG:-v0.0.7}"
TARGET_TAG="${SELECTED_TAG:-v0.0.7}"

# 6. Fetch native release asset digests (SHA256 & Exact Size) from GitHub API
DIGEST_FILE="/tmp/sentinel_core_digests.$$"
rm -f "$DIGEST_FILE"

if command -v python3 &>/dev/null; then
    python3 -c "
import urllib.request, json
tag = '$TARGET_TAG'
repo = '$REPO'
urls = [
    f'https://api.github.com/repos/{repo}/releases/tags/{tag}' if tag and tag != 'latest' else f'https://api.github.com/repos/{repo}/releases/latest',
    f'https://ghproxy.net/https://api.github.com/repos/{repo}/releases/tags/{tag}' if tag and tag != 'latest' else f'https://ghproxy.net/https://api.github.com/repos/{repo}/releases/latest',
    f'https://gh-proxy.com/https://api.github.com/repos/{repo}/releases/tags/{tag}' if tag and tag != 'latest' else f'https://gh-proxy.com/https://api.github.com/repos/{repo}/releases/latest',
]
proxy = '$VALID_PROXY'
handlers = [urllib.request.ProxyHandler({'http': proxy, 'https': proxy})] if proxy else []
opener = urllib.request.build_opener(*handlers)
for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SentinelPanel'})
        with opener.open(req, timeout=10) as r:
            rel = json.loads(r.read().decode('utf-8'))
            with open('$DIGEST_FILE', 'w') as f:
                for a in rel.get('assets', []):
                    name = a.get('name')
                    digest = a.get('digest', '')
                    size = a.get('size', 0)
                    if name:
                        f.write(f'{name}={digest}={size}\n')
            exit(0)
    except Exception:
        pass
" 2>/dev/null || true
fi

calc_sha256() {
    local file="$1"
    if command -v sha256sum &>/dev/null; then
        sha256sum "$file" 2>/dev/null | awk '{print $1}'
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$file" 2>/dev/null | awk '{print $1}'
    elif command -v python3 &>/dev/null; then
        python3 -c "import hashlib; print(hashlib.sha256(open('$file', 'rb').read()).hexdigest())" 2>/dev/null || true
    fi
}

# 7. Build Candidate Download URLs (Direct + Multiple Fast Mirrors)
URL_CANDIDATES=(
    "https://github.com/$REPO/releases/download/$TARGET_TAG"
    "https://gh-proxy.com/https://github.com/$REPO/releases/download/$TARGET_TAG"
    "https://ghfast.top/https://github.com/$REPO/releases/download/$TARGET_TAG"
    "https://gh.ddlc.top/https://github.com/$REPO/releases/download/$TARGET_TAG"
    "https://ghproxy.net/https://github.com/$REPO/releases/download/$TARGET_TAG"
    "https://github.com/$REPO/releases/latest/download"
    "https://gh-proxy.com/https://github.com/$REPO/releases/latest/download"
    "https://ghfast.top/https://github.com/$REPO/releases/latest/download"
)

# Helper function to download asset with multi-mirror fallback and cryptographic verification
download_asset() {
    local ASSET_NAME="$1"
    local DEST_PATH="$2"
    local IS_EXEC="$3"
    local SUCCESS=0

    for BASE_URL in "${URL_CANDIDATES[@]}"; do
        local URL="$BASE_URL/$ASSET_NAME"
        local TMP_FILE="/tmp/${ASSET_NAME}.$$"
        rm -f "$TMP_FILE"

        local IS_MIRROR=0
        local HOST_LABEL="Официальный GitHub"
        if [[ "$BASE_URL" =~ (ghproxy|gh-proxy|ghfast|ddlc|mirror\.ghproxy|fastgit) ]]; then
            IS_MIRROR=1
            HOST_LABEL="CDN-зеркало ($(echo "$BASE_URL" | awk -F'/' '{print $3}'))"
        fi

        echo "  ➜ Попытка загрузки $ASSET_NAME из $HOST_LABEL..."

        if command -v curl &>/dev/null; then
            # Snappy timeouts for direct connection without proxy to immediately bypass throttled AWS S3
            local CURL_OPTS=("-fsSL" "--connect-timeout" "4" "--max-time" "20" "--speed-limit" "10240" "--speed-time" "4")
            if [ "$IS_MIRROR" -eq 1 ]; then
                CURL_OPTS=("-fsSL" "-k" "--connect-timeout" "6" "--max-time" "45" "--retry" "1")
                curl "${CURL_OPTS[@]}" -x "" "$URL" -o "$TMP_FILE" 2>/dev/null || true
            elif [ -n "$VALID_PROXY" ]; then
                CURL_OPTS=("-fsSL" "-k" "--connect-timeout" "10" "--max-time" "60" "--retry" "1")
                curl "${CURL_OPTS[@]}" -x "$VALID_PROXY" "$URL" -o "$TMP_FILE" 2>/dev/null || true
            else
                curl "${CURL_OPTS[@]}" "$URL" -o "$TMP_FILE" 2>/dev/null || true
            fi
        elif command -v wget &>/dev/null; then
            local WGET_OPTS=(-q -T 15 -t 1)
            if [ "$IS_MIRROR" -eq 0 ] && [ -n "$VALID_PROXY" ]; then
                WGET_OPTS+=("-e" "http_proxy=$VALID_PROXY" "-e" "https_proxy=$VALID_PROXY")
            fi
            wget "${WGET_OPTS[@]}" "$URL" -O "$TMP_FILE" 2>/dev/null || true
        elif command -v python3 &>/dev/null; then
            python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
proxy = '$VALID_PROXY' if $IS_MIRROR == 0 else ''
handlers = [urllib.request.ProxyHandler({'http': proxy, 'https': proxy})] if proxy else []
opener = urllib.request.build_opener(*handlers)
req = urllib.request.Request('$URL', headers={'User-Agent': 'SentinelPanel'})
try:
    with opener.open(req, timeout=15) as r, open('$TMP_FILE', 'wb') as f:
        f.write(r.read())
except Exception:
    pass
" 2>/dev/null || true
        fi

        if [ -s "$TMP_FILE" ]; then
            local FILE_SIZE=0
            FILE_SIZE=$(wc -c < "$TMP_FILE" 2>/dev/null || stat -c%s "$TMP_FILE" 2>/dev/null || stat -f%z "$TMP_FILE" 2>/dev/null || echo 0)

            # 1. Проверяем, не вернулась ли HTML-страница ошибки
            if head -n 1 "$TMP_FILE" | grep -iqE "<!DOCTYPE|<html|404: Not Found|\{\"message\":"; then
                rm -f "$TMP_FILE"
                continue
            fi

            # 2. Верификация по нативному SHA-256 хешу от GitHub Releases
            local EXPECTED_ENTRY=""
            if [ -f "$DIGEST_FILE" ]; then
                EXPECTED_ENTRY=$(grep -E "^${ASSET_NAME}=" "$DIGEST_FILE" 2>/dev/null | head -n 1)
            fi
            local EXPECTED_DIGEST=$(echo "$EXPECTED_ENTRY" | cut -d'=' -f2 | tr -d '\r\n ')
            local EXPECTED_HASH="${EXPECTED_DIGEST#sha256:}"
            local EXPECTED_SIZE=$(echo "$EXPECTED_ENTRY" | cut -d'=' -f3 | tr -d '\r\n ')

            if [ -n "$EXPECTED_HASH" ]; then
                local ACTUAL_HASH
                ACTUAL_HASH=$(calc_sha256 "$TMP_FILE")
                if [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then
                    echo "[-] SHA-256 не совпадает для $ASSET_NAME (ожидался ${EXPECTED_HASH:0:12}..., получен ${ACTUAL_HASH:0:12}...). Пробуем следующий источник..."
                    rm -f "$TMP_FILE"
                    continue
                fi
                echo "[+] SHA-256 проверен: ${ACTUAL_HASH:0:16}..."
            elif [ -n "$EXPECTED_SIZE" ] && [ "$EXPECTED_SIZE" -gt 0 ]; then
                if [ "$FILE_SIZE" -ne "$EXPECTED_SIZE" ]; then
                    echo "[-] Несовпадение размера $ASSET_NAME (ожидалось: ${EXPECTED_SIZE}B, получено: ${FILE_SIZE}B). Пробуем следующий источник..."
                    rm -f "$TMP_FILE"
                    continue
                fi
            else
                local MIN_SIZE=3000000
                if [[ "$ASSET_NAME" == *.h ]]; then
                    MIN_SIZE=200
                fi
                if [ "$FILE_SIZE" -le "$MIN_SIZE" ]; then
                    echo "[-] Файл $ASSET_NAME слишком мал (${FILE_SIZE}B). Пробуем следующий источник..."
                    rm -f "$TMP_FILE"
                    continue
                fi
            fi

            # Безопасная замена inode (unlinking старого файла предотвращает Linux SIGBUS)
            rm -f "$DEST_PATH"
            mv -f "$TMP_FILE" "$DEST_PATH"
            if [ "$IS_EXEC" = "1" ]; then
                chmod +x "$DEST_PATH" 2>/dev/null || true
            fi
            echo "[+] Успешно установлен $ASSET_NAME -> $DEST_PATH"
            SUCCESS=1
            break
        fi
        rm -f "$TMP_FILE"
    done

    if [ "$SUCCESS" -eq 0 ]; then
        if [ -f "$DEST_PATH" ]; then
            echo "[-] Не удалось загрузить целый $ASSET_NAME из релиза. Сохранена текущая локальная версия."
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
