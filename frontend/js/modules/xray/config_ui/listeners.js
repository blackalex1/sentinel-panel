import { apiFetch } from "../../../api.js";
import { showToast, showConfirmDialog } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { loadXrayConfig } from "./render.js";

export function setupXrayConfigListeners() {
    const xrayTabParsed = document.getElementById("xray-config-tab-parsed");
    const xrayTabRaw = document.getElementById("xray-config-tab-raw");
    const xraySaveBtn = document.getElementById("xray-config-save-btn");
    const xrayResetBtn = document.getElementById("xray-config-reset-btn");
    if (xrayTabParsed && xrayTabRaw) {
        xrayTabParsed.addEventListener("click", () => {
            xrayTabParsed.classList.add("active");
            xrayTabRaw.classList.remove("active");
            document.getElementById("xray-config-parsed-container").style.display = "block";
            document.getElementById("xray-config-raw-container").style.display = "none";
            if (xraySaveBtn) xraySaveBtn.style.display = "none";
            if (xrayResetBtn) xrayResetBtn.style.display = "none";
        });
        
        xrayTabRaw.addEventListener("click", () => {
            xrayTabRaw.classList.add("active");
            xrayTabParsed.classList.remove("active");
            document.getElementById("xray-config-raw-container").style.display = "block";
            document.getElementById("xray-config-parsed-container").style.display = "none";
            if (xraySaveBtn) xraySaveBtn.style.display = "inline-flex";
            if (xrayResetBtn) xrayResetBtn.style.display = "inline-flex";
        });
    }
    
    if (xraySaveBtn) {
        xraySaveBtn.addEventListener("click", async () => {
            const rawVal = document.getElementById("xray-config-raw-pre").value;
            let parsed = null;
            try {
                parsed = JSON.parse(rawVal);
            } catch (err) {
                showToast(t("config_invalid_json", "Некорректный формат JSON"), "error");
                return;
            }
            
            xraySaveBtn.disabled = true;
            const res = await apiFetch("/api/xray/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ config: parsed, is_custom: true })
            });
            xraySaveBtn.disabled = false;
            
            if (res && res.success) {
                showToast(t("config_saved_success", "Конфигурация успешно сохранена и ядро перезапущено!"));
                loadXrayConfig();
            } else {
                showToast(res ? res.msg : t("config_save_error", "Ошибка при сохранении конфигурации"), "error");
            }
        });
    }
    
    if (xrayResetBtn) {
        xrayResetBtn.addEventListener("click", async () => {
            const confirmed = await showConfirmDialog(t("config_confirm_reset", "Вы уверены, что хотите сбросить конфигурацию на автоматическую генерацию из БД?"));
            if (!confirmed) {
                return;
            }
            xrayResetBtn.disabled = true;
            const res = await apiFetch("/api/xray/config/reset", { method: "POST" });
            xrayResetBtn.disabled = false;
            
            if (res && res.success) {
                showToast(t("config_reset_success", "Сброшено на автогенерацию из БД!"));
                loadXrayConfig();
            } else {
                showToast(res ? res.msg : t("config_reset_error", "Ошибка при сбросе конфигурации"), "error");
            }
        });
    }
}
