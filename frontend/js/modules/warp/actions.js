import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadWarpStatus } from "./status.js";

export function setupWarpListeners() {
    const btnWarpInstall = document.getElementById("btn-warp-install");
    if (btnWarpInstall) {
        btnWarpInstall.addEventListener("click", async () => {
            btnWarpInstall.disabled = true;
            const originalText = btnWarpInstall.innerHTML;
            btnWarpInstall.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_warp_installing", "Установка...")}`;
            
            const res = await apiFetch("/api/system/warp/install", { method: "POST" });
            btnWarpInstall.disabled = false;
            btnWarpInstall.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_warp_toast_install_success", "Cloudflare WARP успешно установлен!"));
                await loadWarpStatus();
            } else {
                showToast(res ? res.msg : "Не удалось установить WARP", "error");
            }
        });
    }

    const btnWarpConnect = document.getElementById("btn-warp-connect");
    if (btnWarpConnect) {
        btnWarpConnect.addEventListener("click", async () => {
            btnWarpConnect.disabled = true;
            const originalText = btnWarpConnect.innerHTML;
            btnWarpConnect.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_warp_connecting", "Подключение...")}`;
            
            const res = await apiFetch("/api/system/warp/connect", { method: "POST" });
            btnWarpConnect.disabled = false;
            btnWarpConnect.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_warp_toast_connect_success", "WARP успешно подключен!"));
                await loadWarpStatus();
            } else {
                showToast(res ? res.msg : "Не удалось подключить WARP", "error");
            }
        });
    }

    const btnWarpDisconnect = document.getElementById("btn-warp-disconnect");
    if (btnWarpDisconnect) {
        btnWarpDisconnect.addEventListener("click", async () => {
            const rules = window.warpDependentRules || [];
            if (rules.length > 0) {
                const ruleNames = rules.map(r => `• ${r.remark}`).join("\n");
                const warningMsg = t(
                    "settings_warp_warn_disconnect_body",
                    "Внимание! Отключение WARP приведет к временной деактивации следующих правил маршрутизации:\n\n{rules}\n\nДоступ к ресурсам в этих правилах пропадет! Вы уверены, что хотите продолжить?"
                ).replace("{rules}", ruleNames);
                
                if (!confirm(warningMsg)) {
                    return;
                }
            }
            
            btnWarpDisconnect.disabled = true;
            const originalText = btnWarpDisconnect.innerHTML;
            btnWarpDisconnect.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_warp_disconnecting", "Отключение...")}`;
            
            const res = await apiFetch("/api/system/warp/disconnect", { method: "POST" });
            btnWarpDisconnect.disabled = false;
            btnWarpDisconnect.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_warp_toast_disconnect_success", "WARP успешно отключен!"));
                await loadWarpStatus();
            } else {
                showToast(res ? res.msg : "Не удалось отключить WARP", "error");
            }
        });
    }

    const btnWarpUninstall = document.getElementById("btn-warp-uninstall");
    if (btnWarpUninstall) {
        btnWarpUninstall.addEventListener("click", async () => {
            const rules = window.warpDependentRules || [];
            if (rules.length > 0) {
                const ruleNames = rules.map(r => `• ${r.remark}`).join("\n");
                const warningMsg = t(
                    "settings_warp_warn_uninstall_body",
                    "Внимание! Удаление WARP приведет к временной деактивации следующих правил маршрутизации:\n\n{rules}\n\nДоступ к ресурсам в этих правилах пропадет! Вы уверены, что хотите продолжить?"
                ).replace("{rules}", ruleNames);
                
                if (!confirm(warningMsg)) {
                    return;
                }
            }
            
            if (!confirm("Вы действительно хотите полностью удалить Cloudflare WARP с сервера?")) {
                return;
            }
            
            btnWarpUninstall.disabled = true;
            const originalText = btnWarpUninstall.innerHTML;
            btnWarpUninstall.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_warp_uninstalling", "Удаление...")}`;
            
            const res = await apiFetch("/api/system/warp/uninstall", { method: "POST" });
            btnWarpUninstall.disabled = false;
            btnWarpUninstall.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_warp_toast_uninstall_success", "Cloudflare WARP успешно удален!"));
                await loadWarpStatus();
            } else {
                showToast(res ? res.msg : "Не удалось удалить WARP", "error");
            }
        });
    }

    const btnWarpApplyKey = document.getElementById("btn-warp-apply-key");
    if (btnWarpApplyKey) {
        btnWarpApplyKey.addEventListener("click", async () => {
            const licenseInput = document.getElementById("settings-warp-license");
            const key = licenseInput ? licenseInput.value.trim() : "";
            if (!key) {
                showToast("Пожалуйста, введите лицензионный ключ WARP+", "error");
                return;
            }
            
            btnWarpApplyKey.disabled = true;
            const originalText = btnWarpApplyKey.innerHTML;
            btnWarpApplyKey.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_warp_registering", "Регистрация...")}`;
            
            const res = await apiFetch("/api/system/warp/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ license_key: key })
            });
            btnWarpApplyKey.disabled = false;
            btnWarpApplyKey.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_warp_toast_register_success", "Лицензионный ключ успешно применен!"));
                await loadWarpStatus();
            } else {
                showToast(res ? res.msg : "Не удалось применить лицензионный ключ", "error");
            }
        });
    }

    const btnWarpRegisterFree = document.getElementById("btn-warp-register-free");
    if (btnWarpRegisterFree) {
        btnWarpRegisterFree.addEventListener("click", async () => {
            if (!confirm("Вы действительно хотите сбросить аккаунт WARP+ на бесплатный?")) {
                return;
            }
            btnWarpRegisterFree.disabled = true;
            const originalText = btnWarpRegisterFree.innerHTML;
            btnWarpRegisterFree.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_warp_registering", "Сброс...")}`;
            
            const res = await apiFetch("/api/system/warp/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ license_key: "" })
            });
            btnWarpRegisterFree.disabled = false;
            btnWarpRegisterFree.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_warp_toast_register_success", "Регистрация бесплатного аккаунта выполнена!"));
                await loadWarpStatus();
            } else {
                showToast(res ? res.msg : "Не удалось зарегистрировать бесплатный аккаунт", "error");
            }
        });
    }
}
