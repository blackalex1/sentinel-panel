#!/bin/bash

# ==============================================================================
# Sentinel-Core Binary & Library Downloader
# Automatically fetches the latest compiled sentinel-core engine for current OS/Arch
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${1:-$SCRIPT_DIR/bin}"

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

echo "[+] Detecting platform: OS=$OS, ARCH=$ARCH..."

REPO="blackalex1/sentinel-core"
GITHUB_API="https://api.github.com/repos/$REPO/releases/latest"
GITHUB_DL_BASE="https://github.com/$REPO/releases/latest/download"

# Determine target binary name
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

echo "[+] Downloading $BIN_NAME from $REPO releases..."

DOWNLOAD_CMD=""
if command -v curl &>/dev/null; then
    DOWNLOAD_CMD="curl -fsSL --connect-timeout 10 --retry 3"
elif command -v wget &>/dev/null; then
    DOWNLOAD_CMD="wget -qO-"
fi

if [ -z "$DOWNLOAD_CMD" ]; then
    echo "[!] Neither curl nor wget is available. Skipping sentinel-core binary download."
    exit 0
fi

# Download CLI binary
TMP_BIN="/tmp/$BIN_NAME.$$"
if curl -fsSL --connect-timeout 10 --retry 2 "$GITHUB_DL_BASE/$BIN_NAME" -o "$TMP_BIN" 2>/dev/null; then
    if [ -s "$TMP_BIN" ]; then
        mv "$TMP_BIN" "$DEST_BIN"
        chmod +x "$DEST_BIN"
        echo "[+] Successfully installed sentinel-core binary at $DEST_BIN"
        
        # Quick verification test
        if "$DEST_BIN" version &>/dev/null || "$DEST_BIN" --help &>/dev/null || "$DEST_BIN" preset list &>/dev/null; then
            echo "[+] sentinel-core binary verified successfully!"
        fi
    else
        rm -f "$TMP_BIN"
        echo "[-] Release asset $BIN_NAME empty or not found yet on GitHub Releases."
    fi
else
    rm -f "$TMP_BIN"
    echo "[-] Release asset $BIN_NAME not yet published or unreachable. Preserving local version if present."
fi

# Download C-Shared library if applicable (optional enhancement)
TMP_LIB="/tmp/$LIB_NAME.$$"
if curl -fsSL --connect-timeout 10 --retry 2 "$GITHUB_DL_BASE/$LIB_NAME" -o "$TMP_LIB" 2>/dev/null; then
    if [ -s "$TMP_LIB" ]; then
        mv "$TMP_LIB" "$DEST_LIB"
        chmod +x "$DEST_LIB" 2>/dev/null || true
        echo "[+] Successfully installed sentinel-core C-Shared library at $DEST_LIB"
    else
        rm -f "$TMP_LIB"
    fi
else
    rm -f "$TMP_LIB"
fi

# Download header file (sentinel-core.h)
TMP_HDR="/tmp/sentinel-core.h.$$"
if curl -fsSL --connect-timeout 10 --retry 2 "$GITHUB_DL_BASE/sentinel-core.h" -o "$TMP_HDR" 2>/dev/null; then
    if [ -s "$TMP_HDR" ]; then
        mv "$TMP_HDR" "$BIN_DIR/sentinel-core.h"
    else
        rm -f "$TMP_HDR"
    fi
else
    rm -f "$TMP_HDR"
fi

exit 0
