import { apiFetch } from "../api.js";
import { showToast, formatBytes, showConfirmDialog } from "../ui.js";
import { t } from "../i18n.js";
import { showClientTrafficChart } from "./clients-chart.js";
import { openEditClientModal } from "./clients-form.js";

export let activeInboundId = null;
export let activeInboundProtocol = "";
export let editModeClientEmail = null;
export let loadInboundsCallbackGlobal = null;

export function setEditModeEmail(email) {
    editModeClientEmail = email;
}

export function setLoadInboundsCallback(cb) {
    loadInboundsCallbackGlobal = cb;
}

export function setActiveInboundProtocol(proto) {
    activeInboundProtocol = proto;
}

export function setActiveInboundId(id) {
    activeInboundId = id;
}

let currentClientsSortCol = "email";
let currentClientsSortDir = "asc";
let currentModalInboundId = null;
let currentModalClientsData = [];
let isClientsHeaderSortInit = false;

function renderClientsModalTable() {
    const tableBody = document.getElementById("clients-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = "";
    const inboundId = currentModalInboundId;
    
    // Sort
    const sorted = [...currentModalClientsData].sort((itemA, itemB) => {
        const cA = itemA.c;
        const cB = itemB.c;
        const statsA = itemA.stats;
        const statsB = itemB.stats;
        let res = 0;
        
        switch (currentClientsSortCol) {
            case "status": {
                const getStatusWeight = (item) => {
                    if (!item.c.enable) return 0;
                    return item.isOnline ? 2 : 1;
                };
                res = getStatusWeight(itemA) - getStatusWeight(itemB);
                break;
            }
            case "used": {
                const usedA = (statsA.up || 0) + (statsA.down || 0);
                const usedB = (statsB.up || 0) + (statsB.down || 0);
                res = usedA - usedB;
                break;
            }
            case "limit": {
                res = (cA.totalGB || 0) - (cB.totalGB || 0);
                break;
            }
            case "expiry": {
                res = (cA.expiryTime || 0) - (cB.expiryTime || 0);
                break;
            }
            case "email":
            default: {
                res = (cA.email || "").localeCompare(cB.email || "");
                break;
            }
        }
        
        return currentClientsSortDir === "desc" ? -res : res;
    });
    
    // Update headers UI
    const modalHeaders = document.querySelectorAll("#clients-modal th[data-sort]");
    modalHeaders.forEach(th => {
        const col = th.getAttribute("data-sort");
        const iconSpan = th.querySelector(".sort-icon");
        if (col === currentClientsSortCol) {
            th.style.color = "var(--accent-cyan, #00f0ff)";
            if (iconSpan) iconSpan.innerText = currentClientsSortDir === "asc" ? "▲" : "▼";
        } else {
            th.style.color = "";
            if (iconSpan) iconSpan.innerText = "↕";
        }
    });
    
    if (!isClientsHeaderSortInit) {
        modalHeaders.forEach(th => {
            th.addEventListener("click", () => {
                const col = th.getAttribute("data-sort");
                if (currentClientsSortCol === col) {
                    currentClientsSortDir = currentClientsSortDir === "asc" ? "desc" : "asc";
                } else {
                    currentClientsSortCol = col;
                    currentClientsSortDir = "asc";
                }
                renderClientsModalTable();
            });
        });
        isClientsHeaderSortInit = true;
    }
    
    sorted.forEach(({ c, stats, isOnline }) => {
        let statusHtml = "";
        if (!c.enable) {
            const reasonStr = stats.blockReason || c.blockReason || t("client_status_blocked", "Заблокирован");
            statusHtml = `<span class="badge inactive" title="${t("client_block_reason_title", "Причина")}: ${reasonStr}" style="cursor: help;">${t("client_status_blocked", "Бан ⚠️")}</span>`;
        } else if (isOnline) {
            statusHtml = `<span class="badge" style="background: rgba(46, 213, 115, 0.15); color: #2ed573; box-shadow: 0 0 8px rgba(46, 213, 115, 0.2);"><span style="display: inline-block; width: 6px; height: 6px; background: #2ed573; border-radius: 50%; margin-right: 6px; vertical-align: middle;"></span>${t("client_status_online", "Онлайн")}</span>`;
        } else {
            statusHtml = `<span class="badge" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary);"><span style="display: inline-block; width: 6px; height: 6px; background: var(--text-muted); border-radius: 50%; margin-right: 6px; vertical-align: middle; opacity: 0.5;"></span>${t("client_status_offline", "Офлайн")}</span>`;
        }
        
        let statusCol = `
            <div style="display: flex; flex-direction: column; gap: 4px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <label class="switch-toggle mini-switch" style="transform: scale(0.8); transform-origin: left center; width: 46px; height: 24px; margin-bottom: 0;">
                        <input type="checkbox" id="toggle-client-${inboundId}-${c.email.replace(/@/g, '_')}" ${c.enable ? 'checked' : ''}>
                        <span class="switch-slider"></span>
                    </label>
                    ${statusHtml}
                </div>
        `;
        const blockReason = stats.blockReason || c.blockReason;
        if (!c.enable && blockReason) {
            statusCol += `<span style="font-size: 11px; color: var(--accent-rose); opacity: 0.9; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${blockReason}">${blockReason}</span>`;
        }
        statusCol += `</div>`;
            
        const trafficLimit = c.totalGB > 0 ? `${c.totalGB} GB` : t("client_status_unlimited", "Безлимит");
        const ipLimit = c.limitIp > 0 ? `IP: ${c.limitIp}` : "IP: ♾️";
        const limitText = `
            <div style="display: flex; flex-direction: column; font-size: 13px; gap: 2px;">
                <span>📊 ${trafficLimit}</span>
                <span style="color: var(--text-secondary);">🖥️ ${ipLimit}</span>
            </div>
        `;
        
        const expiryDate = c.expiryTime > 0 
            ? new Date(c.expiryTime * 1000).toLocaleDateString() 
            : t("client_status_never_expires", "Бессрочно");
            
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="client-email-cell" title="${c.email}"><strong>${c.email}</strong></td>
            <td>${statusCol}</td>
            <td>⬆️ ${formatBytes(stats.up)} | ⬇️ ${formatBytes(stats.down)}</td>
            <td>${limitText}</td>
            <td>${expiryDate}</td>
            <td>
                <div class="actions-group">
                    <button class="table-action-btn chart-btn" id="btn-chart-${inboundId}-${c.email.replace(/@/g, '_')}" title="${t("clients_traffic_chart_btn", "График")}"><i class="fa-solid fa-chart-line"></i></button>
                    <button class="table-action-btn reset-btn" id="btn-reset-${inboundId}-${c.email.replace(/@/g, '_')}" title="${t("clients_reset_traffic_btn", "Сбросить трафик")}"><i class="fa-solid fa-rotate-right"></i></button>
                    <button class="table-action-btn links-btn" id="btn-links-${inboundId}-${c.email.replace(/@/g, '_')}" title="${t("links_modal_title", "Ссылки подключения")}"><i class="fa-solid fa-qrcode"></i></button>
                    <button class="table-action-btn edit-btn" id="btn-edit-${inboundId}-${c.email.replace(/@/g, '_')}" title="${t("inbound_btn_edit", "Редактировать")}"><i class="fa-regular fa-pen-to-square"></i></button>
                    <button class="table-action-btn delete-btn" id="btn-del-${inboundId}-${c.email.replace(/@/g, '_')}" title="${t("inbound_btn_delete", "Удалить")}"><i class="fa-regular fa-trash-can"></i></button>
                </div>
            </td>
        `;
        tableBody.appendChild(tr);
        
        // Register event listeners
        document.getElementById(`btn-chart-${inboundId}-${c.email.replace(/@/g, '_')}`).addEventListener("click", () => showClientTrafficChart(c.email));
        document.getElementById(`btn-reset-${inboundId}-${c.email.replace(/@/g, '_')}`).addEventListener("click", () => resetClientTraffic(inboundId, c.email));
        document.getElementById(`btn-links-${inboundId}-${c.email.replace(/@/g, '_')}`).addEventListener("click", () => openLinksModal(inboundId, c.email));
        document.getElementById(`btn-edit-${inboundId}-${c.email.replace(/@/g, '_')}`).addEventListener("click", () => openEditClientModal(inboundId, c));
        document.getElementById(`btn-del-${inboundId}-${c.email.replace(/@/g, '_')}`).addEventListener("click", () => deleteClient(inboundId, c.id || c.password || c.client_uuid_or_pwd, loadInboundsCallbackGlobal));
        
        document.getElementById(`toggle-client-${inboundId}-${c.email.replace(/@/g, '_')}`).addEventListener("change", (e) => {
            toggleClientActiveStatus(inboundId, c, e.target.checked);
        });
    });
}

export async function openClientsModal(inboundId) {
    activeInboundId = inboundId;
    currentModalInboundId = inboundId;
    editModeClientEmail = null; // Reset edit mode on modal open
    
    const chartContainer = document.getElementById("client-traffic-chart-container");
    if (chartContainer) chartContainer.style.display = "none";
    
    const inboundsRes = await apiFetch("/panel/api/inbounds/list");
    if (!inboundsRes || !inboundsRes.success) return;
    
    const ib = inboundsRes.obj.find(x => x.id === inboundId);
    if (!ib) return;
    
    activeInboundProtocol = ib.protocol;
    document.getElementById("clients-modal-ib-remark").innerText = ib.remark;
    
    // Query online clients
    const onlinesRes = await apiFetch("/panel/api/clients/onlines", { method: "POST" });
    const onlines = (onlinesRes ? onlinesRes.obj : []) || [];
    const onlinesLower = onlines.map(o => String(o).toLowerCase());
    
    // Parse settings and clients stats
    const settings = JSON.parse(ib.settings);
    const clients = settings.clients || [];
    
    currentModalClientsData = clients.map(c => {
        const stats = ib.clientStats.find(s => s.email === c.email) || { up: 0, down: 0, total: 0, enable: true, limitIp: 0, blockReason: "" };
        const isOnline = onlines.includes(c.email) ||
                         (c.id && onlines.includes(c.id)) ||
                         onlinesLower.includes(String(c.email).toLowerCase()) ||
                         (c.id && onlinesLower.includes(String(c.id).toLowerCase()));
        c.allowedIps = c.allowedIps || c.allowed_ips || stats.allowedIps || stats.allowed_ips || "";
        return { c, stats, isOnline };
    });
    
    renderClientsModalTable();

    const resetAllBtn = document.getElementById("reset-all-clients-btn");
    if (resetAllBtn) {
        resetAllBtn.onclick = () => resetAllClientsTrafficForInbound(inboundId);
    }
    
    document.getElementById("clients-modal").classList.add("active");
}

export async function resetClientTraffic(inboundId, email) {
    const confirmMsg = t("confirm_reset_client_traffic_msg", "Вы уверены, что хотите сбросить трафик для клиента {email}?").replace("{email}", email);
    const confirmed = await showConfirmDialog(
        confirmMsg,
        t("confirm_reset_client_traffic_title", "Сброс трафика"),
        t("btn_reset", "Сбросить"),
        t("btn_cancel", "Отмена")
    );
    if (!confirmed) return;

    try {
        const res = await apiFetch(`/panel/api/inbounds/resetClientTraffic/${inboundId}/${encodeURIComponent(email)}`, {
            method: "POST"
        });
        if (res && res.success) {
            showToast(t("traffic_reset_success", "Трафик успешно сброшен!"));
            if (currentModalInboundId) {
                await openClientsModal(currentModalInboundId);
            }
            if (loadInboundsCallbackGlobal) {
                await loadInboundsCallbackGlobal();
            }
        } else {
            showToast(res ? res.msg : t("generic_error", "Ошибка сброса трафика"), "error");
        }
    } catch (e) {
        showToast(e.message, "error");
    }
}

export async function resetAllClientsTrafficForInbound(inboundId) {
    const confirmed = await showConfirmDialog(
        t("confirm_reset_all_clients_traffic_msg", "Вы уверены, что хотите сбросить трафик для всех клиентов этого подключения?"),
        t("confirm_reset_all_clients_traffic_title", "Сброс трафика всех клиентов"),
        t("btn_reset", "Сбросить"),
        t("btn_cancel", "Отмена")
    );
    if (!confirmed) return;

    try {
        const res = await apiFetch(`/panel/api/inbounds/resetAllClientTraffics/${inboundId}`, {
            method: "POST"
        });
        if (res && res.success) {
            showToast(t("traffic_reset_success", "Трафик успешно сброшен!"));
            if (currentModalInboundId) {
                await openClientsModal(currentModalInboundId);
            }
            if (loadInboundsCallbackGlobal) {
                await loadInboundsCallbackGlobal();
            }
        } else {
            showToast(res ? res.msg : t("generic_error", "Ошибка сброса трафика"), "error");
        }
    } catch (e) {
        showToast(e.message, "error");
    }
}

export async function toggleClientActiveStatus(inboundId, clientData, enabled) {
    const email = clientData.email;
    
    const settingsPayload = {
        clients: [{
            id: clientData.id || clientData.password || clientData.client_uuid_or_pwd,
            email: email,
            enable: enabled,
            limitIp: clientData.limitIp || 0,
            totalGB: clientData.totalGB || 0,
            expiryTime: clientData.expiryTime || 0,
            flow: clientData.flow || "",
            alterId: clientData.alterId || 0,
            security: clientData.security || "auto"
        }]
    };
    
    const res = await apiFetch(`/panel/api/inbounds/updateClient/${email}`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
            id: inboundId,
            settings: JSON.stringify(settingsPayload)
        })
    });
    
    if (res && res.success) {
        showToast(enabled ? t("client_unblocked_toast", "Клиент успешно разблокирован!") : t("client_blocked_toast", "Клиент успешно заблокирован!"));
        const clientsModal = document.getElementById("clients-modal");
        if (clientsModal && clientsModal.classList.contains("active")) {
            openClientsModal(inboundId);
        }
        if (loadInboundsCallbackGlobal) loadInboundsCallbackGlobal();
    } else {
        showToast(res ? res.msg : t("client_status_error_toast", "Не удалось изменить статус клиента"), "error");
        const clientsModal = document.getElementById("clients-modal");
        if (clientsModal && clientsModal.classList.contains("active")) {
            openClientsModal(inboundId); // Reload to reset switch
        }
    }
}

export async function deleteClient(inboundId, clientId, loadInboundsCallback) {
    const confirmed = await showConfirmDialog(t("confirm_delete_client", "Вы уверены, что хотите удалить этого клиента?"));
    if (!confirmed) return;
    
    const res = await apiFetch(`/panel/api/inbounds/${inboundId}/delClient/${clientId}`, { method: "POST" });
    if (res && res.success) {
        showToast(t("client_deleted_toast", "Клиент успешно удален"));
        const clientsModal = document.getElementById("clients-modal");
        if (clientsModal && clientsModal.classList.contains("active")) {
            openClientsModal(inboundId);
        }
        if (loadInboundsCallback) loadInboundsCallback();
    }
}

export async function openLinksModal(inboundId, email) {
    const res = await apiFetch(`/panel/api/inbounds/getClientLinks/${inboundId}/${email}`);
    if (!res || !res.success || !res.obj.length) {
        showToast(t("links_generation_error_toast", "Ошибка генерации ссылок"), "error");
        return;
    }
    
    const link = res.obj[0];
    document.getElementById("import-link-input").value = link;

    const mihomoContainer = document.getElementById("mihomo-container");
    const mihomoInput = document.getElementById("mihomo-link-input");
    if (mihomoContainer && mihomoInput) {
        if (res.mihomo) {
            mihomoInput.value = res.mihomo;
            mihomoContainer.style.display = "block";
        } else {
            mihomoInput.value = "";
            mihomoContainer.style.display = "none";
        }
    }
    


    // Render QR-code
    const qrContainer = document.getElementById("qrcode-container");
    if (qrContainer && window.QRCode) {
        qrContainer.innerHTML = "";
        
        new window.QRCode(qrContainer, {
            text: link,
            width: 200,
            height: 200,
            colorDark : "#020617",
            colorLight : "#ffffff",
            correctLevel : window.QRCode.CorrectLevel.L
        });
    }
    
    document.getElementById("links-modal").classList.add("active");
}

