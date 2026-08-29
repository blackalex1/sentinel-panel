#!/usr/bin/env bash

# ==============================================================================
# Sentinel Panel Updater - Network, Proxy & VPN Rotator Module
# ==============================================================================

init_proxy_settings() {
    # Check PROXY_URL from .env if not specified via CLI
    if [ -z "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
        for env_file in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/config/.env"; do
            if [ -f "$env_file" ]; then
                local ENV_P
                ENV_P=$(grep -E '^[[:space:]]*PROXY_URL=' "$env_file" 2>/dev/null | cut -d'=' -f2- | tr -d '"'\'' ')
                if [ -n "$ENV_P" ]; then
                    PROXY_URL="$ENV_P"
                    break
                fi
            fi
        done
    fi
}

show_proxy_menu() {
    if [ -t 0 ] && [ "$AUTO_MODE" -eq 0 ] && [ "$NO_PROXY" -eq 0 ]; then
        log_banner "🌐 НАСТРОЙКА СЕТИ И ПРОКСИ ДЛЯ ОБНОВЛЕНИЯ ПАНЕЛИ"
        echo "Выберите режим подключения к GitHub для загрузки релизов:"
        echo "  1) 🟢 Автоматический VPN / Прокси ротатор [Рекомендуется / По умолчанию]"
        echo "  2) 🌐 Прямое соединение к GitHub (с авто-фолбэком на CDN-зеркала при блокировке)"
        echo "  3) 🔌 Использовать существующий HTTP / SOCKS5 прокси"

        while true; do
            read -r -t 15 -p "Выберите вариант [1-3] (по умолчанию 1): " NET_CHOICE || NET_CHOICE="1"
            NET_CHOICE="${NET_CHOICE:-1}"
            NET_CHOICE=$(echo "$NET_CHOICE" | tr -d '[:space:]\\/')
            case "$NET_CHOICE" in
                1)
                    USE_ROTATOR=1
                    break
                    ;;
                2)
                    USE_ROTATOR=0
                    NO_PROXY=1
                    break
                    ;;
                3)
                    USE_ROTATOR=0
                    while true; do
                        read -r -p "Введите адрес прокси (например socks5://127.0.0.1:10808): " USER_P
                        USER_P=$(echo "$USER_P" | tr -d '[:space:]')
                        if [[ "$USER_P" =~ ^(http|https|socks4|socks5|socks5h):// ]]; then
                            PROXY_URL="$USER_P"
                            break
                        else
                            echo "❌ Неверный формат прокси! URL должен начинаться с http://, https://, socks5:// или socks5h://"
                        fi
                    done
                    break
                    ;;
                *)
                    echo "❌ Неверный ввод '$NET_CHOICE'. Пожалуйста, введите цифру 1, 2 или 3."
                    ;;
            esac
        done
        echo ""
    fi
}

prefetch_proxy_engine() {
    if [ "$USE_ROTATOR" -eq 1 ] && [ "$NO_PROXY" -eq 0 ]; then
        if [ ! -f "$SCRIPT_DIR/bin/sing-box" ] && [ ! -f "$SCRIPT_DIR/bin/xray" ] && ! command -v sing-box &>/dev/null && ! command -v xray &>/dev/null; then
            if [ -f "$SCRIPT_DIR/installation/fetch_proxy_core.sh" ]; then
                chmod +x "$SCRIPT_DIR/installation/fetch_proxy_core.sh"
                bash "$SCRIPT_DIR/installation/fetch_proxy_core.sh" "$SCRIPT_DIR/bin" --auto || true
            fi
        fi
    fi
}

start_vpn_rotator() {
    ROTATOR_ACTIVE_PROXY=""
    if [ "$USE_ROTATOR" -eq 1 ] && [ "$NO_PROXY" -eq 0 ]; then
        log_info "Запуск Sentinel Proxy Rotator для поиска рабочего VPN..."
        local ROTATOR_CMD=("$PYTHON_BIN" -m backend.proxy_rotator --port 10818)
        if [ -n "$PROXY_URL" ] && [[ "$PROXY_URL" =~ ^(ss|vless|vmess|trojan|hysteria2):// ]]; then
            ROTATOR_CMD+=(--node "$PROXY_URL")
        else
            ROTATOR_CMD+=(--find-and-start)
        fi

        # Launch in background and monitor PROXY_READY with real-time logs
        local TEMP_ROTATOR_LOG="/tmp/panel_rotator_start.log"
        rm -f "$TEMP_ROTATOR_LOG"
        "${ROTATOR_CMD[@]}" > "$TEMP_ROTATOR_LOG" 2>&1 &
        TUNNEL_PID=$!

        local LAST_LINE_COUNT=0
        for ((i=0; i<180; i++)); do
            if [ -f "$TEMP_ROTATOR_LOG" ]; then
                local CURRENT_LINE_COUNT
                CURRENT_LINE_COUNT=$(wc -l < "$TEMP_ROTATOR_LOG" 2>/dev/null || echo 0)
                if [ "$CURRENT_LINE_COUNT" -gt "$LAST_LINE_COUNT" ]; then
                    tail -n +"$((LAST_LINE_COUNT + 1))" "$TEMP_ROTATOR_LOG" 2>/dev/null | grep -v "PROXY_READY:" | while read -r line; do
                        [ -n "$line" ] && echo "    $line"
                    done
                    LAST_LINE_COUNT="$CURRENT_LINE_COUNT"
                fi
            fi

            if grep -q "PROXY_READY:" "$TEMP_ROTATOR_LOG" 2>/dev/null; then
                ROTATOR_ACTIVE_PROXY=$(grep -m1 "PROXY_READY:" "$TEMP_ROTATOR_LOG" | cut -d':' -f2- | tr -d '\r\n ')
                log_success "VPN-туннель успешно поднят на $ROTATOR_ACTIVE_PROXY!"
                break
            fi

            if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
                log_error "Процесс ротатора завершился до установления соединения. Лог:"
                cat "$TEMP_ROTATOR_LOG" 2>/dev/null
                break
            fi
            sleep 0.5
        done

        if [ -z "$ROTATOR_ACTIVE_PROXY" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
            log_warn "Превышено время ожидания ответа от VPN-нод. Продолжаем обновление без ротатора..."
            kill -TERM "$TUNNEL_PID" 2>/dev/null || true
            TUNNEL_PID=""
        fi
    fi
}

apply_proxy_environment() {
    VALID_PROXY=""
    FETCH_ARGS=()

    if [ -n "$ROTATOR_ACTIVE_PROXY" ]; then
        VALID_PROXY="$ROTATOR_ACTIVE_PROXY"
    elif [ -n "$PROXY_URL" ] && [ "$NO_PROXY" -eq 0 ]; then
        if [[ "$PROXY_URL" =~ ^(http|https|socks4|socks5|socks5h):// ]]; then
            VALID_PROXY="$PROXY_URL"
        fi
    fi

    if [ -n "$VALID_PROXY" ]; then
        log_success "Активное прокси-соединение для обновления: $VALID_PROXY"
        export http_proxy="$VALID_PROXY"
        export https_proxy="$VALID_PROXY"
        export all_proxy="$VALID_PROXY"
        export HTTP_PROXY="$VALID_PROXY"
        export HTTPS_PROXY="$VALID_PROXY"
        export ALL_PROXY="$VALID_PROXY"
        FETCH_ARGS+=("--proxy" "$VALID_PROXY")
    else
        log_info "Прокси не активен. Будут задействованы быстрые CDN-зеркала и прямые соединения."
    fi

    if [ "$AUTO_MODE" -eq 1 ]; then
        FETCH_ARGS+=("--auto")
    fi
}

clear_proxy_environment() {
    unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
}
