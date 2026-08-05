import { apiFetch } from "../api.js";
import { showToast, formatBytes, showConfirmDialog } from "../ui.js";
import { t } from "../i18n.js";

let currentInbounds = [];

export function renderInboundsList() {
    const container = document.getElementById("inbounds-list");
    if (!container) return;
    container.innerHTML = "";
    
    const sortElem = document.getElementById("inbounds-sort");
    const sortVal = sortElem ? sortElem.value : "id_asc";
    
    const sorted = [...currentInbounds].sort((a, b) => {
        switch (sortVal) {
            case "remark_asc":
                return (a.remark || "").localeCompare(b.remark || "");
            case "remark_desc":
                return (b.remark || "").localeCompare(a.remark || "");
            case "port_asc":
                return (a.port || 0) - (b.port || 0);
            case "port_desc":
                return (b.port || 0) - (a.port || 0);
            case "traffic_desc":
                return ((b.up || 0) + (b.down || 0)) - ((a.up || 0) + (a.down || 0));
            case "protocol_asc":
                return (a.protocol || "").localeCompare(b.protocol || "");
            case "id_asc":
            default:
                return (a.id || 0) - (b.id || 0);
        }
    });
    
    const searchElem = document.getElementById("inbounds-search");
    const term = searchElem ? searchElem.value.toLowerCase().trim() : "";
    
    sorted.forEach(ib => {
        const settings = JSON.parse(ib.settings || "{}");
        const clientsCount = settings.clients ? settings.clients.length : 0;
        
        const card = document.createElement("div");
        card.className = "glass-card inbound-card";
        
        const text = `${ib.remark} ${ib.protocol} ${ib.port} ${ib.core}`.toLowerCase();
        if (term && !text.includes(term)) {
            card.style.display = "none";
        }
        
        const protoLower = (ib.protocol || "").toLowerCase();
        let protoStyle = "background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3);";
        if (protoLower === "vless") {
            protoStyle = "background: rgba(6, 182, 212, 0.15); color: #06b6d4; border: 1px solid rgba(6, 182, 212, 0.3);";
        } else if (protoLower === "vmess") {
            protoStyle = "background: rgba(124, 58, 237, 0.15); color: #a78bfa; border: 1px solid rgba(124, 58, 237, 0.3);";
        } else if (protoLower === "trojan") {
            protoStyle = "background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3);";
        } else if (protoLower === "shadowsocks" || protoLower === "ss") {
            protoStyle = "background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3);";
        } else if (protoLower.includes("hysteria")) {
            protoStyle = "background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);";
        }

        const coreName = ib.core || (protoLower === 'hysteria2' ? 'hysteria' : 'xray');

        card.innerHTML = `
            <div class="inbound-header" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
                <div class="inbound-title-wrap">
                    <h4 style="margin: 0 0 8px 0; font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.3;">${ib.remark}</h4>
                    <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                        <span class="inbound-proto-badge" style="${protoStyle} font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; text-transform: uppercase;">${ib.protocol}</span>
                        <span class="inbound-proto-badge" style="background: rgba(255, 255, 255, 0.05); color: var(--text-secondary); border: 1px solid rgba(255, 255, 255, 0.1); font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 6px;">${coreName}</span>
                    </div>
                </div>
                <label class="switch-toggle">
                    <input type="checkbox" ${ib.enable ? 'checked' : ''} onchange="toggleInbound(${ib.id}, this.checked)">
                    <span class="switch-slider"></span>
                </label>
            </div>
            
            <div class="inbound-details" style="display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; font-size: 13px; background: rgba(255, 255, 255, 0.015); padding: 12px; border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.03);">
                <div class="inbound-detail-row" style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: var(--text-secondary); font-size: 12px; display: flex; align-items: center; gap: 6px;"><i class="fa-solid fa-plug" style="color: var(--accent-cyan); font-size: 11px;"></i> ${t("inbound_port", "Порт")}:</span>
                    <span class="val" style="font-family: monospace; font-size: 13px; font-weight: 700; color: var(--accent-cyan); background: rgba(6, 182, 212, 0.1); padding: 2px 8px; border-radius: 6px; border: 1px solid rgba(6, 182, 212, 0.2);">${ib.port}</span>
                </div>
                <div class="inbound-detail-row" style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: var(--text-secondary); font-size: 12px; display: flex; align-items: center; gap: 6px;"><i class="fa-solid fa-users" style="color: var(--accent-purple); font-size: 11px;"></i> ${t("inbound_users", "Пользователи")}:</span>
                    <span class="val" style="font-weight: 700; color: var(--text-primary); cursor: pointer;" onclick="openClientsModal(${ib.id})">${clientsCount} ${t("inbound_clients_count_label", "клиентов")}</span>
                </div>
                <div class="inbound-detail-row" style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: var(--text-secondary); font-size: 12px; display: flex; align-items: center; gap: 6px;"><i class="fa-solid fa-chart-line" style="color: var(--accent-green); font-size: 11px;"></i> ${t("inbound_traffic", "Расход трафика")}:</span>
                    <span class="val" style="font-size: 12px; font-weight: 600;">
                        <span style="color: var(--accent-purple);"><i class="fa-solid fa-arrow-up" style="font-size: 10px;"></i> ${formatBytes(ib.up)}</span>
                        <span style="color: var(--text-muted); margin: 0 3px;">/</span>
                        <span style="color: var(--accent-green);"><i class="fa-solid fa-arrow-down" style="font-size: 10px;"></i> ${formatBytes(ib.down)}</span>
                    </span>
                </div>
            </div>
            
            <div class="inbound-footer" style="display: flex; gap: 8px; margin-top: auto;">
                <button class="btn secondary-btn" style="flex: 1; padding: 8px 12px; font-size: 12px; border-radius: 8px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 6px;" onclick="openClientsModal(${ib.id})"><i class="fa-solid fa-users"></i> ${t("inbound_btn_clients", "Клиенты")}</button>
                <button class="table-action-btn edit-btn" style="width: 36px; height: 36px; border-radius: 8px; font-size: 13px; display: inline-flex; align-items: center; justify-content: center;" onclick="openEditInboundModal(${ib.id})" title="${t("inbound_btn_edit", "Редактировать")}"><i class="fa-regular fa-pen-to-square"></i></button>
                <button class="table-action-btn delete-btn" style="width: 36px; height: 36px; border-radius: 8px; font-size: 13px; display: inline-flex; align-items: center; justify-content: center;" onclick="deleteInbound(${ib.id})" title="${t("inbound_btn_delete", "Удалить")}"><i class="fa-regular fa-trash-can"></i></button>
            </div>
        `;
        
        container.appendChild(card);
    });
}

export async function loadInbounds() {
    const res = await apiFetch("/panel/api/inbounds/list");
    if (!res || !res.success) return;
    
    currentInbounds = res.obj || [];
    renderInboundsList();
}

export async function toggleInbound(id, state) {
    const listRes = await apiFetch("/panel/api/inbounds/list");
    if (!listRes || !listRes.success) return;
    const target = listRes.obj.find(x => x.id === id);
    if (!target) return;
    
    const res = await apiFetch(`/panel/api/inbounds/update/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            remark: target.remark,
            port: target.port,
            protocol: target.protocol,
            core: target.core || "xray",
            settings: JSON.parse(target.settings),
            streamSettings: JSON.parse(target.streamSettings),
            sniffing: JSON.parse(target.sniffing),
            enable: state ? 1 : 0
        })
    });
    
    if (res && res.success) {
        showToast(state ? t("inbound_enabled", "Подключение включено") : t("inbound_disabled", "Подключение выключено"));
        loadInbounds();
    }
}

export async function deleteInbound(id) {
    const confirmed = await showConfirmDialog(t("confirm_delete_inbound", "Вы уверены, что хотите удалить это подключение? Все связанные клиенты будут также удалены."));
    if (!confirmed) return;
    
    const res = await apiFetch(`/api/inbounds/delete/${id}`, { method: "POST" });
    if (res && res.success) {
        showToast(t("inbound_deleted", "Подключение успешно удалено"));
        loadInbounds();
    }
}
