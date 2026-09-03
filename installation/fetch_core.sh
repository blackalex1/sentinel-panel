#!/usr/bin/env bash

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
    for env_f in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/config/.env" ".env"; do
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
    ALT_LIB="$BIN_DIR/libsentinel-core.dll"
else
    BIN_NAME="sentinel-core-${OS}-${ARCH}"
    DEST_BIN="$BIN_DIR/sentinel-core"
    LIB_NAME="libsentinel-core-${OS}-${ARCH}.so"
    DEST_LIB="$BIN_DIR/libsentinel-core.so"
    ALT_LIB="$BIN_DIR/sentinel-core.so"
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

API_URLS=(
    "https://api.github.com/repos/$REPO/releases"
    "https://gh-proxy.com/https://api.github.com/repos/$REPO/releases"
    "https://ghfast.top/https://api.github.com/repos/$REPO/releases"
    "https://ghproxy.net/https://api.github.com/repos/$REPO/releases"
    "https://gh.ddlc.top/https://api.github.com/repos/$REPO/releases"
)

if command -v curl &>/dev/null; then
    API_CURL_OPTS=("-fsSL" "-k" "-H" "User-Agent: SentinelPanel/1.0" "--connect-timeout" "5" "--max-time" "10")
    if [ -n "$VALID_PROXY" ]; then
        PROXY_ARG="$VALID_PROXY"
        [[ "$PROXY_ARG" =~ ^socks5:// ]] && PROXY_ARG="socks5h://${PROXY_ARG#socks5://}"
        API_CURL_OPTS+=("-x" "$PROXY_ARG")
    fi

    for api_url in "${API_URLS[@]}"; do
        RAW_JSON=$(curl "${API_CURL_OPTS[@]}" "$api_url" 2>/dev/null || true)
        if [ -n "$RAW_JSON" ] && [[ "$RAW_JSON" =~ \"tag_name\" ]]; then
            if command -v python3 &>/dev/null; then
                RELEASE_DATA=$(echo "$RAW_JSON" | python3 -c "
import json, sys
try:
    releases = json.load(sys.stdin)
    if isinstance(releases, list) and len(releases) > 0:
        stable = next((r['tag_name'] for r in releases if not r.get('prerelease')), '')
        prerelease = releases[0]['tag_name'] if releases[0].get('prerelease') else ''
        latest_any = releases[0]['tag_name'] if releases else ''
        print(f'{stable}|{prerelease}|{latest_any}')
        sys.exit(0)
except Exception:
    pass
print('||')
" 2>/dev/null || echo "||")
            else
                LATEST_TAG=$(echo "$RAW_JSON" | grep -m1 '"tag_name":' | cut -d'"' -f4 | tr -d '\r\n ')
                RELEASE_DATA="${LATEST_TAG}||${LATEST_TAG}"
            fi
            STABLE_VER=$(echo "$RELEASE_DATA" | cut -d'|' -f1)
            PRERELEASE_VER=$(echo "$RELEASE_DATA" | cut -d'|' -f2)
            LATEST_ANY=$(echo "$RELEASE_DATA" | cut -d'|' -f3)
            [ -n "$LATEST_ANY" ] && break
        fi
    done
fi

SELECTED_TAG=""
if [ -t 0 ] && [ "$AUTO_MODE" -eq 0 ]; then
    echo ""
    echo "===================================================="
    echo "🛡️  ВЫБОР ВЕРСИИ ЯДРА SENTINEL-CORE"
    echo "===================================================="
    echo "📌 Текущая версия:              $CURRENT_VER"
    echo "🟢 Последняя стабильная (Stable): ${STABLE_VER:-Отсутствует}"
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
        echo "  1) 🟢 Установить стабильную версию ($STABLE_VER)"
        echo "  2) 🟡 Установить пре-релиз / бету ($PRERELEASE_VER)"
        echo "  3) ⏹️  Оставить текущую версию (пропустить)"
        echo "  4) ✏️  Ввести тег/версию вручную"
        read -t 15 -p "Выберите вариант [1-4] (по умолчанию $DEFAULT_CHOICE): " USER_CHOICE || USER_CHOICE="$DEFAULT_CHOICE"
        USER_CHOICE="${USER_CHOICE:-$DEFAULT_CHOICE}"
        case "$USER_CHOICE" in
            1) SELECTED_TAG="$STABLE_VER" ;;
            2) SELECTED_TAG="$PRERELEASE_VER" ;;
            3) echo "[+] Обновление sentinel-core пропущено."; exit 0 ;;
            4) read -p "Введите тег релиза: " SELECTED_TAG ;;
            *) SELECTED_TAG="$STABLE_VER" ;;
        esac
    elif [ -n "$STABLE_VER" ]; then
        echo "  1) 🟢 Установить стабильную версию ($STABLE_VER)"
        echo "  2) ⏹️  Оставить текущую версию (пропустить)"
        read -t 15 -p "Выберите вариант [1-2] (по умолчанию 1): " USER_CHOICE || USER_CHOICE="1"
        USER_CHOICE="${USER_CHOICE:-1}"
        case "$USER_CHOICE" in
            1) SELECTED_TAG="$STABLE_VER" ;;
            2) echo "[+] Обновление sentinel-core пропущено."; exit 0 ;;
            *) SELECTED_TAG="$STABLE_VER" ;;
        esac
    else
        SELECTED_TAG="${LATEST_ANY:-v0.0.7}"
    fi
else
    # Non-interactive / Auto mode
    SELECTED_TAG="${STABLE_VER:-${PRERELEASE_VER:-${LATEST_ANY:-v0.0.7}}}"
fi

echo "[+] Выбранная версия Sentinel-Core: $SELECTED_TAG"

# 5. Fetch asset digests from GitHub API
DIGEST_FILE="/tmp/sentinel_core_digests.$$"
rm -f "$DIGEST_FILE"

if command -v curl &>/dev/null; then
    DIG_CURL_OPTS=("-fsSL" "-k" "--connect-timeout" "5" "--max-time" "10")
    if [ -n "$VALID_PROXY" ]; then
        PROXY_ARG="$VALID_PROXY"
        [[ "$PROXY_ARG" =~ ^socks5:// ]] && PROXY_ARG="socks5h://${PROXY_ARG#socks5://}"
        DIG_CURL_OPTS+=("-x" "$PROXY_ARG")
    fi

    DIGEST_URLS=(
        "https://api.github.com/repos/$REPO/releases/tags/$SELECTED_TAG"
        "https://gh-proxy.com/https://api.github.com/repos/$REPO/releases/tags/$SELECTED_TAG"
        "https://ghfast.top/https://api.github.com/repos/$REPO/releases/tags/$SELECTED_TAG"
        "https://ghproxy.net/https://api.github.com/repos/$REPO/releases/tags/$SELECTED_TAG"
    )

    for dig_url in "${DIGEST_URLS[@]}"; do
        RAW_REL=$(curl "${DIG_CURL_OPTS[@]}" "$dig_url" 2>/dev/null || true)
        if [ -n "$RAW_REL" ] && [[ "$RAW_REL" =~ \"assets\" ]]; then
            if command -v python3 &>/dev/null; then
                echo "$RAW_REL" | python3 -c "
import json, sys
try:
    rel = json.load(sys.stdin)
    with open('$DIGEST_FILE', 'w') as f:
        for a in rel.get('assets', []):
            name = a.get('name')
            digest = a.get('digest', '')
            size = a.get('size', 0)
            if name:
                f.write(f'{name}={digest}={size}\n')
except Exception:
    pass
" 2>/dev/null || true
            fi
            [ -s "$DIGEST_FILE" ] && break
        fi
    done
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

# 6. Candidate Download URLs
URL_CANDIDATES=()
if [ -n "$SELECTED_TAG" ]; then
    URL_CANDIDATES+=(
        "https://github.com/$REPO/releases/download/$SELECTED_TAG"
        "https://gh-proxy.com/https://github.com/$REPO/releases/download/$SELECTED_TAG"
        "https://ghfast.top/https://github.com/$REPO/releases/download/$SELECTED_TAG"
        "https://ghproxy.net/https://github.com/$REPO/releases/download/$SELECTED_TAG"
        "https://gh.ddlc.top/https://github.com/$REPO/releases/download/$SELECTED_TAG"
    )
fi
URL_CANDIDATES+=(
    "https://github.com/$REPO/releases/latest/download"
    "https://gh-proxy.com/https://github.com/$REPO/releases/latest/download"
    "https://ghfast.top/https://github.com/$REPO/releases/latest/download"
)

DIRECT_GITHUB_BLOCKED=0

download_asset() {
    local ASSET_NAME="$1"
    local DEST_PATH="$2"
    local IS_EXEC="$3"
    local SUCCESS=0

    for BASE_URL in "${URL_CANDIDATES[@]}"; do
        local IS_MIRROR=0
        local HOST_LABEL="Официальный GitHub"
        if [[ "$BASE_URL" =~ (ghproxy|gh-proxy|ghfast|ddlc|mirror\.ghproxy|fastgit) ]]; then
            IS_MIRROR=1
            HOST_LABEL="CDN-зеркало ($(echo "$BASE_URL" | awk -F'/' '{print $3}'))"
        fi

        if [ "$IS_MIRROR" -eq 0 ] && [ "$DIRECT_GITHUB_BLOCKED" -eq 1 ] && [ -z "$VALID_PROXY" ]; then
            continue
        fi

        local URL="$BASE_URL/$ASSET_NAME"
        local TMP_FILE="/tmp/${ASSET_NAME}.$$"
        rm -f "$TMP_FILE"

        echo "  ➜ Попытка загрузки $ASSET_NAME из $HOST_LABEL..."

        if command -v curl &>/dev/null; then
            local OPTS=("-fsSL" "-k")
            if [ -n "$VALID_PROXY" ]; then
                local PROXY_ARG="$VALID_PROXY"
                [[ "$PROXY_ARG" =~ ^socks5:// ]] && PROXY_ARG="socks5h://${PROXY_ARG#socks5://}"
                OPTS+=("--connect-timeout" "10" "--max-time" "60" "-x" "$PROXY_ARG")
            elif [ "$IS_MIRROR" -eq 1 ]; then
                OPTS+=("--connect-timeout" "5" "--max-time" "45")
            else
                OPTS+=("--connect-timeout" "3" "--max-time" "6" "--speed-limit" "102400" "--speed-time" "2")
            fi
            curl "${OPTS[@]}" "$URL" -o "$TMP_FILE" 2>/dev/null || true
        fi

        if [ ! -s "$TMP_FILE" ] && command -v wget &>/dev/null; then
            local WGET_OPTS=(-q --no-check-certificate -T 10 -t 1)
            if [ "$IS_MIRROR" -eq 0 ] && [ -n "$VALID_PROXY" ]; then
                WGET_OPTS+=("-e" "http_proxy=$VALID_PROXY" "-e" "https_proxy=$VALID_PROXY")
            fi
            wget "${WGET_OPTS[@]}" "$URL" -O "$TMP_FILE" 2>/dev/null || true
        fi

        if [ ! -s "$TMP_FILE" ] && command -v python3 &>/dev/null; then
            python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
https_handler = urllib.request.HTTPSHandler(context=ctx)
proxy = '$VALID_PROXY' if $IS_MIRROR == 0 else ''
handlers = [https_handler]
if proxy:
    handlers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
opener = urllib.request.build_opener(*handlers)
req = urllib.request.Request('$URL', headers={'User-Agent': 'SentinelPanel/1.0'})
try:
    with opener.open(req, timeout=15) as r, open('$TMP_FILE', 'wb') as f:
        f.write(r.read())
except Exception:
    pass
" 2>/dev/null || true
        fi

        if [ -s "$TMP_FILE" ]; then
            # Check for error html
            if head -n 1 "$TMP_FILE" | grep -iqE "<!DOCTYPE|<html|404: Not Found|\{\"message\":"; then
                rm -f "$TMP_FILE"
                continue
            fi

            # Digest check
            local EXPECTED_ENTRY=""
            if [ -f "$DIGEST_FILE" ]; then
                EXPECTED_ENTRY=$(grep -E "^${ASSET_NAME}=" "$DIGEST_FILE" 2>/dev/null | head -n 1)
            fi
            local EXPECTED_DIGEST=$(echo "$EXPECTED_ENTRY" | cut -d'=' -f2 | tr -d '\r\n ')
            local EXPECTED_HASH="${EXPECTED_DIGEST#sha256:}"
            if [ -n "$EXPECTED_HASH" ]; then
                local ACTUAL_HASH
                ACTUAL_HASH=$(calc_sha256 "$TMP_FILE")
                if [ -n "$ACTUAL_HASH" ] && [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then
                    echo "[-] Несовпадение SHA-256 для $ASSET_NAME. Пробуем следующее зеркало..."
                    rm -f "$TMP_FILE"
                    continue
                fi
                echo "[+] SHA-256 проверен (${ACTUAL_HASH:0:16}...)"
            fi

            rm -f "$DEST_PATH"
            mv -f "$TMP_FILE" "$DEST_PATH"
            if [ "$IS_EXEC" = "1" ]; then
                chmod +x "$DEST_PATH" 2>/dev/null || true
            fi
            echo "[+] Успешно установлен $ASSET_NAME -> $DEST_PATH"
            SUCCESS=1
            break
        fi
        [ "$IS_MIRROR" -eq 0 ] && [ -z "$VALID_PROXY" ] && DIRECT_GITHUB_BLOCKED=1
        rm -f "$TMP_FILE"
    done

    rm -f "$DIGEST_FILE"
    if [ "$SUCCESS" -eq 0 ]; then
        if [ -f "$DEST_PATH" ]; then
            echo "[-] Не удалось загрузить $ASSET_NAME из релиза. Сохранена локальная копия."
        else
            echo "[!] Ошибка: Не удалось скачать $ASSET_NAME."
            return 1
        fi
    fi
    return 0
}

# 7. Download CLI binary
echo "[+] Загрузка бинарника $BIN_NAME..."
download_asset "$BIN_NAME" "$DEST_BIN" 1 || true

# 8. Download C-Shared library
echo "[+] Загрузка библиотеки $LIB_NAME..."
download_asset "$LIB_NAME" "$DEST_LIB" 0 || true

# Create symlink/alias for shared library
if [ -f "$DEST_LIB" ]; then
    if [ "$OS" != "windows" ]; then
        ln -sf "$DEST_LIB" "$ALT_LIB" 2>/dev/null || cp -f "$DEST_LIB" "$ALT_LIB" 2>/dev/null || true
    else
        cp -f "$DEST_LIB" "$ALT_LIB" 2>/dev/null || true
    fi
fi

# 9. Download header file
download_asset "sentinel-core.h" "$BIN_DIR/sentinel-core.h" 0 || true

# 10. Verification
if [ -x "$DEST_BIN" ] || [ -f "$DEST_BIN" ]; then
    echo "[+] Проверка работоспособности sentinel-core..."
    if "$DEST_BIN" version &>/dev/null || "$DEST_BIN" --help &>/dev/null || "$DEST_BIN" preset list &>/dev/null; then
        echo "[+] sentinel-core успешно проверен и готов к работе!"
    fi
fi

exit 0
