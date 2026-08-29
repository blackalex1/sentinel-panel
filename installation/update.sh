#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel - Main Update Orchestrator
# Modular, Resilient Update Script for Sentinel Panel & Core Engine
# ==============================================================================

set -e

# Navigate to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

MODULES_DIR="$SCRIPT_DIR/installation/modules"

# Source all modular components
# shellcheck source=modules/common.sh
source "$MODULES_DIR/common.sh"
# shellcheck source=modules/dns.sh
source "$MODULES_DIR/dns.sh"
# shellcheck source=modules/proxy.sh
source "$MODULES_DIR/proxy.sh"
# shellcheck source=modules/git.sh
source "$MODULES_DIR/git.sh"
# shellcheck source=modules/core.sh
source "$MODULES_DIR/core.sh"
# shellcheck source=modules/docker.sh
source "$MODULES_DIR/docker.sh"
# shellcheck source=modules/service.sh
source "$MODULES_DIR/service.sh"

# 0. Initial validation & setup
check_root
setup_traps
free_proxy_ports
detect_python

# Default configuration variables
PROXY_URL=""
NO_PROXY=0
AUTO_MODE=0
USE_ROTATOR=1
TUNNEL_PID=""

# Parse CLI arguments
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

# Initialize settings from .env / env
init_proxy_settings

# Interactive network selection menu (if TTY terminal)
show_proxy_menu

# Ensure unencrypted bootstrap DNS resolution
ensure_unencrypted_dns

# Pre-fetch proxy engine and launch rotator tunnel if selected
prefetch_proxy_engine
start_vpn_rotator
apply_proxy_environment

log_banner "🔄 UPDATING SENTINEL PANEL"

# 1. Update Git codebase with automatic CDN mirror fallback
update_git_codebase

# 2. Update Sentinel-Core engine binary from GitHub releases
update_sentinel_core_engine

# 3. Rebuild and restart Docker containers with database volume migration
rebuild_and_restart_docker

# 4. Update and restart host agent systemd service
update_systemd_host_agent

# 5. Connect to live logs
stream_docker_logs
