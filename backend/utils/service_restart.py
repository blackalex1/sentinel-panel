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
_pending_cores: set[str] = set()


def _do_restart(cores: set[str] | None = None) -> None:
    """Выполняется в daemon-потоке. Перезапускает необходимые сервисы."""
    restart_all = not cores or "all" in cores

    if restart_all or "xray" in cores:
        try:
            from backend.xray import write_xray_config, restart_xray
            write_xray_config()
            restart_xray()
        except Exception:
            logging.exception("service_restart: ошибка при рестарте Xray")

    if restart_all or "singbox" in cores or "sing-box" in cores:
        try:
            from backend.singbox import write_singbox_config, restart_singbox
            write_singbox_config(force=True)
            restart_singbox()
        except Exception:
            logging.exception("service_restart: ошибка при рестарте Sing-box")

    if restart_all or "hysteria" in cores or "hysteria2" in cores:
        try:
            from backend.hysteria import restart_hysteria
            restart_hysteria()
        except Exception:
            logging.exception("service_restart: ошибка при рестарте Hysteria")


def restart_services_background(delay: float = DEBOUNCE_SECONDS, core: str | None = None) -> None:
    """
    Планирует перезапуск сервисов в фоне и возвращает управление немедленно.

    Дебаунс DEBOUNCE_SECONDS: повторный вызов в течение этого интервала
    отменяет предыдущий таймер и ставит новый — итоговый рестарт будет
    ровно один, через delay после последнего вызова.
    """
    global _pending_timer, _pending_cores

    if delay is None or delay < 0:
        delay = DEBOUNCE_SECONDS

    with _lock:
        if core:
            _pending_cores.add(core.lower())
        else:
            _pending_cores.add("all")

        if _pending_timer is not None:
            _pending_timer.cancel()

        def _runner():
            with _lock:
                cores_to_run = set(_pending_cores)
                _pending_cores.clear()
            _do_restart(cores_to_run)

        _pending_timer = threading.Timer(delay, _runner)
        _pending_timer.daemon = True
        _pending_timer.start()
