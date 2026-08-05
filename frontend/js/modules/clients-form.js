import { apiFetch } from "../api.js";
import { showToast } from "../ui.js";
import { t } from "../i18n.js";
import {
    activeInboundProtocol,
    activeInboundId,
    editModeClientEmail,
    setEditModeEmail,
    openClientsModal
} from "./clients-core.js";

export function openEditClientModal(inboundId, clientData) {
    setEditModeEmail(clientData.email);
    document.getElementById("client-ib-id").value = inboundId;
    document.getElementById("c-email").value = clientData.email;
    document.getElementById("c-email").disabled = false;
    
    document.getElementById("c-uuid").value = clientData.id || clientData.password || clientData.client_uuid_or_pwd || "";
    document.getElementById("c-limit-gb").value = clientData.totalGB || 0;
    
    let daysRemaining = 0;
    if (clientData.expiryTime > 0) {
        const nowSec = Math.floor(Date.now() / 1000);
        const diffSec = clientData.expiryTime - nowSec;
        daysRemaining = Math.max(0, Math.ceil(diffSec / 86400));
    }
    document.getElementById("c-expiry-days").value = daysRemaining;
    document.getElementById("c-limit-ip").value = clientData.limitIp || 0;
    document.getElementById("c-allowed-ips").value = clientData.allowedIps || clientData.allowed_ips || "";
    document.getElementById("c-enable").checked = clientData.enable;
    
    const flowGroup = document.getElementById("client-flow-group");
    const vmessGroup = document.getElementById("client-vmess-group");
    
    flowGroup.style.display = (activeInboundProtocol === "vless") ? "block" : "none";
    vmessGroup.style.display = (activeInboundProtocol === "vmess") ? "block" : "none";
    
    if (flowGroup.style.display === "block") {
        document.getElementById("c-flow").value = clientData.flow || "";
    }
    if (vmessGroup.style.display === "block") {
        document.getElementById("c-alter-id").value = clientData.alterId || 0;
        document.getElementById("c-security").value = clientData.security || "auto";
    }
    
    document.getElementById("client-modal-title").innerText = t("client_edit_title", "Редактирование клиента");
    document.getElementById("client-modal").classList.add("active");
}

export async function handleClientFormSubmit(e, loadInboundsCallback) {
    e.preventDefault();
    const ibId = parseInt(document.getElementById("client-ib-id").value);
    const email = document.getElementById("c-email").value;
    const uuid = document.getElementById("c-uuid").value;
    
    if (!email || !email.trim()) {
        showToast(t("client_err_email_required", "Имя или Email обязательны"), "error");
        return;
    }
    if (!uuid || !uuid.trim()) {
        showToast(t("client_err_uuid_required", "UUID или Пароль обязательны"), "error");
        return;
    }
    const limitGb = parseInt(document.getElementById("c-limit-gb").value) || 0;
    const expiryDays = parseInt(document.getElementById("c-expiry-days").value) || 0;
    const limitIp = parseInt(document.getElementById("c-limit-ip").value) || 0;
    const allowedIps = document.getElementById("c-allowed-ips").value.trim();
    const enable = document.getElementById("c-enable").checked;
    
    const expiryTime = expiryDays > 0 ? Math.floor(Date.now() / 1000) + (expiryDays * 86400) : 0;
    
    // Flow and VMess selection
    const flowSelect = document.getElementById("c-flow");
    const flow = flowSelect ? flowSelect.value : "";
    const alterId = parseInt(document.getElementById("c-alter-id").value) || 0;
    const security = document.getElementById("c-security").value || "auto";
    
    const settingsPayload = {
        clients: [{
            id: uuid,
            email: email,
            enable: enable,
            limitIp: limitIp,
            allowedIps: allowedIps,
            totalGB: limitGb,
            expiryTime: expiryTime,
            ...(activeInboundProtocol === "vless" ? { flow: flow } : {}),
            alterId: alterId,
            security: security
        }]
    };
    
    let url = "/panel/api/inbounds/addClient";
    if (editModeClientEmail) {
        url = `/panel/api/inbounds/updateClient/${editModeClientEmail}`;
    }
    
    const res = await apiFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
            id: ibId,
            settings: JSON.stringify(settingsPayload)
        })
    });
    
    if (res && res.success) {
        document.getElementById("client-modal").classList.remove("active");
        showToast(editModeClientEmail ? t("client_updated_toast", "Клиент успешно обновлен!") : t("client_added_toast", "Клиент успешно добавлен!"));
        openClientsModal(ibId);
        if (loadInboundsCallback) loadInboundsCallback();
    } else {
        showToast(res ? res.msg : t("client_save_error_toast", "Ошибка сохранения клиента"), "error");
    }
}
