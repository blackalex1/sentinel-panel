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

            // Include DNS settings if present in Quick Rules tab
            const dnsPresetSelect = document.getElementById("setting-dns-preset");
            if (dnsPresetSelect) payload.dns_preset = dnsPresetSelect.value;
            const dnsRemoteInput = document.getElementById("setting-dns-remote");
            if (dnsRemoteInput) payload.dns_remote_server = dnsRemoteInput.value.trim();
            const dnsDirectInput = document.getElementById("setting-dns-direct");
            if (dnsDirectInput) payload.dns_direct_server = dnsDirectInput.value.trim();
            const dnsStrategySelect = document.getElementById("setting-dns-strategy");
            if (dnsStrategySelect) payload.dns_strategy = dnsStrategySelect.value;
            const dnsCustomInput = document.getElementById("setting-dns-custom");
            if (dnsCustomInput) payload.dns_custom_servers = dnsCustomInput.value.trim();
            
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

    // DNS Presets and dedicated save button in Routing -> Quick Rules
    const DNS_PRESET_MAP = {
        "google": { remote: "https://dns.google/dns-query", direct: "https://8.8.8.8/dns-query", custom: "https://dns.google/dns-query, https://8.8.8.8/dns-query, 8.8.8.8" },
        "cloudflare": { remote: "https://1.1.1.1/dns-query", direct: "https://8.8.8.8/dns-query", custom: "https://1.1.1.1/dns-query, https://8.8.8.8/dns-query, 1.1.1.1" },
        "adguard": { remote: "https://dns.adguard-dns.com/dns-query", direct: "https://8.8.8.8/dns-query", custom: "https://dns.adguard-dns.com/dns-query, https://8.8.8.8/dns-query, 94.140.14.14" },
        "yandex": { remote: "https://77.88.8.8/dns-query", direct: "https://77.88.8.8/dns-query", custom: "https://77.88.8.8/dns-query, 77.88.8.8" }
    };

    const dnsPresetSelect = document.getElementById("setting-dns-preset");
    if (dnsPresetSelect) {
        dnsPresetSelect.addEventListener("change", (e) => {
            const val = e.target.value;
            if (DNS_PRESET_MAP[val]) {
                const remoteInp = document.getElementById("setting-dns-remote");
                const directInp = document.getElementById("setting-dns-direct");
                const customInp = document.getElementById("setting-dns-custom");
                if (remoteInp) remoteInp.value = DNS_PRESET_MAP[val].remote;
                if (directInp) directInp.value = DNS_PRESET_MAP[val].direct;
                if (customInp && !customInp.value) customInp.value = DNS_PRESET_MAP[val].custom;
            }
        });
    }

    const btnSaveDns = document.getElementById("btn-save-dns");
    if (btnSaveDns) {
        btnSaveDns.addEventListener("click", async () => {
            const preset = dnsPresetSelect ? dnsPresetSelect.value : "google";
            const remote = (document.getElementById("setting-dns-remote")?.value || "").trim();
            const direct = (document.getElementById("setting-dns-direct")?.value || "").trim();
            const strategy = document.getElementById("setting-dns-strategy")?.value || "ipv4_only";
            const custom = (document.getElementById("setting-dns-custom")?.value || "").trim();

            btnSaveDns.disabled = true;
            const originalHtml = btnSaveDns.innerHTML;
            btnSaveDns.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> ${t("saving", "Сохранение...")}`;

            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    dns_preset: preset,
                    dns_remote_server: remote,
                    dns_direct_server: direct,
                    dns_strategy: strategy,
                    dns_custom_servers: custom
                })
            });

            btnSaveDns.disabled = false;
            btnSaveDns.innerHTML = originalHtml;

            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки DNS успешно сохранены и применены!"));
                loadRoutingRules();
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки DNS"), "error");
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
