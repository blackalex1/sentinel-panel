import { apiFetch } from "../../../api.js";
import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { loadHysteriaConfig, renderSelectedHysteriaConfig } from "./render.js";

export function setupHysteriaConfigListeners() {
    const hysteriaTabParsed = document.getElementById("hysteria-config-tab-parsed");
    const hysteriaTabRaw = document.getElementById("hysteria-config-tab-raw");
    const saveBtn = document.getElementById("hysteria-config-save-btn");
    const resetBtn = document.getElementById("hysteria-config-reset-btn");
    if (hysteriaTabParsed && hysteriaTabRaw) {
        hysteriaTabParsed.addEventListener("click", () => {
            hysteriaTabParsed.classList.add("active");
            hysteriaTabRaw.classList.remove("active");
            document.getElementById("hysteria-config-parsed-container").style.display = "block";
            document.getElementById("hysteria-config-raw-container").style.display = "none";
            if (saveBtn) saveBtn.style.display = "none";
            if (resetBtn) resetBtn.style.display = "none";
        });
        
        hysteriaTabRaw.addEventListener("click", () => {
            hysteriaTabRaw.classList.add("active");
            hysteriaTabParsed.classList.remove("active");
            document.getElementById("hysteria-config-raw-container").style.display = "block";
            document.getElementById("hysteria-config-parsed-container").style.display = "none";
            if (saveBtn) saveBtn.style.display = "inline-flex";
            if (resetBtn) resetBtn.style.display = "inline-flex";
        });
    }
    
    if (saveBtn) {
        saveBtn.addEventListener("click", async () => {
            const select = document.getElementById("hysteria-config-inbound-select");
            if (!select || !window.hysteriaConfigs || window.hysteriaConfigs.length === 0) return;
            
            const selectedIdx = parseInt(select.value);
            if (isNaN(selectedIdx) || !window.hysteriaConfigs[selectedIdx]) return;
            
            const inboundId = window.hysteriaConfigs[selectedIdx].inbound_id;
            const rawVal = document.getElementById("hysteria-config-raw-pre").value;
            
            let parsed = null;
            try {
                parsed = JSON.parse(rawVal);
            } catch (err) {
                showToast(t("config_invalid_json", "Некорректный формат JSON"), "error");
                return;
            }
            
            saveBtn.disabled = true;
            const res = await apiFetch("/api/hysteria/config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ inbound_id: inboundId, config: parsed })
            });
            saveBtn.disabled = false;
            
            if (res && res.success) {
                showToast(t("config_saved_success", "Конфигурация успешно сохранена и ядро перезапущено!"));
                await loadHysteriaConfig(selectedIdx);
            } else {
                showToast(res ? res.msg : t("config_save_error", "Ошибка при сохранении конфигурации"), "error");
            }
        });
    }
    
    if (resetBtn) {
        resetBtn.addEventListener("click", async () => {
            const select = document.getElementById("hysteria-config-inbound-select");
            if (!select || !window.hysteriaConfigs || window.hysteriaConfigs.length === 0) return;
            
            const selectedIdx = parseInt(select.value);
            if (isNaN(selectedIdx) || !window.hysteriaConfigs[selectedIdx]) return;
            
            const inboundId = window.hysteriaConfigs[selectedIdx].inbound_id;
            if (!confirm(t("config_confirm_reset", "Вы уверены, что хотите сбросить конфигурацию на автоматическую генерацию из БД?"))) {
                return;
            }
            
            resetBtn.disabled = true;
            const res = await apiFetch("/api/hysteria/config/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ inbound_id: inboundId })
            });
            resetBtn.disabled = false;
            
            if (res && res.success) {
                showToast(t("config_reset_success", "Сброшено на автогенерацию из БД!"));
                await loadHysteriaConfig(selectedIdx);
            } else {
                showToast(res ? res.msg : t("config_reset_error", "Ошибка при сбросе конфигурации"), "error");
            }
        });
    }
    
    // Selector for Hysteria configs
    const hysteriaSelect = document.getElementById("hysteria-config-inbound-select");
    if (hysteriaSelect) {
        hysteriaSelect.addEventListener("change", (e) => {
            const index = parseInt(e.target.value);
            if (!isNaN(index) && window.hysteriaConfigs && window.hysteriaConfigs[index]) {
                const item = window.hysteriaConfigs[index];
                const modeBadge = document.getElementById("hysteria-config-mode-badge");
                if (modeBadge) {
                    const isCustom = item.use_custom === true;
                    if (isCustom) {
                        modeBadge.className = "tag-badge tag-badge-blocked";
                        modeBadge.setAttribute("data-i18n", "config_mode_custom");
                        modeBadge.innerText = t("config_mode_custom", "КАСТОМ");
                    } else {
                        modeBadge.className = "tag-badge tag-badge-direct";
                        modeBadge.setAttribute("data-i18n", "config_mode_auto");
                        modeBadge.innerText = t("config_mode_auto", "АВТО");
                    }
                }
                renderSelectedHysteriaConfig(item.config, item.clients);
            }
        });
    }
}
