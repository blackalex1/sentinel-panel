import { apiFetch } from "../../api.js";
import { formatBytes } from "../../ui.js";
import { t } from "../../i18n.js";
import { openLinksModal, openEditClientModal, deleteClient } from "../../clients.js";

export let dashboardClients = [];
export let lastOnlines = [];

let dashClientsSortCol = "email";
let dashClientsSortDir = "asc";
let isDashHeaderSortInit = false;
let isDashboardSearchInitialized = false;

export async function loadDashboardClients() {
    try {
        const inboundsRes = await apiFetch("/panel/api/inbounds/list");
        const onlinesRes = await apiFetch("/panel/api/clients/onlines", { method: "POST" });
        if (!inboundsRes || !inboundsRes.success || !onlinesRes || !onlinesRes.success) return;

        lastOnlines = onlinesRes.obj || [];
        const tempClients = [];

        inboundsRes.obj.forEach(ib => {
            let settings = {};
            try {
                settings = JSON.parse(ib.settings);
            } catch (e) {
                console.error("Error parsing settings for inbound", ib.id, e);
            }
            const clients = settings.clients || [];
            clients.forEach(c => {
                const stats = ib.clientStats.find(s => s.email === c.email) || { up: 0, down: 0, blockReason: "" };
                const allowedIps = c.allowedIps || c.allowed_ips || stats.allowedIps || stats.allowed_ips || "";
                c.allowedIps = allowedIps;
                tempClients.push({
                    email: c.email,
                    enable: c.enable,
                    limitIp: c.limitIp,
                    allowedIps: allowedIps,
                    totalGB: c.totalGB,
                    expiryTime: c.expiryTime,
                    up: stats.up,
                    down: stats.down,
                    blockReason: stats.blockReason || c.blockReason || "",
                    inboundId: ib.id,
                    inboundRemark: ib.remark,
                    inboundProtocol: ib.protocol,
                    rawClient: c
                });
            });
        });

        // Stable sort alphabetically by email
        tempClients.sort((a, b) => a.email.localeCompare(b.email));
        dashboardClients = tempClients;

        filterAndRenderClients();
        setupDashboardClientsListeners();
    } catch (err) {
        console.error("Error loading dashboard clients:", err);
    }
}

export function filterAndRenderClients() {
    const tableBody = document.getElementById("dashboard-clients-table-body");
    if (!tableBody) return;

    const searchInput = document.getElementById("dashboard-clients-search");
    const onlineFilter = document.getElementById("dashboard-filter-online");
    const blockedFilter = document.getElementById("dashboard-filter-blocked");

    const searchQuery = searchInput ? searchInput.value.toLowerCase().trim() : "";
    const showOnlyOnline = onlineFilter ? onlineFilter.checked : false;
    const showOnlyBlocked = blockedFilter ? blockedFilter.checked : false;

    const onlinesLower = (lastOnlines || []).map(o => String(o).toLowerCase());
    const checkIsOnline = (c) => {
        const email = String(c.email || "");
        const rawId = c.rawClient ? String(c.rawClient.id || "") : "";
        return lastOnlines.includes(email) ||
               (rawId && lastOnlines.includes(rawId)) ||
               onlinesLower.includes(email.toLowerCase()) ||
               (rawId && onlinesLower.includes(rawId.toLowerCase()));
    };

    // Filter
    const filtered = dashboardClients.filter(c => {
        const isOnline = checkIsOnline(c);
        const matchesSearch = c.email.toLowerCase().includes(searchQuery) || 
                              c.inboundRemark.toLowerCase().includes(searchQuery) ||
                              c.inboundProtocol.toLowerCase().includes(searchQuery);

        if (!matchesSearch) return false;
        if (showOnlyOnline && !isOnline) return false;
        if (showOnlyBlocked && c.enable) return false;

        return true;
    });

    // Sort
    filtered.sort((itemA, itemB) => {
        let res = 0;
        switch (dashClientsSortCol) {
            case "status": {
                const getStatusWeight = (item) => {
                    if (!item.enable) return 0;
                    return checkIsOnline(item) ? 2 : 1;
                };
                res = getStatusWeight(itemA) - getStatusWeight(itemB);
                break;
            }
            case "inbound": {
                res = (itemA.inboundRemark || "").localeCompare(itemB.inboundRemark || "");
                break;
            }
            case "used": {
                const usedA = (itemA.up || 0) + (itemA.down || 0);
                const usedB = (itemB.up || 0) + (itemB.down || 0);
                res = usedA - usedB;
                break;
            }
            case "limit": {
                res = (itemA.totalGB || 0) - (itemB.totalGB || 0);
                break;
            }
            case "expiry": {
                res = (itemA.expiryTime || 0) - (itemB.expiryTime || 0);
                break;
            }
            case "email":
            default: {
                res = (itemA.email || "").localeCompare(itemB.email || "");
                break;
            }
        }
        return dashClientsSortDir === "desc" ? -res : res;
    });

    // Update header icons
    const dashHeaders = document.querySelectorAll("th[dash-sort]");
    dashHeaders.forEach(th => {
        const col = th.getAttribute("dash-sort");
        const iconSpan = th.querySelector(".sort-icon");
        if (col === dashClientsSortCol) {
            th.style.color = "var(--accent-cyan, #06b6d4)";
            if (iconSpan) iconSpan.innerText = dashClientsSortDir === "asc" ? "▲" : "▼";
        } else {
            th.style.color = "";
            if (iconSpan) iconSpan.innerText = "↕";
        }
    });

    // Render
    tableBody.innerHTML = "";
    if (filtered.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">
                    ${t("no_matching_clients", "Клиенты не найдены")}
                </td>
            </tr>
        `;
        return;
    }

    filtered.forEach(c => {
        const isOnline = lastOnlines.includes(c.email);
        
        let statusHtml = "";
        if (!c.enable) {
            const reasonStr = c.blockReason || t("client_status_blocked", "Заблокирован");
            statusHtml = `<span class="badge inactive" title="${t("client_block_reason_title", "Причина")}: ${reasonStr}" style="cursor: help;">${t("client_status_blocked", "Бан ⚠️")}</span>`;
        } else if (isOnline) {
            statusHtml = `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); box-shadow: 0 0 10px rgba(16, 185, 129, 0.2);"><span style="display: inline-block; width: 7px; height: 7px; background: #10b981; border-radius: 50%; margin-right: 6px; vertical-align: middle; box-shadow: 0 0 6px #10b981;"></span>${t("client_status_online", "Онлайн")}</span>`;
        } else {
            statusHtml = `<span class="badge" style="background: rgba(255, 255, 255, 0.04); color: var(--text-secondary); border: 1px solid rgba(255, 255, 255, 0.08);"><span style="display: inline-block; width: 6px; height: 6px; background: var(--text-muted); border-radius: 50%; margin-right: 6px; vertical-align: middle; opacity: 0.5;"></span>${t("client_status_offline", "Офлайн")}</span>`;
        }

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

        const emailSafe = c.email.replace(/@/g, '_').replace(/\./g, '_');

        const tr = document.createElement("tr");
        tr.style.cssText = "transition: background 0.2s ease;";
        tr.addEventListener("mouseenter", () => tr.style.background = "rgba(255, 255, 255, 0.03)");
        tr.addEventListener("mouseleave", () => tr.style.background = "transparent");

        tr.innerHTML = `
            <td class="client-email-cell" title="${c.email}"><strong>${c.email}</strong></td>
            <td>${statusHtml}</td>
            <td>
                <a href="#" class="inbound-link" id="db-link-inbound-${c.inboundId}-${emailSafe}" style="color: var(--primary-color, #a855f7); text-decoration: none; font-weight: 500; transition: color 0.2s;">
                    ${c.inboundProtocol.toUpperCase()} (${c.inboundRemark})
                </a>
            </td>
            <td>⬆️ ${formatBytes(c.up)} | ⬇️ ${formatBytes(c.down)}</td>
            <td>${limitText}</td>
            <td>${expiryDate}</td>
            <td>
                <div class="actions-group">
                    <button class="table-action-btn links-btn" id="db-btn-links-${c.inboundId}-${emailSafe}" title="${t("links_modal_title", "Ссылки подключения")}"><i class="fa-solid fa-qrcode"></i></button>
                    <button class="table-action-btn edit-btn" id="db-btn-edit-${c.inboundId}-${emailSafe}" title="${t("inbound_btn_edit", "Редактировать")}"><i class="fa-regular fa-pen-to-square"></i></button>
                    <button class="table-action-btn delete-btn" id="db-btn-del-${c.inboundId}-${emailSafe}" title="${t("inbound_btn_delete", "Удалить")}"><i class="fa-regular fa-trash-can"></i></button>
                </div>
            </td>
        `;

        tableBody.appendChild(tr);

        // Add event listeners to the inline elements
        const inboundLink = document.getElementById(`db-link-inbound-${c.inboundId}-${emailSafe}`);
        if (inboundLink) {
            inboundLink.addEventListener("click", (e) => {
                e.preventDefault();
                if (window.openClientsModal) {
                    window.openClientsModal(c.inboundId);
                }
            });
        }

        const linksBtn = document.getElementById(`db-btn-links-${c.inboundId}-${emailSafe}`);
        if (linksBtn) {
            linksBtn.addEventListener("click", () => openLinksModal(c.inboundId, c.email));
        }

        const editBtn = document.getElementById(`db-btn-edit-${c.inboundId}-${emailSafe}`);
        if (editBtn) {
            editBtn.addEventListener("click", () => openEditClientModal(c.inboundId, c.rawClient));
        }

        const delBtn = document.getElementById(`db-btn-del-${c.inboundId}-${emailSafe}`);
        if (delBtn) {
            delBtn.addEventListener("click", () => deleteClient(
                c.inboundId, 
                c.rawClient.id || c.rawClient.password || c.rawClient.client_uuid_or_pwd, 
                async () => {
                    await loadDashboardClients();
                }
            ));
        }
    });
}

export function setupDashboardClientsListeners() {
    const dashHeaders = document.querySelectorAll("th[dash-sort]");
    if (!isDashHeaderSortInit) {
        dashHeaders.forEach(th => {
            th.addEventListener("click", () => {
                const col = th.getAttribute("dash-sort");
                if (dashClientsSortCol === col) {
                    dashClientsSortDir = dashClientsSortDir === "asc" ? "desc" : "asc";
                } else {
                    dashClientsSortCol = col;
                    dashClientsSortDir = "asc";
                }
                filterAndRenderClients();
            });
        });
        isDashHeaderSortInit = true;
    }

    if (isDashboardSearchInitialized) return;
    
    const searchInput = document.getElementById("dashboard-clients-search");
    const onlineFilter = document.getElementById("dashboard-filter-online");
    const blockedFilter = document.getElementById("dashboard-filter-blocked");
    const refreshBtn = document.getElementById("dashboard-clients-refresh");

    if (searchInput) {
        searchInput.addEventListener("input", () => filterAndRenderClients());
    }
    if (onlineFilter) {
        onlineFilter.addEventListener("change", () => filterAndRenderClients());
    }
    if (blockedFilter) {
        blockedFilter.addEventListener("change", () => filterAndRenderClients());
    }
    if (refreshBtn) {
        refreshBtn.addEventListener("click", async () => {
            const spinIcon = refreshBtn.querySelector("i");
            if (spinIcon) spinIcon.classList.add("fa-spin");
            await loadDashboardClients();
            if (spinIcon) spinIcon.classList.remove("fa-spin");
        });
    }

    isDashboardSearchInitialized = true;
}
