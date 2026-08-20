import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadBbrStatus } from "../../dashboard.js";

export async function loadOptimizationStatus() {
    const badge = document.getElementById("optimization-status-badge");
    if (!badge) return;
    
    const res = await apiFetch("/api/system/optimization/status");
    if (res && res.success) {
        if (res.optimized) {
            badge.innerText = t("settings_sys_opt_active");
            badge.className = "badge success-badge";
            badge.style.background = "rgba(46, 213, 115, 0.15)";
            badge.style.color = "#2ed573";
        } else {
            badge.innerText = t("settings_sys_opt_inactive");
            badge.className = "badge warning-badge";
            badge.style.background = "rgba(255, 165, 2, 0.15)";
            badge.style.color = "#ffa502";
        }
    } else {
        badge.innerText = "Error";
        badge.className = "badge danger-badge";
    }
}

export async function loadIpv6Status() {
    const badge = document.getElementById("ipv6-status-badge");
    if (!badge) return;

    const res = await apiFetch("/api/system/ipv6/status");
    if (res && res.success) {
        if (res.ipv6_disabled) {
            badge.innerText = t("settings_ipv6_disabled", "Отключен");
            badge.className = "badge danger-badge";
            badge.style.background = "rgba(244, 63, 94, 0.15)";
            badge.style.color = "#f43f5e";
        } else {
            badge.innerText = t("settings_ipv6_enabled", "Включен");
            badge.className = "badge success-badge";
            badge.style.background = "rgba(46, 213, 115, 0.15)";
            badge.style.color = "#2ed573";
        }
    } else {
        badge.innerText = "Error";
        badge.className = "badge warning-badge";
    }
}

export function setupNetworkListeners() {
    const enableBbrBtn = document.getElementById("enable-bbr-btn");
    if (enableBbrBtn) {
        enableBbrBtn.addEventListener("click", async () => {
            enableBbrBtn.disabled = true;
            enableBbrBtn.innerText = t("dashboard_enabling_bbr");
            const res = await apiFetch("/api/system/bbr/enable", { method: "POST" });
            enableBbrBtn.disabled = false;
            enableBbrBtn.innerText = t("dashboard_enable_bbr");
            if (res && res.success) {
                showToast(t("bbr_enabled"));
                await loadBbrStatus();
            } else {
                showToast(res ? res.msg : t("bbr_enable_error"), "error");
            }
        });
    }

    const btnApplyOptimizations = document.getElementById("btn-apply-optimizations");
    if (btnApplyOptimizations) {
        btnApplyOptimizations.addEventListener("click", async () => {
            btnApplyOptimizations.disabled = true;
            const originalText = btnApplyOptimizations.innerHTML;
            btnApplyOptimizations.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_sys_opt_applying")}`;
            
            const res = await apiFetch("/api/system/optimization/apply", { method: "POST" });
            btnApplyOptimizations.disabled = false;
            btnApplyOptimizations.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_sys_opt_success"));
                loadOptimizationStatus();
            } else {
                showToast(res ? res.msg : t("settings_sys_opt_error"), "error");
            }
        });
    }

    const btnDisableIpv6 = document.getElementById("btn-disable-ipv6");
    if (btnDisableIpv6) {
        btnDisableIpv6.addEventListener("click", async () => {
            btnDisableIpv6.disabled = true;
            const originalHtml = btnDisableIpv6.innerHTML;
            btnDisableIpv6.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_ipv6_disabling", "Отключение...")}`;
            
            const res = await apiFetch("/api/system/ipv6/set", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ disable: true })
            });
            btnDisableIpv6.disabled = false;
            btnDisableIpv6.innerHTML = originalHtml;

            if (res && res.success) {
                showToast(res.msg || t("settings_ipv6_disabled_success", "IPv6 успешно отключен!"));
                await loadIpv6Status();
            } else {
                showToast(res ? res.msg : t("settings_ipv6_error", "Ошибка настройки IPv6"), "error");
            }
        });
    }

    const btnEnableIpv6 = document.getElementById("btn-enable-ipv6");
    if (btnEnableIpv6) {
        btnEnableIpv6.addEventListener("click", async () => {
            btnEnableIpv6.disabled = true;
            const originalHtml = btnEnableIpv6.innerHTML;
            btnEnableIpv6.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_ipv6_enabling", "Включение...")}`;
            
            const res = await apiFetch("/api/system/ipv6/set", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ disable: false })
            });
            btnEnableIpv6.disabled = false;
            btnEnableIpv6.innerHTML = originalHtml;

            if (res && res.success) {
                showToast(res.msg || t("settings_ipv6_enabled_success", "IPv6 успешно включен!"));
                await loadIpv6Status();
            } else {
                showToast(res ? res.msg : t("settings_ipv6_error", "Ошибка настройки IPv6"), "error");
            }
        });
    }
}
