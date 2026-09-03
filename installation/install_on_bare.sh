#!/bin/bash

# Force system and python to output in UTF-8
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8

# Navigate to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "[+] Проверка виртуального окружения Python..."
if [ ! -d ".venv" ]; then
    echo "[!] Создание виртуального окружения..."
    python3 -m venv .venv || python -m venv .venv
fi

echo "[+] Активация окружения и установка зависимостей..."
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
fi

pip install --upgrade pip 2>/dev/null || true
pip install -r requirements.txt

echo "[+] Загрузка актуального ядра Sentinel-Core (Go CLI + C-FFI)..."
if [ -f "$SCRIPT_DIR/installation/fetch_core.sh" ]; then
    bash "$SCRIPT_DIR/installation/fetch_core.sh" "$SCRIPT_DIR/bin" --auto
fi

echo "[+] Загрузка proxy-движков (Sing-box, Xray-core, Hysteria 2)..."
if [ -f "$SCRIPT_DIR/installation/fetch_proxy_core.sh" ]; then
    bash "$SCRIPT_DIR/installation/fetch_proxy_core.sh" "$SCRIPT_DIR/bin" --auto
fi

chmod +x "$SCRIPT_DIR/bin"/* 2>/dev/null || true

export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

echo "[+] Запуск Sentinel Panel в фоновом режиме..."
python -m backend.main &
PANEL_PID=$!

echo "[+] Sentinel Panel запущена (PID: $PANEL_PID)."
echo "[+] Управление Telegram-ботом и ядрами осуществляется автоматически через Sentinel-Core."
echo "[+] Для остановки процесса используйте: kill $PANEL_PID"
