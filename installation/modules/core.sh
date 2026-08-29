#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel Updater - Sentinel-Core Engine Binary Module
# ==============================================================================

update_sentinel_core_engine() {
    log_info "Проверка и обновление бинарника ядра sentinel-core..."
    local FETCH_SCRIPT="$SCRIPT_DIR/installation/fetch_core.sh"
    if [ -f "$FETCH_SCRIPT" ]; then
        chmod +x "$FETCH_SCRIPT"
        bash "$FETCH_SCRIPT" "$SCRIPT_DIR/bin" "${FETCH_ARGS[@]}"
    else
        log_warn "Скрипт $FETCH_SCRIPT не найден. Пропуск обновления ядра."
    fi
}
