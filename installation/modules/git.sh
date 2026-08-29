#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel Updater - Git Repository Synchronization Module
# ==============================================================================

pull_panel_git_direct() {
    if [ -n "$VALID_PROXY" ]; then
        git -c "http.proxy=$VALID_PROXY" -c "https.proxy=$VALID_PROXY" fetch origin main && git reset --hard origin/main
    else
        git fetch origin main && git reset --hard origin/main
    fi
}

update_git_codebase() {
    log_info "Получение последних обновлений из Git..."
    git remote set-url origin https://github.com/blackalex1/sentinel-panel.git 2>/dev/null
    local OLD_HEAD
    OLD_HEAD=$(git rev-parse HEAD 2>/dev/null)

    local PULL_OK=0
    if pull_panel_git_direct; then
        PULL_OK=1
    else
        log_warn "Прямое подключение к GitHub не удалось. Пробуем через быстрое зеркало..."
        local MIRRORS=(
            "https://gh-proxy.com/https://github.com/blackalex1/sentinel-panel.git"
            "https://ghfast.top/https://github.com/blackalex1/sentinel-panel.git"
            "https://gh.ddlc.top/https://github.com/blackalex1/sentinel-panel.git"
            "https://ghproxy.net/https://github.com/blackalex1/sentinel-panel.git"
        )
        for mirror_url in "${MIRRORS[@]}"; do
            if git -c "http.proxy=" -c "https.proxy=" fetch "$mirror_url" main 2>/dev/null && git reset --hard FETCH_HEAD; then
                log_success "Git успешно обновлен через зеркало $(echo "$mirror_url" | awk -F'/' '{print $3}')!"
                PULL_OK=1
                break
            fi
        done
    fi

    if [ "$PULL_OK" -eq 1 ]; then
        local NEW_HEAD
        NEW_HEAD=$(git rev-parse HEAD 2>/dev/null)
        if [ "$OLD_HEAD" != "$NEW_HEAD" ] && [ -n "$OLD_HEAD" ]; then
            log_success "Изменения успешно применены:"
            git diff --stat "$OLD_HEAD" "$NEW_HEAD"
        else
            log_success "Кодовая база уже актуальна (Already up to date)."
        fi
        log_success "Этап обновления Git завершен успешно."
    else
        log_warn "Не удалось обновить Git. Продолжаем работу с локальной версией репозитория..."
    fi
}
