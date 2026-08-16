import { apiFetch } from "../../../api.js";
import { formatBytes } from "../../../ui.js";
import { t } from "../../../i18n.js";

export let outboundsCache = [];

export function setOutboundsCache(val) {
    outboundsCache = val;
}

export async function loadOutbounds() {
    const res = await apiFetch("/api/routing/outbounds");
    if (!res || !res.success) return;
    
    outboundsCache = res.obj;
    const tbody = document.getElementById("outbounds-list-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    
    res.obj.forEach(ob => {
        const tr = document.createElement("tr");
        tr.style.borderBottom = "1px solid var(--border-color)";
        
        let settingsText = "";
        let backupBadge = "";
        try {
            const settingsObj = JSON.parse(ob.settings || "{}");
            if (Array.isArray(settingsObj.backup_outbounds) && settingsObj.backup_outbounds.length > 0) {
                backupBadge = `<div style="font-size: 11px; color: var(--accent-green); margin-top: 2px;"><i class="fa-solid fa-shield-halved" style="margin-right: 3px;"></i>${t("routing_backup_badge_label", "Резерв")}: ${settingsObj.backup_outbounds.join(", ")}</div>`;
            }
            if (ob.protocol === "socks" || ob.protocol === "http" || ob.protocol === "shadowsocks") {
                const server = settingsObj.servers ? settingsObj.servers[0] : null;
                if (server) {
                    settingsText = `${server.address}:${server.port}`;
                }
            } else if (ob.protocol === "vless") {
                const server = settingsObj.vnext ? settingsObj.vnext[0] : null;
                if (server) {
                    settingsText = `${server.address}:${server.port}`;
                }
            } else if (ob.protocol === "hysteria" || ob.protocol === "hysteria2") {
                if (settingsObj.address && settingsObj.port) {
                    settingsText = `${settingsObj.address}:${settingsObj.port}`;
                }
            } else {
                settingsText = "-";
            }
        } catch (e) {
            settingsText = "Error";
        }
        
        let badgeClass = "tag-badge";
        const protoLower = ob.protocol.toLowerCase();
        const tagLower = ob.tag.toLowerCase();
        if (protoLower === "freedom" || tagLower === "direct") {
            badgeClass += " tag-badge-direct";
        } else if (protoLower === "blackhole" || tagLower === "blocked") {
            badgeClass += " tag-badge-blocked";
        } else if (tagLower === "warp") {
            badgeClass += " tag-badge-warp";
        } else {
            badgeClass += " tag-badge-proxy";
        }

        const deleteBtn = ob.is_system === 1 
            ? `<button class="table-action-btn delete-btn" disabled><i class="fa-regular fa-trash-can"></i></button>`
            : `<button class="table-action-btn delete-btn" onclick="window.deleteOutbound(${ob.id})" title="${t("routing_btn_delete", "Удалить")}"><i class="fa-regular fa-trash-can"></i></button>`;
            
        const downFormatted = formatBytes(ob.down || 0);
        const upFormatted = formatBytes(ob.up || 0);
        const trafficText = `<span style="color: var(--accent-blue);"><i class="fa-solid fa-arrow-down" style="margin-right: 4px; font-size: 11px;"></i>${downFormatted}</span> <span style="color: var(--text-secondary); margin: 0 4px;">/</span> <span style="color: var(--accent-purple);"><i class="fa-solid fa-arrow-up" style="margin-right: 4px; font-size: 11px;"></i>${upFormatted}</span>`;

        const tcpTestBtn = `<button class="table-action-btn test-btn" onclick="window.testOutbound(${ob.id}, 'tcp', this)" title="${t("routing_btn_tcp_test", "TCP пинг")}"><i class="fa-solid fa-plug"></i></button>`;
        const httpTestBtn = `<button class="table-action-btn test-btn test-btn-http" onclick="window.testOutbound(${ob.id}, 'http', this)" title="${t("routing_btn_http_test", "HTTP тест через прокси")}"><i class="fa-solid fa-globe"></i></button>`;

        tr.innerHTML = `
            <td style="padding: 12px 15px; font-weight: 500;">${ob.remark}</td>
            <td style="padding: 12px 15px;"><span class="${badgeClass}">${ob.protocol}</span></td>
            <td style="padding: 12px 15px; color: var(--accent-blue); font-family: monospace;">${ob.tag}</td>
            <td style="padding: 12px 15px; color: var(--text-secondary);">${settingsText}${backupBadge}</td>
            <td style="padding: 12px 15px; font-size: 13px; white-space: nowrap;">${trafficText}</td>
            <td style="padding: 12px 15px;">
                <label class="switch-toggle">
                    <input type="checkbox" ${ob.enable === 1 ? 'checked' : ''} onchange="window.toggleOutbound(${ob.id}, this.checked)">
                    <span class="switch-slider"></span>
                </label>
            </td>
            <td style="padding: 12px 15px;">
                <div style="display: flex; gap: 8px;">
                    ${tcpTestBtn}
                    ${httpTestBtn}
                    <button class="table-action-btn edit-btn" onclick="window.openOutboundModal(${ob.id})" title="${t("routing_btn_edit", "Редактировать")}"><i class="fa-regular fa-pen-to-square"></i></button>
                    ${deleteBtn}
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
    
    populateOutboundDropdowns();
}

export async function populateOutboundDropdowns(showApi = false, targetVal = null) {
    const select = document.getElementById("rule-outbound");
    if (!select) return;

    const valToSet = targetVal !== null ? targetVal : select.value;

    if (!outboundsCache || outboundsCache.length === 0) {
        const res = await apiFetch("/api/routing/outbounds");
        if (res && res.success) {
            outboundsCache = res.obj;
        }
    }

    select.innerHTML = "";
    
    if (showApi) {
        // Add default system API outbound tag for internal API routing rules
        const optionApi = document.createElement("option");
        optionApi.value = "api";
        optionApi.innerText = "api (Internal API traffic)";
        select.appendChild(optionApi);
    }
    
    (outboundsCache || []).forEach(ob => {
        if (ob.enable === 1) {
            const option = document.createElement("option");
            option.value = ob.tag;
            option.innerText = `${ob.tag} (${ob.protocol} - ${ob.remark})`;
            select.appendChild(option);
        }
    });

    if (valToSet) {
        select.value = valToSet;
    }
}
