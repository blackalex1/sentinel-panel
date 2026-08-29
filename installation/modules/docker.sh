#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel Updater - Docker & Database Migration Module
# ==============================================================================

rebuild_and_restart_docker() {
    log_info "Пересборка и перезапуск Docker-контейнеров..."

    # Kill old background server cores, but preserve active rotator tunnel
    if [ -n "$TUNNEL_PID" ]; then
        pgrep -f "sing-box.*singbox_server" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
        pgrep -f "xray.*xray_server" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
    else
        pkill -9 -f "sing-box" 2>/dev/null || true
        pkill -9 -f "xray" 2>/dev/null || true
    fi

    docker ps -a --filter "name=spectre" -q | xargs -r docker rm -f 2>/dev/null || true
    docker ps -a --filter "name=sentinel" -q | xargs -r docker rm -f 2>/dev/null || true
    docker compose down --remove-orphans 2>/dev/null || true

    # Auto-migrate legacy database volume (spectre-panel_pgdata / panel_pgdata / installation_pgdata -> sentinel-panel_pgdata)
    for v in spectre-panel_pgdata panel_pgdata installation_pgdata; do
        if docker volume inspect "$v" &>/dev/null; then
            log_info "Обнаружен устаревший том базы данных '$v'."
            if ! docker volume inspect sentinel-panel_pgdata &>/dev/null; then
                log_info "Миграция данных из '$v' в 'sentinel-panel_pgdata'..."
                docker volume create --label "com.docker.compose.project=sentinel-panel" --label "com.docker.compose.volume=pgdata" sentinel-panel_pgdata >/dev/null 2>&1
                docker run --rm -v "$v":/from -v sentinel-panel_pgdata:/to postgres:16-alpine sh -c "rm -rf /to/* 2>/dev/null || true; cp -a /from/. /to/"
                log_success "Данные БД успешно перенесены в 'sentinel-panel_pgdata'!"
            fi
            log_info "Очистка устаревшего тома '$v'..."
            docker volume rm -f "$v" >/dev/null 2>&1 || true
        fi
    done

    # Ensure sentinel-panel_pgdata has compose labels to eliminate 'not created by Docker Compose' warning
    if docker volume inspect sentinel-panel_pgdata &>/dev/null; then
        local LABEL_CHECK
        LABEL_CHECK=$(docker volume inspect sentinel-panel_pgdata --format '{{index .Labels "com.docker.compose.volume"}}' 2>/dev/null || true)
        if [ "$LABEL_CHECK" != "pgdata" ]; then
            log_info "Добавление Docker Compose меток к 'sentinel-panel_pgdata'..."
            docker volume create --label "com.docker.compose.project=sentinel-panel" --label "com.docker.compose.volume=pgdata" sentinel-panel_pgdata_migrated >/dev/null 2>&1
            docker run --rm -v sentinel-panel_pgdata:/from -v sentinel-panel_pgdata_migrated:/to postgres:16-alpine sh -c "cp -a /from/. /to/"
            docker volume rm -f sentinel-panel_pgdata >/dev/null 2>&1
            docker volume create --label "com.docker.compose.project=sentinel-panel" --label "com.docker.compose.volume=pgdata" sentinel-panel_pgdata >/dev/null 2>&1
            docker run --rm -v sentinel-panel_pgdata_migrated:/from -v sentinel-panel_pgdata:/to postgres:16-alpine sh -c "cp -a /from/. /to/"
            docker volume rm -f sentinel-panel_pgdata_migrated >/dev/null 2>&1
        fi
    fi

    # Clean up proxy environment variables before running docker compose to allow direct build and pip install
    clear_proxy_environment

    if docker compose up -d --build; then
        log_success "Docker контейнеры успешно пересобраны и запущены!"
    else
        log_error "Не удалось пересобрать или запустить Docker контейнеры."
        return 1
    fi
}

stream_docker_logs() {
    log_banner "[✓] Обновление успешно завершено!"
    echo -e "[ℹ️] Подключение к живому потоку логов панели (Нажмите ${COLOR_BOLD}CTRL+C${COLOR_RESET} для выхода в терминал):"
    log_banner ""
    docker compose logs -f --tail 30 sentinel-panel
}
