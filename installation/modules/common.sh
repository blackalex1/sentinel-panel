#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel Updater - Common Utilities & Helpers Module
# ==============================================================================

# Color definitions
COLOR_RESET="\033[0m"
COLOR_BOLD="\033[1m"
COLOR_RED="\033[0;31m"
COLOR_GREEN="\033[0;32m"
COLOR_YELLOW="\033[0;33m"
COLOR_CYAN="\033[0;36m"
COLOR_BLUE="\033[0;34m"

log_info() {
    echo -e "${COLOR_CYAN}[+] $*${COLOR_RESET}"
}

log_success() {
    echo -e "${COLOR_GREEN}[✓] $*${COLOR_RESET}"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[!] $*${COLOR_RESET}"
}

log_error() {
    echo -e "${COLOR_RED}[-] $*${COLOR_RESET}"
}

log_banner() {
    echo -e "${COLOR_BLUE}====================================================${COLOR_RESET}"
    echo -e "${COLOR_BOLD}$*${COLOR_RESET}"
    echo -e "${COLOR_BLUE}====================================================${COLOR_RESET}"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Пожалуйста, запустите скрипт с правами root (используйте sudo)."
        exit 1
    fi
}

detect_python() {
    local CANDIDATES=(
        "$SCRIPT_DIR/.venv/bin/python3"
        "$SCRIPT_DIR/venv/bin/python3"
        "/opt/sentinel-panel/.venv/bin/python3"
        "$(command -v python3 2>/dev/null)"
        "$(command -v python 2>/dev/null)"
    )
    for py in "${CANDIDATES[@]}"; do
        if [ -x "$py" ]; then
            PYTHON_BIN="$py"
            return 0
        fi
    done
    PYTHON_BIN="python3"
}

cleanup_tunnel() {
    if [ -n "$TUNNEL_PID" ]; then
        kill -TERM "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
        TUNNEL_PID=""
    fi
    fuser -k -9 10818/tcp 10819/tcp 2>/dev/null || true
    pkill -9 -f "(proxy_rotator|sing-box.*failover|xray.*failover)" 2>/dev/null || true
}

free_proxy_ports() {
    fuser -k -9 10818/tcp 10819/tcp 2>/dev/null || true
    pkill -9 -f "(proxy_rotator|sing-box.*failover|xray.*failover)" 2>/dev/null || true
}

setup_traps() {
    trap cleanup_tunnel EXIT INT TERM
}
