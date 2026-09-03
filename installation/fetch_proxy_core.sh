#!/usr/bin/env bash

# ==============================================================================
# Sing-box, Xray-Core & Hysteria 2 Proxy Engines Downloader for Sentinel-Panel
# Fetches official Sing-box, Xray-core and Hysteria 2 binaries for current OS/Arch
# Supports HTTP/HTTPS/SOCKS5 Proxies, VPN, and GitHub Fast Mirrors
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"
AUTO_MODE=0
PROXY_URL=""

# Colors for interactive UI
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

while [[ $# -gt 0 ]]; do
    case "$1" in
        --auto|-y)
            AUTO_MODE=1
            shift
            ;;
        --proxy|-p)
            PROXY_URL="$2"
            shift 2
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

# Check PROXY_URL from .env if not set via CLI
if [ -z "$PROXY_URL" ]; then
    for env_file in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/config/.env" ".env"; do
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

VALID_PROXY=""
CURL_OPTS=("-fsSL" "--connect-timeout" "10" "--retry" "2")

if [ -n "$PROXY_URL" ]; then
    if [[ "$PROXY_URL" =~ ^(http|https|socks4|socks5|socks5h):// ]]; then
        VALID_PROXY="$PROXY_URL"
        echo -e "${CYAN}[+] Использование прокси для proxy-движков: $VALID_PROXY${NC}"
        export http_proxy="$VALID_PROXY"
        export https_proxy="$VALID_PROXY"
        export all_proxy="$VALID_PROXY"
        export HTTP_PROXY="$VALID_PROXY"
        export HTTPS_PROXY="$VALID_PROXY"
        export ALL_PROXY="$VALID_PROXY"
        CURL_OPTS+=("-x" "$VALID_PROXY")
    fi
fi

# 1. Detect OS
OS_TYPE="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$OS_TYPE" in
    linux*)   OS="linux" ;;
    darwin*)  OS="macos" ;;
    msys*|mingw*|cygwin*) OS="windows" ;;
    *)        OS="linux" ;;
esac

# 2. Detect Architecture
ARCH_RAW="$(uname -m | tr '[:upper:]' '[:lower:]')"
case "$ARCH_RAW" in
    x86_64|amd64)
        ARCH_SINGBOX="amd64"
        ARCH_XRAY="64"
        ARCH_HYSTERIA="amd64"
        ;;
    aarch64|arm64)
        ARCH_SINGBOX="arm64"
        ARCH_XRAY="arm64-v8a"
        ARCH_HYSTERIA="arm64"
        ;;
    armv7*|armhf)
        ARCH_SINGBOX="armv7"
        ARCH_XRAY="arm32-v7a"
        ARCH_HYSTERIA="armv7"
        ;;
    *)
        ARCH_SINGBOX="amd64"
        ARCH_XRAY="64"
        ARCH_HYSTERIA="amd64"
        ;;
esac

# Check existing installations
SB_INSTALLED="Не установлено"
XRAY_INSTALLED="Не установлено"
HYSTERIA_INSTALLED="Не установлено"

if [ -f "$BIN_DIR/sing-box" ] || [ -f "$BIN_DIR/sing-box.exe" ] || command -v sing-box &>/dev/null; then
    SB_BIN="$BIN_DIR/sing-box"
    [ ! -f "$SB_BIN" ] && SB_BIN=$(command -v sing-box 2>/dev/null)
    if [ -x "$SB_BIN" ]; then
        SB_INSTALLED=$("$SB_BIN" version 2>/dev/null | head -n 1 || echo "Установлено")
    fi
fi

if [ -f "$BIN_DIR/xray" ] || [ -f "$BIN_DIR/xray.exe" ] || command -v xray &>/dev/null; then
    XRAY_BIN="$BIN_DIR/xray"
    [ ! -f "$XRAY_BIN" ] && XRAY_BIN=$(command -v xray 2>/dev/null)
    if [ -x "$XRAY_BIN" ]; then
        XRAY_INSTALLED=$("$XRAY_BIN" version 2>/dev/null | head -n 1 || echo "Установлено")
    fi
fi

HY_BIN="$BIN_DIR/hysteria-linux-${ARCH_HYSTERIA}"
[ "$OS" = "windows" ] && HY_BIN="$BIN_DIR/hysteria-windows-${ARCH_HYSTERIA}.exe"
[ ! -f "$HY_BIN" ] && [ -f "$BIN_DIR/hysteria" ] && HY_BIN="$BIN_DIR/hysteria"
[ ! -f "$HY_BIN" ] && [ -f "$BIN_DIR/hysteria.exe" ] && HY_BIN="$BIN_DIR/hysteria.exe"

if [ -f "$HY_BIN" ]; then
    if [ -x "$HY_BIN" ]; then
        HYSTERIA_INSTALLED=$("$HY_BIN" version 2>/dev/null | head -n 1 || echo "Установлено")
    fi
fi

fetch_singbox() {
    echo -e "${CYAN}[+] Загрузка Sing-box из официального репозитория SagerNet/sing-box...${NC}"
    local SB_TAG=""
    if command -v python3 &>/dev/null; then
        SB_TAG=$(python3 -c "
import urllib.request, json, os
urls = [
    'https://api.github.com/repos/SagerNet/sing-box/releases/latest',
    'https://gh-proxy.com/https://api.github.com/repos/SagerNet/sing-box/releases/latest',
    'https://ghfast.top/https://api.github.com/repos/SagerNet/sing-box/releases/latest',
    'https://ghproxy.net/https://api.github.com/repos/SagerNet/sing-box/releases/latest'
]
proxy = '$VALID_PROXY'
handlers = [urllib.request.ProxyHandler({'http': proxy, 'https': proxy})] if proxy else []
opener = urllib.request.build_opener(*handlers)
for u in urls:
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'SentinelPanel'})
        with opener.open(req, timeout=6) as r:
            tag = json.loads(r.read().decode('utf-8'))['tag_name']
            if tag:
                print(tag)
                exit(0)
    except Exception:
        continue
" 2>/dev/null)
    fi

    if [ -z "$SB_TAG" ]; then
        SB_TAG="v1.11.4"
    fi
    local VER_NUM="${SB_TAG#v}"

    local SB_FILENAME=""
    if [ "$OS" = "windows" ]; then
        SB_FILENAME="sing-box-${VER_NUM}-windows-${ARCH_SINGBOX}.zip"
    elif [ "$OS" = "macos" ]; then
        SB_FILENAME="sing-box-${VER_NUM}-darwin-${ARCH_SINGBOX}.tar.gz"
    else
        SB_FILENAME="sing-box-${VER_NUM}-linux-${ARCH_SINGBOX}.tar.gz"
    fi

    local SB_CANDIDATES=(
        "https://github.com/SagerNet/sing-box/releases/download/${SB_TAG}/${SB_FILENAME}"
        "https://gh-proxy.com/https://github.com/SagerNet/sing-box/releases/download/${SB_TAG}/${SB_FILENAME}"
        "https://ghfast.top/https://github.com/SagerNet/sing-box/releases/download/${SB_TAG}/${SB_FILENAME}"
        "https://ghproxy.net/https://github.com/SagerNet/sing-box/releases/download/${SB_TAG}/${SB_FILENAME}"
        "https://mirror.ghproxy.com/https://github.com/SagerNet/sing-box/releases/download/${SB_TAG}/${SB_FILENAME}"
    )

    local TMP_ARCHIVE="/tmp/singbox_latest.tar.gz"
    if [[ "$SB_FILENAME" == *.zip ]]; then
        TMP_ARCHIVE="/tmp/singbox_latest.zip"
    fi

    for URL in "${SB_CANDIDATES[@]}"; do
        rm -f "$TMP_ARCHIVE"
        if curl "${CURL_OPTS[@]}" -o "$TMP_ARCHIVE" "$URL" 2>/dev/null; then
            if [ -s "$TMP_ARCHIVE" ] && ! head -n 1 "$TMP_ARCHIVE" | grep -iqE "<!DOCTYPE|<html|404: Not Found|\{\"message\":"; then
                if [[ "$TMP_ARCHIVE" == *.tar.gz ]]; then
                    tar -xzf "$TMP_ARCHIVE" --strip-components=1 -C "$BIN_DIR" 2>/dev/null || tar -xzf "$TMP_ARCHIVE" -C "$BIN_DIR"
                elif command -v unzip &>/dev/null; then
                    unzip -q -o "$TMP_ARCHIVE" -d "/tmp/sb_extract" 2>/dev/null && cp /tmp/sb_extract/*/sing-box* "$BIN_DIR/" 2>/dev/null && rm -rf /tmp/sb_extract
                elif command -v python3 &>/dev/null; then
                    python3 -c "import zipfile, os; z = zipfile.ZipFile('$TMP_ARCHIVE'); [z.extract(f, '$BIN_DIR') for f in z.namelist() if 'sing-box' in f]"
                fi
                chmod +x "$BIN_DIR/sing-box" 2>/dev/null || chmod +x "$BIN_DIR/sing-box.exe" 2>/dev/null || true
                rm -f "$TMP_ARCHIVE"
                echo -e "${GREEN}✓ Sing-box ($SB_TAG) успешно установлен в $BIN_DIR${NC}"
                return 0
            fi
        fi
    done

    echo -e "${RED}⚠️ Не удалось загрузить Sing-box напрямую. Сохранена текущая версия.${NC}"
    return 1
}

fetch_xray() {
    echo -e "${CYAN}[+] Загрузка Xray-core из официального репозитория XTLS/Xray-core...${NC}"
    local XRAY_FILENAME=""
    if [ "$OS" = "windows" ]; then
        XRAY_FILENAME="Xray-windows-${ARCH_XRAY}.zip"
    elif [ "$OS" = "macos" ]; then
        XRAY_FILENAME="Xray-macos-${ARCH_XRAY}.zip"
    else
        XRAY_FILENAME="Xray-linux-${ARCH_XRAY}.zip"
    fi

    local XRAY_CANDIDATES=(
        "https://github.com/XTLS/Xray-core/releases/latest/download/${XRAY_FILENAME}"
        "https://gh-proxy.com/https://github.com/XTLS/Xray-core/releases/latest/download/${XRAY_FILENAME}"
        "https://ghfast.top/https://github.com/XTLS/Xray-core/releases/latest/download/${XRAY_FILENAME}"
        "https://ghproxy.net/https://github.com/XTLS/Xray-core/releases/latest/download/${XRAY_FILENAME}"
        "https://mirror.ghproxy.com/https://github.com/XTLS/Xray-core/releases/latest/download/${XRAY_FILENAME}"
    )

    local TMP_ZIP="/tmp/xray_latest.zip"
    for URL in "${XRAY_CANDIDATES[@]}"; do
        rm -f "$TMP_ZIP"
        if curl "${CURL_OPTS[@]}" -o "$TMP_ZIP" "$URL" 2>/dev/null; then
            if [ -s "$TMP_ZIP" ] && ! head -n 1 "$TMP_ZIP" | grep -iqE "<!DOCTYPE|<html|404: Not Found|\{\"message\":"; then
                if command -v unzip &>/dev/null; then
                    unzip -q -o "$TMP_ZIP" -d "$BIN_DIR" xray xray.exe geoip.dat geosite.dat 2>/dev/null || unzip -q -o "$TMP_ZIP" -d "$BIN_DIR"
                    chmod +x "$BIN_DIR/xray" 2>/dev/null || true
                    rm -f "$TMP_ZIP"
                    echo -e "${GREEN}✓ Xray-core успешно установлен в $BIN_DIR${NC}"
                    return 0
                elif command -v python3 &>/dev/null; then
                    python3 -c "import zipfile; zipfile.ZipFile('$TMP_ZIP').extractall('$BIN_DIR')"
                    chmod +x "$BIN_DIR/xray" 2>/dev/null || true
                    rm -f "$TMP_ZIP"
                    echo -e "${GREEN}✓ Xray-core успешно распакован в $BIN_DIR${NC}"
                    return 0
                fi
            fi
        fi
    done

    echo -e "${RED}⚠️ Не удалось загрузить Xray-core напрямую${NC}"
    return 1
}

fetch_hysteria() {
    echo -e "${CYAN}[+] Загрузка Hysteria 2 из официального репозитория apernet/hysteria...${NC}"
    local HY_FILENAME="hysteria-linux-${ARCH_HYSTERIA}"
    local HY_DEST="$BIN_DIR/hysteria-linux-${ARCH_HYSTERIA}"
    local HY_SYMLINK="$BIN_DIR/hysteria"

    if [ "$OS" = "windows" ]; then
        HY_FILENAME="hysteria-windows-${ARCH_HYSTERIA}.exe"
        HY_DEST="$BIN_DIR/hysteria-windows-${ARCH_HYSTERIA}.exe"
        HY_SYMLINK="$BIN_DIR/hysteria.exe"
    elif [ "$OS" = "macos" ]; then
        HY_FILENAME="hysteria-darwin-${ARCH_HYSTERIA}"
        HY_DEST="$BIN_DIR/hysteria-darwin-${ARCH_HYSTERIA}"
        HY_SYMLINK="$BIN_DIR/hysteria"
    fi

    local HY_CANDIDATES=(
        "https://github.com/apernet/hysteria/releases/latest/download/${HY_FILENAME}"
        "https://gh-proxy.com/https://github.com/apernet/hysteria/releases/latest/download/${HY_FILENAME}"
        "https://ghfast.top/https://github.com/apernet/hysteria/releases/latest/download/${HY_FILENAME}"
        "https://ghproxy.net/https://github.com/apernet/hysteria/releases/latest/download/${HY_FILENAME}"
        "https://mirror.ghproxy.com/https://github.com/apernet/hysteria/releases/latest/download/${HY_FILENAME}"
    )

    local TMP_HY="/tmp/${HY_FILENAME}.$$"
    for URL in "${HY_CANDIDATES[@]}"; do
        rm -f "$TMP_HY"
        if curl "${CURL_OPTS[@]}" -o "$TMP_HY" "$URL" 2>/dev/null; then
            if [ -s "$TMP_HY" ] && ! head -n 1 "$TMP_HY" | grep -iqE "<!DOCTYPE|<html|404: Not Found|\{\"message\":"; then
                rm -f "$HY_DEST"
                mv -f "$TMP_HY" "$HY_DEST"
                chmod +x "$HY_DEST" 2>/dev/null || true

                # Create alias / symlink
                if [ "$OS" != "windows" ]; then
                    ln -sf "$HY_DEST" "$HY_SYMLINK" 2>/dev/null || cp -f "$HY_DEST" "$HY_SYMLINK" 2>/dev/null || true
                else
                    cp -f "$HY_DEST" "$HY_SYMLINK" 2>/dev/null || true
                fi
                chmod +x "$HY_SYMLINK" 2>/dev/null || true

                echo -e "${GREEN}✓ Hysteria 2 успешно установлена в $BIN_DIR${NC}"
                return 0
            fi
        fi
    done

    echo -e "${RED}⚠️ Не удалось загрузить Hysteria 2 напрямую${NC}"
    return 1
}

fetch_geodata() {
    # Ensure geoip.dat and geosite.dat exist
    if [ ! -f "$BIN_DIR/geoip.dat" ] || [ ! -f "$BIN_DIR/geosite.dat" ]; then
        echo -e "${CYAN}[+] Загрузка баз маршрутизации geoip.dat и geosite.dat...${NC}"
        local GEOIP_URLS=(
            "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
            "https://gh-proxy.com/https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
            "https://ghfast.top/https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
        )
        local GEOSITE_URLS=(
            "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"
            "https://gh-proxy.com/https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"
            "https://ghfast.top/https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"
        )

        if [ ! -f "$BIN_DIR/geoip.dat" ]; then
            for u in "${GEOIP_URLS[@]}"; do
                if curl "${CURL_OPTS[@]}" -o "$BIN_DIR/geoip.dat" "$u" 2>/dev/null && [ -s "$BIN_DIR/geoip.dat" ]; then
                    break
                fi
            done
        fi

        if [ ! -f "$BIN_DIR/geosite.dat" ]; then
            for u in "${GEOSITE_URLS[@]}"; do
                if curl "${CURL_OPTS[@]}" -o "$BIN_DIR/geosite.dat" "$u" 2>/dev/null && [ -s "$BIN_DIR/geosite.dat" ]; then
                    break
                fi
            done
        fi
    fi
}

if [ "$AUTO_MODE" -eq 1 ]; then
    echo -e "${CYAN}[+] Автоматическая загрузка proxy-движков для Sentinel-Panel...${NC}"
    fetch_singbox || true
    fetch_xray || true
    fetch_hysteria || true
    fetch_geodata || true
else
    DEFAULT_PROXY_CHOICE="1"
    echo ""
    echo -e "${CYAN}====================================================${NC}"
    echo -e "${BLUE}🚀  ВЫБОР PROXY-ДВИЖКОВ ДЛЯ ПАНЕЛИ${NC}"
    echo -e "${CYAN}====================================================${NC}"
    echo -e "📌 Текущее состояние:"
    echo -e "  • ${YELLOW}Sing-box:${NC}   $SB_INSTALLED"
    echo -e "  • ${YELLOW}Xray-core:${NC}  $XRAY_INSTALLED"
    echo -e "  • ${YELLOW}Hysteria 2:${NC} $HYSTERIA_INSTALLED"
    echo -e "${CYAN}====================================================${NC}"
    echo -e "Варианты установки:"
    echo -e "  1) ${GREEN}🟢 Установить ВСЕ движки (Sing-box + Xray-core + Hysteria 2) [Рекомендуется]${NC}"
    echo -e "  2) 🟡 Только Sing-box"
    echo -e "  3) 🟡 Только Xray-core"
    echo -e "  4) 🟡 Только Hysteria 2"
    echo -e "  5) ⏹️  Оставить текущие версии (Пропустить обновление)"
    read -t 15 -p "Выберите вариант [1-5] (по умолчанию $DEFAULT_PROXY_CHOICE): " PROXY_CHOICE || PROXY_CHOICE="$DEFAULT_PROXY_CHOICE"
    PROXY_CHOICE="${PROXY_CHOICE:-$DEFAULT_PROXY_CHOICE}"

    case "$PROXY_CHOICE" in
        1) fetch_singbox; fetch_xray; fetch_hysteria; fetch_geodata ;;
        2) fetch_singbox ;;
        3) fetch_xray; fetch_geodata ;;
        4) fetch_hysteria ;;
        5) echo -e "${GREEN}[+] Обновление прокси-движков пропущено.${NC}" ;;
        *) fetch_singbox; fetch_xray; fetch_hysteria; fetch_geodata ;;
    esac
fi

# Ensure all binaries in bin are executable
chmod +x "$BIN_DIR"/* 2>/dev/null || true

exit 0
