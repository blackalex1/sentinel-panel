import { apiFetch } from "../../api.js";
import { formatBytes, loadComponent } from "../../ui.js";
import { t } from "../../i18n.js";

export async function openGlobalTrafficDetailsModal(selectedDate) {
    let modal = document.getElementById("global-traffic-details-modal");
    if (!modal) {
        await loadComponent("global-traffic-modal", "components/global-traffic-modal.html", "body");
        modal = document.getElementById("global-traffic-details-modal");
    }
    if (!modal) return;

    const dateStr = (typeof selectedDate === "string" && selectedDate.trim()) ? selectedDate.trim() : new Date().toISOString().split("T")[0];
    const dateEl = document.getElementById("gt-modal-date");
    if (dateEl) dateEl.innerText = dateStr;
    modal.style.display = "flex";
    modal.classList.add("active");

    const closeModal = () => {
        modal.style.display = "none";
        modal.classList.remove("active");
    };

    const closeBtn = document.getElementById("gt-modal-close-btn");
    if (closeBtn && !closeBtn._hasClick) {
        closeBtn._hasClick = true;
        closeBtn.onclick = closeModal;
        modal.onclick = (e) => { if (e.target === modal) closeModal(); };
    }

    const tableBody = document.getElementById("gt-modal-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 20px; color: var(--text-muted);">${t("gt_modal_loading", "Загрузка данных...")}</td></tr>`;

    const res = await apiFetch(`/panel/api/system/global-traffic-details?date=${dateStr}`);
    if (!res || !res.success) {
        tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 20px; color: var(--accent-rose);">${t("gt_modal_load_error", "Ошибка загрузки данных")}</td></tr>`;
        return;
    }

    const totalBytesEl = document.getElementById("gt-modal-total-bytes");
    if (totalBytesEl) totalBytesEl.innerText = formatBytes(res.total_bytes);
    
    const downBytesEl = document.getElementById("gt-modal-down-bytes");
    if (downBytesEl) downBytesEl.innerText = formatBytes(res.total_down);

    const upBytesEl = document.getElementById("gt-modal-up-bytes");
    if (upBytesEl) upBytesEl.innerText = formatBytes(res.total_up);

    const countEl = document.getElementById("gt-modal-client-count");
    if (countEl) countEl.innerText = res.clients.length;

    const renderRows = (filter = "") => {
        const query = filter.toLowerCase().trim();
        const filtered = res.clients.filter(c => c.email.toLowerCase().includes(query));

        if (filtered.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 20px; color: var(--text-muted);">${t("gt_modal_no_data", "Нет данных по клиентам за эту дату")}</td></tr>`;
            return;
        }

        tableBody.innerHTML = filtered.map(c => {
            const barWidth = c.percent > 0 ? Math.max(c.percent, 3) : 0;
            const proto = (c.protocol || "vless").toUpperCase();
            const core = (c.core || "singbox").toUpperCase();
            const coreBadgeClass = (core.includes("XRAY")) ? "tag-badge-warp" : (core.includes("HYSTERIA")) ? "tag-badge-blocked" : "tag-badge-proxy";
            return `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03); transition: background 0.2s;" onmouseenter="this.style.background='rgba(255,255,255,0.03)'" onmouseleave="this.style.background='transparent'">
                <td style="padding: 10px 14px; font-weight: 600; color: var(--text-primary);">${c.email}</td>
                <td style="padding: 10px 14px; text-align: center; white-space: nowrap;">
                    <span class="tag-badge tag-badge-direct" style="font-size: 10.5px; padding: 2px 7px; text-transform: uppercase; font-weight: 700;">${proto}</span>
                    <span class="tag-badge ${coreBadgeClass}" style="font-size: 10.5px; padding: 2px 7px; text-transform: uppercase; font-weight: 700; margin-left: 4px;">${core}</span>
                </td>
                <td style="padding: 10px 14px; text-align: right; color: var(--accent-green); font-weight: 600;">⬇️ ${formatBytes(c.down)}</td>
                <td style="padding: 10px 14px; text-align: right; color: var(--accent-purple); font-weight: 600;">⬆️ ${formatBytes(c.up)}</td>
                <td style="padding: 10px 14px; text-align: right; font-weight: 700; color: var(--text-primary);">${formatBytes(c.total)}</td>
                <td style="padding: 10px 14px; text-align: right;">
                    <div style="display: flex; align-items: center; justify-content: flex-end; gap: 8px;">
                        <div style="flex: 1; height: 8px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.05); border-radius: 4px; overflow: hidden; max-width: 85px; position: relative;">
                            <div style="width: ${barWidth}%; height: 100%; background: linear-gradient(90deg, #00f0ff, #a855f7); border-radius: 4px; box-shadow: 0 0 6px rgba(0, 240, 255, 0.4); transition: width 0.3s ease;"></div>
                        </div>
                        <span style="font-size: 11px; font-weight: 700; color: var(--accent-cyan); min-width: 48px; text-align: right;">${c.percent}%</span>
                    </div>
                </td>
            </tr>
            `;
        }).join("");
    };

    renderRows();

    const searchInput = document.getElementById("gt-modal-search");
    if (searchInput) {
        searchInput.value = "";
        searchInput.oninput = (e) => renderRows(e.target.value);
    }
}
