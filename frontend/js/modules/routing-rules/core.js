import { apiFetch, getCsrfToken } from "../../api.js";
import { showToast, showConfirmDialog } from "../../ui.js";
import { t } from "../../i18n.js";
import { populateOutboundDropdowns } from "../routing-outbounds.js";
import { enhanceAllSelects } from "../../components/customSelect.js";

export async function loadRoutingRules() {
    loadQuickSecurityRules();
    const res = await apiFetch("/api/routing/rules");
    if (!res || !res.success) return;
    
    const tbody = document.getElementById("routing-rules-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    
    const rules = res.obj;
    rules.forEach((rule, idx) => {
        const tr = document.createElement("tr");
        tr.style.borderBottom = "1px solid var(--border-color)";
        
        let conditions = [];
        const fmtArr = (arr) => Array.isArray(arr) ? arr.join(", ") : String(arr || "");
        if (rule.inbound_tags && (Array.isArray(rule.inbound_tags) ? rule.inbound_tags.length > 0 : rule.inbound_tags)) {
            conditions.push(`<span style="color:var(--accent-orange); font-size:12px; margin-right:4px;">Inbounds:</span>${fmtArr(rule.inbound_tags)}`);
        }
        if (rule.users && (Array.isArray(rule.users) ? rule.users.length > 0 : rule.users)) {
            conditions.push(`<span style="color:#eccc68; font-size:12px; margin-right:4px;">Users:</span>${fmtArr(rule.users)}`);
        }
        if (rule.domains && (Array.isArray(rule.domains) ? rule.domains.length > 0 : rule.domains)) {
            const dCount = Array.isArray(rule.domains) ? rule.domains.length : 1;
            conditions.push(`<span style="color:var(--accent-blue); font-size:12px; margin-right:4px;">Domains:</span>${dCount} ${t("routing_count_pcs", "шт.")}`);
        }
        if (rule.ips && (Array.isArray(rule.ips) ? rule.ips.length > 0 : rule.ips)) {
            conditions.push(`<span style="color:var(--accent-purple); font-size:12px; margin-right:4px;">IPs:</span>${fmtArr(rule.ips)}`);
        }
        if (rule.protocols && (Array.isArray(rule.protocols) ? rule.protocols.length > 0 : rule.protocols)) {
            conditions.push(`<span style="color:#2ed573; font-size:12px; margin-right:4px;">Protos:</span>${fmtArr(rule.protocols)}`);
        }
        
        const conditionsHtml = conditions.length > 0 
            ? conditions.map(c => `<div style="margin-bottom: 4px; font-size: 13px;">${c}</div>`).join("") 
            : `<span style="color: var(--text-secondary); font-size:13px;">${t("routing_condition_any", "Any (Всегда)")}</span>`;
            
        let badgeClass = "tag-badge";
        const destLower = rule.outbound_tag.toLowerCase();
        if (destLower === "direct") {
            badgeClass += " tag-badge-direct";
        } else if (destLower === "blocked") {
            badgeClass += " tag-badge-blocked";
        } else if (destLower === "warp") {
            badgeClass += " tag-badge-warp";
        } else if (destLower === "api") {
            badgeClass += " tag-badge-api";
        } else {
            badgeClass += " tag-badge-proxy";
        }

        const isFirst = idx === 0;
        const isLast = idx === rules.length - 1;
        const upBtn = `<button class="table-action-btn move-btn" ${isFirst ? 'disabled' : ''} onclick="window.moveRule(${rule.id}, 'up')" title="${t("routing_btn_move_up", "Вверх")}"><i class="fa-solid fa-arrow-up"></i></button>`;
        const downBtn = `<button class="table-action-btn move-btn" ${isLast ? 'disabled' : ''} onclick="window.moveRule(${rule.id}, 'down')" title="${t("routing_btn_move_down", "Вниз")}"><i class="fa-solid fa-arrow-down"></i></button>`;
        
        const deleteBtn = (rule.inbound_tags && rule.inbound_tags.includes("api") && rule.outbound_tag === "api")
            ? `<button class="table-action-btn delete-btn" disabled><i class="fa-regular fa-trash-can"></i></button>`
            : `<button class="table-action-btn delete-btn" onclick="window.deleteRoutingRule(${rule.id})" title="${t("routing_btn_delete", "Удалить")}"><i class="fa-regular fa-trash-can"></i></button>`;

        tr.setAttribute("data-rule-id", rule.id);

        tr.addEventListener("mousedown", (e) => {
            if (e.target && e.target.closest && e.target.closest(".drag-handle")) {
                tr.setAttribute("draggable", "true");
            } else {
                tr.removeAttribute("draggable");
            }
        });

        // Drag and drop event listeners
        tr.addEventListener("dragstart", (e) => {
            tr.classList.add("dragging");
            e.dataTransfer.setData("text/plain", String(rule.id));
            e.dataTransfer.effectAllowed = "move";
        });
        tr.addEventListener("dragend", () => {
            tr.removeAttribute("draggable");
            tr.classList.remove("dragging");
            document.querySelectorAll("#routing-rules-tbody tr").forEach(r => r.classList.remove("drag-over"));
        });
        tr.addEventListener("dragover", (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            tr.classList.add("drag-over");
        });
        tr.addEventListener("dragleave", () => {
            tr.classList.remove("drag-over");
        });
        tr.addEventListener("drop", async (e) => {
            e.preventDefault();
            tr.classList.remove("drag-over");
            const draggedId = e.dataTransfer.getData("text/plain");
            const draggingRow = tbody.querySelector(`tr[data-rule-id="${draggedId}"]`);
            if (draggingRow && draggingRow !== tr) {
                const allRows = Array.from(tbody.children);
                const draggedIdx = allRows.indexOf(draggingRow);
                const targetIdx = allRows.indexOf(tr);
                if (draggedIdx < targetIdx) {
                    tbody.insertBefore(draggingRow, tr.nextSibling);
                } else {
                    tbody.insertBefore(draggingRow, tr);
                }
                // Save new priority order
                const newRuleIds = Array.from(tbody.children).map(r => r.getAttribute("data-rule-id")).filter(Boolean);
                const sortRes = await apiFetch("/api/routing/rules/sort", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ rule_ids: newRuleIds })
                });
                if (sortRes && sortRes.success) {
                    showToast(t("routing_priority_updated", "Порядок правил обновлен"));
                    loadRoutingRules();
                }
            }
        });

        const dragHandle = `<i class="fa-solid fa-grip-lines drag-handle" style="color: var(--text-secondary); cursor: grab; margin-right: 8px;"></i>`;

        tr.innerHTML = `
            <td style="padding: 12px 15px; text-align: center;">${dragHandle}</td>
            <td style="padding: 12px 15px; text-align: center; font-weight: 600; color: var(--text-secondary);">${idx + 1}</td>
            <td style="padding: 12px 15px; font-weight: 500;">${rule.remark || "-"}</td>
            <td style="padding: 12px 15px;">${conditionsHtml}</td>
            <td style="padding: 12px 15px;"><span class="${badgeClass}">${rule.outbound_tag}</span></td>
            <td style="padding: 12px 15px;">
                <label class="switch-toggle">
                    <input type="checkbox" ${rule.enable === 1 ? 'checked' : ''} onchange="window.toggleRoutingRule(${rule.id}, this.checked)">
                    <span class="switch-slider"></span>
                </label>
            </td>
            <td style="padding: 12px 15px;">
                <div style="display: flex; gap: 8px; align-items: center;">
                    ${upBtn}
                    ${downBtn}
                    <button class="table-action-btn edit-btn" onclick="window.openRoutingRuleModal(${rule.id})" title="${t("routing_btn_edit", "Редактировать")}"><i class="fa-regular fa-pen-to-square"></i></button>
                    ${deleteBtn}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });

    // Setup Export / Import preset button handlers
    const exportBtn = document.getElementById("export-routing-preset-btn");
    if (exportBtn) {
        exportBtn.onclick = async () => {
            const res = await apiFetch("/api/routing/rules/export");
            if (res && res.success) {
                const jsonStr = JSON.stringify(res.preset, null, 2);
                const blob = new Blob([jsonStr], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `sentinel-routing-preset-${new Date().toISOString().slice(0, 10)}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast(t("routing_preset_exported", "Пресет правил успешно экспортирован"));
            }
        };
    }

    const importBtn = document.getElementById("import-routing-preset-btn");
    const importModal = document.getElementById("routing-preset-import-modal");
    if (importBtn && importModal) {
        importBtn.onclick = async () => {
            const templateSelect = document.getElementById("preset-template-select");
            const fileGroup = document.getElementById("preset-file-group");

            function updateFileGroupVisibility() {
                if (fileGroup && templateSelect) {
                    fileGroup.style.display = (templateSelect.value === "custom") ? "block" : "none";
                }
            }

            if (templateSelect) {
                try {
                    const presetsRes = await apiFetch("/api/v1/routing/presets");
                    const presets = (presetsRes && presetsRes.success && Array.isArray(presetsRes.obj)) ? presetsRes.obj : [];
                    templateSelect.innerHTML = `<option data-i18n="routing_preset_opt_custom" value="custom">${t("routing_preset_opt_custom", "Загрузить свой JSON файл")}</option>`;
                    presets.forEach(p => {
                        const opt = document.createElement("option");
                        opt.value = p.id;
                        opt.textContent = `${p.name} (${p.description || p.defaultTarget})`;
                        templateSelect.appendChild(opt);
                    });
                } catch (e) {
                    console.warn("Failed to load presets for modal:", e);
                }

                templateSelect.onchange = updateFileGroupVisibility;
                updateFileGroupVisibility();
                enhanceAllSelects(importModal);
            }
            importModal.classList.add("active");
        };
    }

    const importForm = document.getElementById("routing-preset-import-form");
    if (importForm) {
        importForm.onsubmit = async (e) => {
            e.preventDefault();
            const templateVal = document.getElementById("preset-template-select").value;
            const mode = document.getElementById("preset-mode-select").value;

            let presetObj = null;

            if (templateVal === "custom") {
                const fileInput = document.getElementById("preset-json-file");
                if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
                    showToast(t("routing_select_file", "Пожалуйста, выберите JSON файл"), "error");
                    return;
                }
                try {
                    const text = await fileInput.files[0].text();
                    presetObj = JSON.parse(text);
                } catch (err) {
                    showToast(t("routing_invalid_json", "Ошибка парсинга JSON файла"), "error");
                    return;
                }
            } else {
                // Fetch dynamic preset directly from sentinel-core
                const presetDetailsRes = await apiFetch(`/api/v1/routing/presets/${templateVal}`);
                if (presetDetailsRes && presetDetailsRes.success && presetDetailsRes.obj) {
                    presetObj = presetDetailsRes.obj;
                } else {
                    showToast(t("routing_preset_load_error", "Не удалось загрузить пресет из ядра"), "error");
                    return;
                }
            }

            if (!presetObj) return;

            const res = await apiFetch("/api/routing/rules/import", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mode: mode, preset: presetObj })
            });

            if (res && res.success) {
                showToast(res.msg || t("routing_preset_imported", "Пресет успешно импортирован"));
                importModal.classList.remove("active");
                loadRoutingRules();
            } else {
                showToast(res ? res.msg : "Error", "error");
            }
        };
    }
}

export async function loadQuickSecurityRules() {
    // Load Quick Security Rules settings & outbound selections dynamically from sentinel-core presets
    try {
        const [setObj, outboundsRes, presetsRes] = await Promise.all([
            apiFetch("/api/settings"),
            apiFetch("/api/routing/outbounds"),
            apiFetch("/api/v1/routing/presets")
        ]);

        if (setObj && setObj.success) {
            const outbounds = (outboundsRes && outboundsRes.success) ? outboundsRes.obj : [];
            const presets = (presetsRes && presetsRes.success && Array.isArray(presetsRes.obj)) ? presetsRes.obj : [];
            const quickPresets = presets.filter(p => p.type === "quick_rule" || (p.type !== "template" && p.id !== "global_proxy" && p.id !== "direct_all"));
            const gridContainer = document.getElementById("quick-security-rules-grid");

            if (gridContainer) {
                gridContainer.innerHTML = "";

                quickPresets.forEach(p => {
                    const presetId = p.id;
                    const settingKey = (presetId === "ip_checkers") ? "ip_checkers" : `block_${presetId}`;
                    const outSettingKey = (presetId === "ip_checkers") ? "ip_checkers_outbound" : `block_${presetId}_outbound`;
                    
                    const isChecked = Boolean(setObj[settingKey]);
                    const selectedOutbound = setObj[outSettingKey] || (p.defaultTarget === "block" ? "blocked" : (p.defaultTarget || "direct"));

                    const card = document.createElement("div");
                    card.id = `quick-rule-card-${presetId}`;
                    card.style.cssText = "background: var(--bg-input); border: 1px solid var(--border-color); border-radius: 12px; padding: 15px 20px; display: flex; flex-direction: column; gap: 10px;";

                    // Options HTML
                    let optionsHtml = `
                        <option value="blocked" ${selectedOutbound === "blocked" ? "selected" : ""}>BLOCKED</option>
                        <option value="direct" ${selectedOutbound === "direct" ? "selected" : ""}>DIRECT</option>
                    `;
                    outbounds.forEach(ob => {
                        if (ob.tag !== "blocked" && ob.tag !== "direct") {
                            const sel = selectedOutbound === ob.tag ? "selected" : "";
                            const label = ob.remark ? `${ob.remark} (${ob.tag})` : ob.tag;
                            optionsHtml += `<option value="${ob.tag}" ${sel}>${label}</option>`;
                        }
                    });

                    card.innerHTML = `
                        <label for="quick-block-${presetId}" style="display: flex; align-items: center; justify-content: space-between; cursor: pointer; user-select: none; margin: 0;">
                            <div style="display: flex; flex-direction: column; gap: 4px;">
                                <span style="font-weight: 600; font-size: 14px;">${p.name}</span>
                                <span style="font-size: 11px; color: var(--text-secondary);">${p.description || ""}</span>
                            </div>
                            <span class="switch-toggle">
                                <input id="quick-block-${presetId}" type="checkbox" ${isChecked ? "checked" : ""}/>
                                <span class="switch-slider"></span>
                            </span>
                        </label>
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; border-top: 1px dashed var(--border-color); padding-top: 8px;">
                            <span data-i18n="routing_outbound_label" style="font-size: 12px; color: var(--text-secondary);">${t("routing_outbound_label", "Маршрут")}</span>
                            <select class="select-input quick-outbound-select" id="quick-outbound-${presetId}" style="padding: 4px 8px; font-size: 12px; height: 30px; min-width: 130px;">
                                ${optionsHtml}
                            </select>
                        </div>
                    `;
                    gridContainer.appendChild(card);
                });

                // Initialize custom selects on newly created quick rule cards
                enhanceAllSelects(gridContainer);
            }

            // Custom Config Warning Banner
            const banner = document.getElementById("custom-config-warning-banner");
            if (banner) {
                const isCustomSingbox = setObj.use_custom_singbox_config === "true";
                const isCustomXray = setObj.use_custom_xray_config === "true";
                const isCustomHysteria = setObj.use_custom_hysteria_config === "true";

                if (isCustomSingbox || isCustomXray || isCustomHysteria) {
                    banner.style.display = "flex";
                    const cores = [];
                    if (isCustomSingbox) cores.push("Sing-box");
                    if (isCustomXray) cores.push("Xray");
                    if (isCustomHysteria) cores.push("Hysteria 2");
                    const coresText = cores.join(", ");
                    const titleEl = document.getElementById("custom-config-banner-title");
                    const textEl = document.getElementById("custom-config-banner-text");
                    if (titleEl) titleEl.innerText = t("routing_custom_config_banner_title_dynamic", "⚠️ Внимание: Активен ручной (кастомный) конфиг для {cores}!").replace("{cores}", coresText);
                    if (textEl) textEl.innerText = t("routing_custom_config_banner_text_dynamic", "Для {cores} включено ручное редактирование файла. Правила маршрутизации панели не применяются движком.").replace("{cores}", coresText);
                } else {
                    banner.style.display = "none";
                }
            }
        }
    } catch (err) {
        console.error("Failed to load quick security rules:", err);
    }
}

export async function openRoutingRuleModal(id = null) {
    const modal = document.getElementById("routing-rule-modal");
    if (!modal) return;

    const form = document.getElementById("routing-rule-form");
    if (form) form.reset();

    // Show modal immediately so UI response feels instant
    modal.classList.add("active");

    const clientSelectGroup = document.getElementById("rule-client-select-group");
    if (clientSelectGroup) clientSelectGroup.style.display = "none";
    
    // Populate outbound dropdowns asynchronously
    await populateOutboundDropdowns(false);
    
    // Fetch inbounds and rules in parallel if editing
    const [inboundsRes, rulesRes] = await Promise.all([
        apiFetch("/panel/api/inbounds/list"),
        id ? apiFetch("/api/routing/rules") : Promise.resolve(null)
    ]);

    const inbounds = (inboundsRes && inboundsRes.success) ? inboundsRes.obj : [];
    
    const inboundSelect = document.getElementById("rule-inbound-select");
    if (inboundSelect) {
        inboundSelect.innerHTML = `<option value="">${t("routing_rule_modal_all_inbounds", "Все подключения (Any)")}</option>`;
        
        const apiOpt = document.createElement("option");
        apiOpt.value = "api";
        apiOpt.innerText = "api (Internal API traffic)";
        inboundSelect.appendChild(apiOpt);
        
        inbounds.forEach(ib => {
            if (ib.protocol === "hysteria2") {
                const streamSettings = JSON.parse(ib.streamSettings || "{}");
                const hysteria = streamSettings.hysteria || {};
                if (hysteria.routingViaXray) {
                    const opt = document.createElement("option");
                    opt.value = `inbound-${ib.id}-socks`;
                    opt.innerText = `Hysteria 2 - ${ib.remark} (${t("routing_via_xray", "через Xray")})`;
                    inboundSelect.appendChild(opt);
                }
            } else {
                const opt = document.createElement("option");
                opt.value = `inbound-${ib.id}`;
                opt.innerText = `${ib.protocol.toUpperCase()} - ${ib.remark}`;
                inboundSelect.appendChild(opt);
            }
        });
        
        inboundSelect.onchange = function() {
            const selectedVal = inboundSelect.value;
            const clientSelect = document.getElementById("rule-client-select");
            
            if (!selectedVal || selectedVal === "api") {
                if (clientSelectGroup) clientSelectGroup.style.display = "none";
                if (clientSelect) clientSelect.innerHTML = `<option value="">${t("routing_rule_modal_all_clients", "Все клиенты (All)")}</option>`;
                return;
            }
            
            const parts = selectedVal.split("-");
            const ibId = parseInt(parts[1]);
            const selectedIb = inbounds.find(x => x.id === ibId);
            
            if (selectedIb && selectedIb.clientStats && selectedIb.clientStats.length > 0) {
                if (clientSelect) {
                    clientSelect.innerHTML = `<option value="">${t("routing_rule_modal_all_clients", "Все клиенты (All)")}</option>`;
                    selectedIb.clientStats.forEach(c => {
                        const opt = document.createElement("option");
                        opt.value = c.email;
                        opt.innerText = c.email;
                        clientSelect.appendChild(opt);
                    });
                }
                if (clientSelectGroup) clientSelectGroup.style.display = "block";
            } else {
                if (clientSelectGroup) clientSelectGroup.style.display = "none";
                if (clientSelect) clientSelect.innerHTML = `<option value="">${t("routing_rule_modal_all_clients", "Все клиенты (All)")}</option>`;
            }
        };
    }
    
    if (id && rulesRes && rulesRes.success) {
        document.getElementById("routing-rule-modal-title").innerText = t("routing_rule_modal_edit", "Редактирование правила маршрутизации");
        const rule = rulesRes.obj.find(x => String(x.id) === String(id));
        if (rule) {
            const isApiRule = rule.inbound_tags && rule.inbound_tags.includes("api") && rule.outbound_tag === "api";
            await populateOutboundDropdowns(isApiRule, rule.outbound_tag);
            document.getElementById("rule-id").value = rule.id;
            document.getElementById("rule-remark").value = rule.remark || "";
            document.getElementById("rule-outbound").value = rule.outbound_tag;
            document.getElementById("rule-protocols").value = rule.protocols ? rule.protocols.join(", ") : "";
            
            const inboundTag = rule.inbound_tags && rule.inbound_tags.length > 0 ? rule.inbound_tags[0] : "";
            if (inboundSelect) {
                inboundSelect.value = inboundTag;
                if (typeof inboundSelect.onchange === "function") {
                    inboundSelect.onchange();
                }
            }
            
            const clientSelect = document.getElementById("rule-client-select");
            const ruleUser = rule.users && rule.users.length > 0 ? rule.users[0] : "";
            if (clientSelect && ruleUser) {
                clientSelect.value = ruleUser;
            }
            
            document.getElementById("rule-domains").value = rule.domains ? rule.domains.join("\n") : "";
            document.getElementById("rule-ips").value = rule.ips ? rule.ips.join("\n") : "";
            document.getElementById("rule-enable").checked = rule.enable === 1;
        }
    } else if (!id) {
        document.getElementById("routing-rule-modal-title").innerText = t("routing_rule_modal_create", "Создание правила маршрутизации");
        document.getElementById("rule-id").value = "";
        document.getElementById("rule-enable").checked = true;
    }
}

export async function toggleRoutingRule(id, checked) {
    const listRes = await apiFetch("/api/routing/rules");
    if (!listRes || !listRes.success) return;
    const rule = listRes.obj.find(x => x.id === id);
    if (!rule) return;
    
    const res = await apiFetch(`/api/routing/rules/update/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            remark: rule.remark,
            outbound_tag: rule.outbound_tag,
            inbound_tags: rule.inbound_tags,
            users: rule.users || [],
            domains: rule.domains,
            ips: rule.ips,
            protocols: rule.protocols,
            enable: checked ? 1 : 0,
            sort_order: rule.sort_order
        })
    });
    
    if (res && res.success) {
        showToast(checked ? t("routing_rule_enabled", "Правило маршрутизации включено") : t("routing_rule_disabled", "Правило маршрутизации выключено"));
        loadRoutingRules();
    }
}

export async function deleteRoutingRule(id) {
    const confirmed = await showConfirmDialog(t("routing_confirm_delete_rule", "Вы уверены, что хотите удалить это правило маршрутизации?"));
    if (!confirmed) return;
    
    const res = await apiFetch(`/api/routing/rules/delete/${id}`, { method: "POST" });
    if (res && res.success) {
        showToast(t("routing_rule_deleted", "Правило успешно удалено"));
        loadRoutingRules();
    } else {
        showToast(res ? res.msg : "Error", "error");
    }
}

window.openRoutingRuleModal = openRoutingRuleModal;
window.toggleRoutingRule = toggleRoutingRule;
window.deleteRoutingRule = deleteRoutingRule;

