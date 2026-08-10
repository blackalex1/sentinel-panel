"""
service_restart.py
------------------
Утилита для фонового дебаунсированного рестарта сервисов (Xray / Sing-box / Hysteria).

Вместо того чтобы блокировать HTTP-ответ на 20-30 секунд пока сервисы
последовательно перезапускаются — функция restart_services_background()
немедленно возвращает управление, а рестарт выполняется в daemon-потоке.

Дебаунс (DEBOUNCE_SECONDS):
    Если за DEBOUNCE_SECONDS после вызова поступает ещё один вызов,
    таймер сбрасывается. Это позволяет схлопывать серии быстрых изменений
    (например импорт 20 правил подряд) в единственный фактический рестарт.
"""

import threading
import logging

# Задержка перед фактическим рестартом (секунды).
# Схлопывает серии вызовов в один рестарт.
DEBOUNCE_SECONDS = 0.3

_lock = threading.Lock()
_pending_timer: threading.Timer | None = None


def _do_restart() -> None:
    """Выполняется в daemon-потоке. Перезапускает все три сервиса."""
    try:
        from backend.xray import write_xray_config, restart_xray
        write_xray_config()
        restart_xray()
    except Exception:
        logging.exception("service_restart: ошибка при рестарте Xray")

    try:
        from backend.singbox import write_singbox_config, restart_singbox
        write_singbox_config(force=True)
        restart_singbox()
    except Exception:
        logging.exception("service_restart: ошибка при рестарте Sing-box")

    try:
        from backend.hysteria import restart_hysteria
        restart_hysteria()
    except Exception:
        logging.exception("service_restart: ошибка при рестарте Hysteria")


def restart_services_background() -> None:
    """
    Планирует перезапуск сервисов в фоне и возвращает управление немедленно.

    Дебаунс DEBOUNCE_SECONDS: повторный вызов в течение этого интервала
    отменяет предыдущий таймер и ставит новый — итоговый рестарт будет
    ровно один, через DEBOUNCE_SECONDS после последнего вызова.
    """
    global _pending_timer

    with _lock:
        if _pending_timer is not None:
            _pending_timer.cancel()

        _pending_timer = threading.Timer(DEBOUNCE_SECONDS, _do_restart)
        _pending_timer.daemon = True
        _pending_timer.start()
