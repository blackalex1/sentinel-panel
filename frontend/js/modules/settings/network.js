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
            badge.innerText = t("settings_sys_opt_active", "Оптимизировано (Тюнинг применен)");
            badge.className = "badge success-badge";
            badge.style.background = "rgba(46, 213, 115, 0.15)";
            badge.style.color = "#2ed573";
        } else {
            badge.innerText = t("settings_sys_opt_inactive", "Не оптимизировано (Стандартные настройки)");
            badge.className = "badge warning-badge";
            badge.style.background = "rgba(255, 165, 2, 0.15)";
            badge.style.color = "#ffa502";
        }
    } else {
        badge.innerText = "Error";
        badge.className = "badge danger-badge";
    }
}

export function setupNetworkListeners() {
    const enableBbrBtn = document.getElementById("enable-bbr-btn");
    if (enableBbrBtn) {
        enableBbrBtn.addEventListener("click", async () => {
            enableBbrBtn.disabled = true;
            enableBbrBtn.innerText = "Включение...";
            const res = await apiFetch("/api/system/bbr/enable", { method: "POST" });
            enableBbrBtn.disabled = false;
            enableBbrBtn.innerText = "Включить";
            if (res && res.success) {
                showToast(t("bbr_enabled", "BBR ускорение успешно включено на хост-системе!"));
                loadBbrStatus();
            } else {
                showToast(res ? res.msg : t("bbr_enable_error", "Не удалось включить BBR"), "error");
            }
        });
    }

    const btnApplyOptimizations = document.getElementById("btn-apply-optimizations");
    if (btnApplyOptimizations) {
        btnApplyOptimizations.addEventListener("click", async () => {
            btnApplyOptimizations.disabled = true;
            const originalText = btnApplyOptimizations.innerHTML;
            btnApplyOptimizations.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("settings_sys_opt_applying", "Применение...")}`;
            
            const res = await apiFetch("/api/system/optimization/apply", { method: "POST" });
            btnApplyOptimizations.disabled = false;
            btnApplyOptimizations.innerHTML = originalText;
            
            if (res && res.success) {
                showToast(t("settings_sys_opt_success", "Системные оптимизации сети успешно применены!"));
                loadOptimizationStatus();
            } else {
                showToast(res ? res.msg : t("settings_sys_opt_error", "Не удалось применить оптимизации"), "error");
            }
        });
    }
}
