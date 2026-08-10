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
            const block_bittorrent = document.getElementById("quick-block-bittorrent").checked;
            const block_bittorrent_outbound = document.getElementById("quick-outbound-bittorrent")?.value || "blocked";
            const block_ads = document.getElementById("quick-block-ads").checked;
            const block_ads_outbound = document.getElementById("quick-outbound-ads")?.value || "blocked";
            const block_cn = document.getElementById("quick-block-cn").checked;
            const block_cn_outbound = document.getElementById("quick-outbound-cn")?.value || "blocked";
            const block_ru = document.getElementById("quick-block-ru").checked;
            const block_ru_outbound = document.getElementById("quick-outbound-ru")?.value || "blocked";
            const block_us = document.getElementById("quick-block-us").checked;
            const block_us_outbound = document.getElementById("quick-outbound-us")?.value || "blocked";
            const ip_checkers = document.getElementById("quick-block-ip-checkers").checked;
            const ip_checkers_outbound = document.getElementById("quick-outbound-ip-checkers")?.value || "direct";
            
            btnSaveQuickRules.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    block_bittorrent,
                    block_bittorrent_outbound,
                    block_ads,
                    block_ads_outbound,
                    block_cn,
                    block_cn_outbound,
                    block_ru,
                    block_ru_outbound,
                    block_us,
                    block_us_outbound,
                    ip_checkers,
                    ip_checkers_outbound
                })
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
            showToast("Конфигурация ядер успешно сброшена к авто-режиму панели!");
            loadRoutingRules();
        });
    }
}
