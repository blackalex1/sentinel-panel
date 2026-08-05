# Watchdog state to prevent circular dependencies between scheduler and service wrappers

consecutive_xray_restarts = 0
consecutive_hysteria_restarts = 0
consecutive_singbox_restarts = 0
in_watchdog_context = False

def reset_xray_watchdog():
    global consecutive_xray_restarts
    consecutive_xray_restarts = 0

def reset_hysteria_watchdog():
    global consecutive_hysteria_restarts
    consecutive_hysteria_restarts = 0

def reset_singbox_watchdog():
    global consecutive_singbox_restarts
    consecutive_singbox_restarts = 0

