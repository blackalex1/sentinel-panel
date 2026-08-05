#!/bin/bash

# Force system and python to output in UTF-8
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8

# Navigate to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "[+] Проверка виртуального окружения..."
if [ ! -d ".venv" ]; then
    echo "[!] Создание виртуального окружения..."
    python3 -m venv .venv
fi

echo "[+] Активация окружения и установка зависимостей..."
source .venv/bin/activate
pip install -r requirements.txt

echo "[+] Запуск VPN-панели на случайном порту..."
python backend/main.py &

echo "[+] Запуск Telegram-бота..."
python bot/mini_bot.py &

echo "[+] VPN-панель и бот запущены в фоновом режиме."
echo "[+] Для остановки используйте killall python или kill <PID>."
