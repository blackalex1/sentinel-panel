import { apiFetch } from "../api.js";
import { t } from "../i18n.js";
import { showToast, showConfirmDialog } from "../ui.js";

export let auditPage = 1;
export const auditLimit = 10;
export let auditSearch = "";

export function setAuditPage(val) {
    auditPage = val;
}

export function setAuditSearch(val) {
    auditSearch = val;
}

export async function loadAuditLogs() {
    const tbody = document.getElementById("audit-logs-tbody");
    if (!tbody) return;
    
    const res = await apiFetch(`/api/audit-logs?page=${auditPage}&limit=${auditLimit}&search=${encodeURIComponent(auditSearch)}`);
    if (!res || !res.success) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 15px; color: var(--text-secondary);" data-i18n="audit_logs_no_records">Записи не найдены</td></tr>`;
        return;
    }
    
    tbody.innerHTML = "";
    if (res.obj.logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 15px; color: var(--text-secondary);" data-i18n="audit_logs_no_records">Записи не найдены</td></tr>`;
        const totalText = document.getElementById("audit-logs-total-text");
        if (totalText) totalText.innerText = `${t("audit_logs_total_text", "Всего записей")}: 0`;
        return;
    }
    
    res.obj.logs.forEach(log => {
        const date = new Date(log.timestamp * 1000).toLocaleString();
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="white-space: nowrap; color: var(--text-secondary);">${date}</td>
            <td style="white-space: nowrap; font-weight: 500; color: var(--text-primary);">${log.username}</td>
            <td style="white-space: nowrap;"><span class="badge secondary-badge" style="font-size: 12px;">${t("audit_action_" + log.action, log.action)}</span></td>
            <td style="white-space: nowrap; color: var(--accent-blue);">${log.target || "-"}</td>
            <td style="color: var(--text-secondary); font-size: 13px; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${log.details || ''}">${log.details || "-"}</td>
        `;
        tbody.appendChild(tr);
    });
    
    const pageNum = document.getElementById("audit-page-number");
    if (pageNum) pageNum.innerText = res.obj.page;
    
    const totalText = document.getElementById("audit-logs-total-text");
    if (totalText) totalText.innerText = `${t("audit_logs_total_text", "Всего записей")}: ${res.obj.total}`;
    
    const btnPrev = document.getElementById("btn-audit-prev");
    if (btnPrev) btnPrev.disabled = (res.obj.page <= 1);
    
    const btnNext = document.getElementById("btn-audit-next");
    if (btnNext) btnNext.disabled = (res.obj.page * res.obj.limit >= res.obj.total);
}

export function setupAuditLogsListeners() {
    const auditSearchInput = document.getElementById("audit-logs-search");
    if (auditSearchInput) {
        auditSearchInput.addEventListener("input", (e) => {
            setAuditSearch(e.target.value);
            setAuditPage(1);
            loadAuditLogs();
        });
    }

    const auditCategorySelect = document.getElementById("audit-logs-category");
    if (auditCategorySelect) {
        auditCategorySelect.addEventListener("change", (e) => {
            const val = e.target.value;
            setAuditSearch(val);
            if (auditSearchInput) {
                auditSearchInput.value = val;
            }
            setAuditPage(1);
            loadAuditLogs();
        });
    }

    const btnClearConnections = document.getElementById("btn-clear-connections");
    if (btnClearConnections) {
        btnClearConnections.addEventListener("click", async () => {
            const confirmed = await showConfirmDialog(t("confirm_clear_connections", "Вы действительно хотите полностью очистить всю историю подключений? Это удалит все логи входов/выходов из журнала."));
            if (!confirmed) {
                return;
            }
            
            try {
                const res = await apiFetch("/api/security/audit-logs/clear-connections", {
                    method: "POST"
                });
                
                if (res && res.success) {
                    showToast(res.msg || t("connections_cleared_success", "История подключений успешно очищена!"), "success");
                    setAuditPage(1);
                    loadAuditLogs();
                } else {
                    showToast(res ? res.msg : t("connections_clear_failed", "Не удалось очистить историю подключений."), "error");
                }
            } catch (err) {
                showToast(t("connections_clear_error", "Ошибка при очистке истории подключений."), "error");
            }
        });
    }
    
    const btnAuditPrev = document.getElementById("btn-audit-prev");
    if (btnAuditPrev) {
        btnAuditPrev.addEventListener("click", () => {
            if (auditPage > 1) {
                setAuditPage(auditPage - 1);
                loadAuditLogs();
            }
        });
    }
    
    const btnAuditNext = document.getElementById("btn-audit-next");
    if (btnAuditNext) {
        btnAuditNext.addEventListener("click", () => {
            setAuditPage(auditPage + 1);
            loadAuditLogs();
        });
    }
}
