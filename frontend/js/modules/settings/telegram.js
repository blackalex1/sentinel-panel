import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadSettings } from "./core.js";

export function setupTelegramListeners() {
    const telegram2faEnableInput = document.getElementById("setting-telegram-2fa-enable");
    if (telegram2faEnableInput) {
        telegram2faEnableInput.addEventListener("change", async (e) => {
            const isChecked = e.target.checked;
            telegram2faEnableInput.disabled = true;
            
            if (isChecked) {
                const telegramTokenInput = document.getElementById("setting-telegram-token");
                const telegramAdminIdsInput = document.getElementById("setting-telegram-admin-ids");
                const hasToken = telegramTokenInput && telegramTokenInput.value.trim() && telegramTokenInput.value.trim() !== "••••••••";
                const hasAdminIds = telegramAdminIdsInput && telegramAdminIdsInput.value.trim();
                
                if (!hasToken || !hasAdminIds) {
                    showToast(t("telegram_2fa_config_warning", "Внимание: Убедитесь, что настроили токен бота и ID администраторов в блоке интеграции ниже!"), "info");
                }
            }

            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    telegram_2fa_enabled: isChecked
                })
            });
            telegram2faEnableInput.disabled = false;
            
            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
                e.target.checked = !isChecked;
            }
        });
    }

    // Card 2: Telegram Settings Save
    const btnSaveTelegram = document.getElementById("btn-save-telegram");
    if (btnSaveTelegram) {
        btnSaveTelegram.addEventListener("click", async () => {
            const telegramTokenInput = document.getElementById("setting-telegram-token");
            const telegramToken = telegramTokenInput ? telegramTokenInput.value.trim() : "";
            const telegramAdminIdsInput = document.getElementById("setting-telegram-admin-ids");
            const telegramAdminIds = telegramAdminIdsInput ? telegramAdminIdsInput.value.trim() : "";
            const telegram2faEnableInput = document.getElementById("setting-telegram-2fa-enable");
            const telegram2faEnable = telegram2faEnableInput ? telegram2faEnableInput.checked : false;
            const telegramBotEnableInput = document.getElementById("setting-telegram-bot-enable");
            const telegramBotEnable = telegramBotEnableInput ? telegramBotEnableInput.checked : true;
            const telegramClientEventsEnableInput = document.getElementById("setting-telegram-client-events-enable");
            const telegramClientEventsEnable = telegramClientEventsEnableInput ? telegramClientEventsEnableInput.checked : true;

            btnSaveTelegram.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    telegram_bot_token: telegramToken,
                    telegram_admin_ids: telegramAdminIds,
                    telegram_2fa_enabled: telegram2faEnable,
                    telegram_bot_enabled: telegramBotEnable,
                    telegram_client_events_enabled: telegramClientEventsEnable
                })
            });
            btnSaveTelegram.disabled = false;

            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
                loadSettings();
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
            }
        });
    }

    // Card 2: Telegram Bot Restart
    const btnRestartTelegramBot = document.getElementById("btn-restart-telegram-bot");
    if (btnRestartTelegramBot) {
        btnRestartTelegramBot.addEventListener("click", async () => {
            btnRestartTelegramBot.disabled = true;
            const originalText = btnRestartTelegramBot.innerHTML;
            btnRestartTelegramBot.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("loading", "Ожидание...")}`;
            
            const res = await apiFetch("/api/system/telegram/restart", { method: "POST" });
            btnRestartTelegramBot.disabled = false;
            btnRestartTelegramBot.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(res.msg || "Telegram-бот успешно перезапущен!");
            } else {
                showToast(res ? res.msg : "Не удалось перезапустить бота", "error");
            }
        });
    }

    // Telegram Bot Token visibility toggle & dynamic fetching
    const btnToggleTelegramToken = document.getElementById("btn-toggle-telegram-token");
    if (btnToggleTelegramToken) {
        btnToggleTelegramToken.addEventListener("click", async () => {
            const tokenInput = document.getElementById("setting-telegram-token");
            if (!tokenInput) return;
            
            const isPassword = tokenInput.type === "password";
            if (isPassword) {
                if (tokenInput.value === "••••••••") {
                    btnToggleTelegramToken.disabled = true;
                    try {
                        const res = await apiFetch("/api/settings/telegram/token");
                        if (res && res.success) {
                            tokenInput.value = res.token || "";
                        }
                    } catch (err) {
                        showToast("Ошибка получения токена: " + err, "error");
                    } finally {
                        btnToggleTelegramToken.disabled = false;
                    }
                }
                tokenInput.type = "text";
                btnToggleTelegramToken.innerHTML = '<i class="fa-regular fa-eye-slash"></i>';
            } else {
                tokenInput.type = "password";
                btnToggleTelegramToken.innerHTML = '<i class="fa-regular fa-eye"></i>';
            }
        });
    }
}
