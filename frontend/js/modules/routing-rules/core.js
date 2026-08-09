import { apiFetch, getCsrfToken } from "../../api.js";
import { showToast, showConfirmDialog } from "../../ui.js";
import { t } from "../../i18n.js";
import { populateOutboundDropdowns } from "../routing-outbounds.js";

export async function loadRoutingRules() {
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
        if (rule.inbound_tags && rule.inbound_tags.length > 0) {
            conditions.push(`<span style="color:var(--accent-orange); font-size:12px; margin-right:4px;">Inbounds:</span>${rule.inbound_tags.join(", ")}`);
        }
        if (rule.users && rule.users.length > 0) {
            conditions.push(`<span style="color:#eccc68; font-size:12px; margin-right:4px;">Users:</span>${rule.users.join(", ")}`);
        }
        if (rule.domains && rule.domains.length > 0) {
            conditions.push(`<span style="color:var(--accent-blue); font-size:12px; margin-right:4px;">Domains:</span>${rule.domains.length} шт.`);
        }
        if (rule.ips && rule.ips.length > 0) {
            conditions.push(`<span style="color:var(--accent-purple); font-size:12px; margin-right:4px;">IPs:</span>${rule.ips.join(", ")}`);
        }
        if (rule.protocols && rule.protocols.length > 0) {
            conditions.push(`<span style="color:#2ed573; font-size:12px; margin-right:4px;">Protos:</span>${rule.protocols.join(", ")}`);
        }
        
        const conditionsHtml = conditions.length > 0 
            ? conditions.map(c => `<div style="margin-bottom: 4px; font-size: 13px;">${c}</div>`).join("") 
            : `<span style="color: var(--text-secondary); font-size:13px;">Any (Всегда)</span>`;
            
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

        tr.setAttribute("draggable", "true");
        tr.setAttribute("data-rule-id", rule.id);
        tr.style.cursor = "grab";

        // Drag and drop event listeners
        tr.addEventListener("dragstart", (e) => {
            const handle = (e.target && e.target.closest) ? e.target.closest(".drag-handle") : null;
            if (!handle) {
                e.preventDefault();
                return false;
            }
            tr.classList.add("dragging");
            e.dataTransfer.setData("text/plain", rule.id);
            e.dataTransfer.effectAllowed = "move";
        });
        tr.addEventListener("dragend", () => {
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
                a.download = `spectre-routing-preset-${new Date().toISOString().slice(0, 10)}.json`;
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
        importBtn.onclick = () => {
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
            } else if (templateVal === "ai_bypass") {
                presetObj = {
                    rules: [
                        {
                            remark: "Route OpenAI & ChatGPT",
                            outbound_tag: "proxy",
                            domains: ["geosite:openai", "domain:chatgpt.com", "domain:oaistatic.com", "domain:oaiusercontent.com"],
                            enable: 1
                        },
                        {
                            remark: "Route Anthropic & Claude",
                            outbound_tag: "proxy",
                            domains: ["domain:claude.ai", "domain:anthropic.com"],
                            enable: 1
                        }
                    ]
                };
            } else if (templateVal === "block_ads_torrent") {
                presetObj = {
                    rules: [
                        {
                            remark: "Block Torrent Traffic",
                            outbound_tag: "blocked",
                            protocols: ["bittorrent"],
                            domains: ["domain:torrent", "domain:tracker", "domain:peerexchange", "keyword:torrent"],
                            enable: 1
                        },
                        {
                            remark: "Block Ad Networks",
                            outbound_tag: "blocked",
                            domains: ["geosite:category-ads-all"],
                            enable: 1
                        }
                    ]
                };
            } else if (templateVal === "split_ru_direct") {
                presetObj = {
                    rules: [
                        {
                            remark: "Route RU Government & Yandex Direct",
                            outbound_tag: "direct",
                            domains: ["geosite:category-gov-ru", "geosite:yandex"],
                            enable: 1
                        }
                    ]
                };
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

    // Load Quick Security Rules settings
    try {
        const setObj = await apiFetch("/api/settings");
        if (setObj && setObj.success) {
            const bittorrentCb = document.getElementById("quick-block-bittorrent");
            if (bittorrentCb) bittorrentCb.checked = Boolean(setObj.block_bittorrent);
            
            const adsCb = document.getElementById("quick-block-ads");
            if (adsCb) adsCb.checked = Boolean(setObj.block_ads);
            
            const cnCb = document.getElementById("quick-block-cn");
            if (cnCb) cnCb.checked = Boolean(setObj.block_cn);
            
            const ruCb = document.getElementById("quick-block-ru");
            if (ruCb) ruCb.checked = Boolean(setObj.block_ru);
            
            const usCb = document.getElementById("quick-block-us");
            if (usCb) usCb.checked = Boolean(setObj.block_us);
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
        inboundSelect.innerHTML = '<option value="">Все подключения (Any)</option>';
        
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
                    opt.innerText = `Hysteria 2 - ${ib.remark} (через Xray)`;
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
                if (clientSelect) clientSelect.innerHTML = '<option value="">Все клиенты (All)</option>';
                return;
            }
            
            const parts = selectedVal.split("-");
            const ibId = parseInt(parts[1]);
            const selectedIb = inbounds.find(x => x.id === ibId);
            
            if (selectedIb && selectedIb.clientStats && selectedIb.clientStats.length > 0) {
                if (clientSelect) {
                    clientSelect.innerHTML = '<option value="">Все клиенты (All)</option>';
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
                if (clientSelect) clientSelect.innerHTML = '<option value="">Все клиенты (All)</option>';
            }
        };
    }
    
    if (id && rulesRes && rulesRes.success) {
        document.getElementById("routing-rule-modal-title").innerText = t("routing_rule_modal_edit", "Редактирование правила маршрутизации");
        const rule = rulesRes.obj.find(x => x.id === id);
        if (rule) {
            const isApiRule = rule.inbound_tags && rule.inbound_tags.includes("api") && rule.outbound_tag === "api";
            if (isApiRule) {
                await populateOutboundDropdowns(true);
            }
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

