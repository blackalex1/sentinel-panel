#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel Updater - Host Systemd Service (sentinel-agent) Module
# ==============================================================================

update_systemd_host_agent() {
    log_info "Настройка и перезапуск системной службы sentinel-agent..."

    if systemctl is-active --quiet spectre-agent 2>/dev/null || [ -f "/etc/systemd/system/spectre-agent.service" ]; then
        log_info "Очистка устаревшей службы spectre-agent..."
        systemctl stop spectre-agent 2>/dev/null || true
        systemctl disable spectre-agent 2>/dev/null || true
        rm -f /etc/systemd/system/spectre-agent.service
    fi

    local SERVICE_TEMPLATE="$SCRIPT_DIR/host/sentinel-agent.service"
    local SERVICE_DEST="/etc/systemd/system/sentinel-agent.service"

    if [ -f "$SERVICE_TEMPLATE" ]; then
        sed "s|/opt/sentinel-panel|$SCRIPT_DIR|g" "$SERVICE_TEMPLATE" > "$SERVICE_DEST"
        systemctl daemon-reload
        systemctl enable sentinel-agent
        systemctl restart sentinel-agent
        log_success "Служба sentinel-agent успешно настроена и перезапущена!"
    fi
}
