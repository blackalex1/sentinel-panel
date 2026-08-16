import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadRoutingRules, openRoutingRuleModal } from "./core.js";

export function setupRoutingRulesListeners() {
    const addRuleBtn = document.getElementById("add-routing-rule-btn");
    if (addRuleBtn) {
        addRuleBtn.addEventListener("click", () => openRoutingRuleModal());
    }

    const ruleForm = document.getElementById("routing-rule-form");
    if (ruleForm) {
        ruleForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const id = document.getElementById("rule-id").value;
            const remark = document.getElementById("rule-remark").value.trim();
            const outbound_tag = document.getElementById("rule-outbound").value;
            
            if (!remark) {
                showToast(t("routing_err_rule_remark", "Укажите название правила"), "warning");
                return;
            }
            if (!outbound_tag) {
                showToast(t("routing_err_rule_outbound", "Выберите назначение правила"), "warning");
                return;
            }
            const enable = document.getElementById("rule-enable").checked ? 1 : 0;
            
            const protocolsInput = document.getElementById("rule-protocols").value.trim();
            const protocols = protocolsInput ? protocolsInput.split(",").map(s => s.trim()).filter(Boolean) : [];
            
            const inboundSelect = document.getElementById("rule-inbound-select");
            const inboundVal = inboundSelect ? inboundSelect.value : "";
            const inbound_tags = inboundVal ? [inboundVal] : [];
            
            const clientSelect = document.getElementById("rule-client-select");
            const clientVal = clientSelect && document.getElementById("rule-client-select-group").style.display !== "none" ? clientSelect.value : "";
            const users = clientVal ? [clientVal] : [];
            
            const domainsInput = document.getElementById("rule-domains").value.trim();
            const domains = domainsInput ? domainsInput.split("\n").map(s => s.trim()).filter(Boolean) : [];
            
            const ipsInput = document.getElementById("rule-ips").value.trim();
            const ips = ipsInput ? ipsInput.split("\n").map(s => s.trim()).filter(Boolean) : [];
            
            if (!inbound_tags.length && !users.length && !domains.length && !ips.length && !protocols.length) {
                showToast(t("routing_err_no_conditions", "Укажите хотя бы одно условие маршрутизации"), "warning");
                return;
            }
            
            const url = id ? `/api/routing/rules/update/${id}` : "/api/routing/rules/create";
            const res = await apiFetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ remark, outbound_tag, inbound_tags, users, domains, ips, protocols, enable })
            });
            
            if (res && res.success) {
                showToast(id ? t("routing_rule_updated", "Правило маршрутизации успешно обновлено") : t("routing_rule_created", "Правило маршрутизации успешно создано"));
                document.getElementById("routing-rule-modal").classList.remove("active");
                loadRoutingRules();
            } else {
                showToast(res ? res.msg : "Error", "error");
            }
        });
    }

    const btnSaveQuickRules = document.getElementById("btn-save-quick-rules");
    if (btnSaveQuickRules) {
        btnSaveQuickRules.addEventListener("click", async () => {
            const payload = {};
            const checkboxes = document.querySelectorAll('#quick-security-rules-grid input[type="checkbox"]');
            
            checkboxes.forEach(cb => {
                const presetId = cb.id.replace("quick-block-", "");
                const settingKey = (presetId === "ip_checkers") ? "ip_checkers" : `block_${presetId}`;
                const outSettingKey = (presetId === "ip_checkers") ? "ip_checkers_outbound" : `block_${presetId}_outbound`;
                
                payload[settingKey] = cb.checked;
                const outSelect = document.getElementById(`quick-outbound-${presetId}`);
                if (outSelect) {
                    payload[outSettingKey] = outSelect.value;
                }
            });
            
            btnSaveQuickRules.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            btnSaveQuickRules.disabled = false;
            
            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
                loadRoutingRules();
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
            }
        });
    }

    const btnResetCustom = document.getElementById("btn-reset-custom-config");
    if (btnResetCustom) {
        btnResetCustom.addEventListener("click", async () => {
            btnResetCustom.disabled = true;
            await Promise.all([
                apiFetch("/api/singbox/config/reset", { method: "POST" }),
                apiFetch("/api/xray/config/reset", { method: "POST" }),
                apiFetch("/api/hysteria/config/reset", { method: "POST" })
            ]);
            btnResetCustom.disabled = false;
            showToast(t("routing_custom_config_reset_success", "Конфигурация ядер успешно сброшена к авто-режиму панели!"));
            loadRoutingRules();
        });
    }
}
