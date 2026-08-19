import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { compileXraySettings, populateXraySettings } from "./xray.js";
import { compileSingboxSettings, populateSingboxSettings } from "./singbox.js";
import { compileHysteriaSettings, populateHysteriaSettings } from "./hysteria.js";
import { updateFormToggles, updateTabVisibility, handleProtocolChange } from "./toggles.js";
import { validateInboundForm } from "./validation.js";

export let editInboundId = null;
export let originalClients = [];

export function setEditInboundId(val) {
    editInboundId = val;
}

export function setOriginalClients(val) {
    originalClients = val;
}

export function generateRandomPassword(length = 16) {
    const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let password = "";
    for (let i = 0; i < length; i++) {
        password += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return password;
}

export function switchInboundModalTab(tabName) {
    const tabButtons = document.querySelectorAll(".modal-tab-btn");
    const tabPanels = document.querySelectorAll(".tab-panel");
    
    let activeTabButton = document.querySelector(".modal-tab-btn.active");
    let currentTab = activeTabButton ? activeTabButton.getAttribute("data-tab") : "basic";
    
    if (currentTab === "advanced" && tabName !== "advanced") {
        const jsonEditor = document.getElementById("ib-json-editor");
        const rawVal = (jsonEditor.value || "").trim();
        if (rawVal) {
            try {
                const parsed = JSON.parse(rawVal);
                populateFormFromJson(parsed);
            } catch (err) {
                showToast(t("invalid_json_toast", "Неверный формат JSON!") + " " + err.message, "error");
                return false;
            }
        }
    }
    
    if (tabName === "advanced" && currentTab !== "advanced") {
        const payload = serializeFormToJson();
        document.getElementById("ib-json-editor").value = JSON.stringify(payload, null, 2);
    }
    
    tabButtons.forEach(btn => {
        if (btn.getAttribute("data-tab") === tabName) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    
    tabPanels.forEach(panel => {
        if (panel.id === `tab-panel-${tabName}`) {
            panel.style.display = "block";
            panel.classList.add("active-panel");
        } else {
            panel.style.display = "none";
            panel.classList.remove("active-panel");
        }
    });

    try {
        updateFormToggles();
    } catch (e) {
        console.warn("updateFormToggles on tab switch error:", e);
    }
    
    return true;
}

export function serializeFormToJson() {
    const remark = document.getElementById("ib-remark").value;
    const port = parseInt(document.getElementById("ib-port").value) || 0;
    const protocol = document.getElementById("ib-protocol").value;
    const coreElem = document.getElementById("ib-core");
    const core = coreElem ? coreElem.value : "xray";
    
    const totalGB = parseFloat(document.getElementById("ib-total").value) || 0;
    const total = totalGB * 1024 * 1024 * 1024;
    
    const expiryTimeInput = document.getElementById("ib-expiry-time").value;
    let expiryTime = 0;
    if (expiryTimeInput) {
        expiryTime = new Date(expiryTimeInput).getTime();
    }
    
    let settings = { clients: originalClients };
    let streamSettings = {};
    let sniffing = { enabled: false, destOverride: [] };
    
    const sniffingInput = document.getElementById("ib-sniffing");
    const isSniffingEnabled = sniffingInput ? sniffingInput.checked : false;
    if (isSniffingEnabled) {
        const dests = [];
        if (document.getElementById("ib-sniffing-http")?.checked) dests.push("http");
        if (document.getElementById("ib-sniffing-tls")?.checked) dests.push("tls");
        if (document.getElementById("ib-sniffing-quic")?.checked) dests.push("quic");
        if (document.getElementById("ib-sniffing-fakedns")?.checked) dests.push("fakedns");
        
        sniffing = {
            enabled: true,
            destOverride: dests,
            routeOnly: document.getElementById("ib-sniffing-routeonly")?.checked || false
        };
    }
    
    if (protocol === "vless" || protocol === "vmess" || protocol === "trojan") {
        const network = document.getElementById("ib-network").value;
        const security = document.getElementById("ib-security").value;
        
        streamSettings = {
            network: network,
            security: security
        };
        
        if (core === "singbox") {
            compileSingboxSettings(protocol, security, network, streamSettings, settings);
        } else {
            compileXraySettings(protocol, security, network, streamSettings, settings);
        }
    } else if (protocol === "shadowsocks") {
        const method = document.getElementById("ib-ss-method").value;
        settings = {
            method: method,
            clients: originalClients,
            network: "tcp,udp"
        };
    } else if (protocol === "hysteria2") {
        sniffing = { enabled: false, destOverride: [] };
        compileHysteriaSettings(streamSettings, settings, originalClients);
    }
    
    return {
        remark,
        port,
        protocol,
        core,
        settings,
        streamSettings,
        sniffing,
        total,
        expiryTime
    };
}

export function populateFormFromJson(payload) {
    if (!payload || typeof payload !== "object") return;
    
    if (payload.remark !== undefined) {
        document.getElementById("ib-remark").value = payload.remark || "";
    }
    if (payload.port !== undefined) {
        document.getElementById("ib-port").value = payload.port || 0;
    }
    if (payload.protocol !== undefined) {
        const protoSelect = document.getElementById("ib-protocol");
        protoSelect.value = payload.protocol || "vless";
        handleProtocolChange(payload.protocol);
    }
    if (payload.core !== undefined) {
        const coreElem = document.getElementById("ib-core");
        if (coreElem) coreElem.value = payload.core || "xray";
    }
    
    // Total & Expiry Time
    if (payload.total !== undefined) {
        document.getElementById("ib-total").value = payload.total ? (payload.total / (1024 * 1024 * 1024)) : 0;
    }
    if (payload.expiryTime !== undefined) {
        if (payload.expiryTime > 0) {
            const date = new Date(payload.expiryTime);
            const pad = (num) => String(num).padStart(2, '0');
            const formatted = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
            document.getElementById("ib-expiry-time").value = formatted;
        } else {
            document.getElementById("ib-expiry-time").value = "";
        }
    }
    
    const settings = payload.settings || {};
    const streamSettings = payload.streamSettings || {};
    const sniffing = payload.sniffing || {};
    const protocol = payload.protocol || "vless";
    
    const coreVal = payload.core || (protocol === "hysteria2" ? "hysteria" : "xray");

    // Sniffing
    const sniffingChecked = sniffing.enabled || false;
    const sniffingInput = document.getElementById("ib-sniffing");
    if (sniffingInput) sniffingInput.checked = sniffingChecked;
    
    if (document.getElementById("ib-sniffing-http")) document.getElementById("ib-sniffing-http").checked = false;
    if (document.getElementById("ib-sniffing-tls")) document.getElementById("ib-sniffing-tls").checked = false;
    if (document.getElementById("ib-sniffing-quic")) document.getElementById("ib-sniffing-quic").checked = false;
    if (document.getElementById("ib-sniffing-fakedns")) document.getElementById("ib-sniffing-fakedns").checked = false;
    if (document.getElementById("ib-sniffing-routeonly")) document.getElementById("ib-sniffing-routeonly").checked = false;
    
    if (sniffingChecked) {
        const dests = sniffing.destOverride || [];
        if (document.getElementById("ib-sniffing-http")) document.getElementById("ib-sniffing-http").checked = dests.includes("http");
        if (document.getElementById("ib-sniffing-tls")) document.getElementById("ib-sniffing-tls").checked = dests.includes("tls");
        if (document.getElementById("ib-sniffing-quic")) document.getElementById("ib-sniffing-quic").checked = dests.includes("quic");
        if (document.getElementById("ib-sniffing-fakedns")) document.getElementById("ib-sniffing-fakedns").checked = dests.includes("fakedns");
        if (document.getElementById("ib-sniffing-routeonly")) document.getElementById("ib-sniffing-routeonly").checked = sniffing.routeOnly || false;
    }

    if (protocol === "vless" || protocol === "vmess" || protocol === "trojan") {
        if (streamSettings.network !== undefined) {
            document.getElementById("ib-network").value = streamSettings.network || "tcp";
        }
        if (streamSettings.security !== undefined) {
            document.getElementById("ib-security").value = streamSettings.security || "none";
        }
        
        if (coreVal === "singbox") {
            populateSingboxSettings(protocol, streamSettings.security || "none", streamSettings.network || "tcp", streamSettings, settings);
        } else {
            populateXraySettings(protocol, streamSettings.security || "none", streamSettings.network || "tcp", streamSettings, settings);
        }
    } else if (protocol === "shadowsocks") {
        document.getElementById("ib-ss-method").value = settings.method || "aes-256-gcm";
    } else if (protocol === "hysteria2") {
        populateHysteriaSettings(streamSettings);
    }
    
    if (settings.clients) {
        originalClients = settings.clients;
    }
    
    updateFormToggles();
}

export async function handleInboundFormSubmit(e, loadInboundsCallback) {
    e.preventDefault();
    
    const advancedTabActive = document.querySelector(".modal-tab-btn[data-tab='advanced']").classList.contains("active");
    
    let payload;
    if (advancedTabActive) {
        const jsonEditor = document.getElementById("ib-json-editor");
        try {
            payload = JSON.parse(jsonEditor.value);
        } catch (err) {
            showToast(t("invalid_json_toast", "Неверный формат JSON!") + " " + err.message, "error");
            return;
        }
    } else {
        if (!validateInboundForm()) {
            return;
        }
        payload = serializeFormToJson();
    }
    
    // Preserving clients
    if (editInboundId !== null) {
        payload.settings.clients = originalClients;
    }
    
    const { remark, port, protocol, core, settings, streamSettings, sniffing, total, expiryTime } = payload;
    
    let res;
    if (editInboundId !== null) {
        res = await apiFetch(`/panel/api/inbounds/update/${editInboundId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ remark, port, protocol, core, settings, streamSettings, sniffing, enable: 1, total, expiryTime })
        });
    } else {
        res = await apiFetch("/api/inbounds/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ remark, port, protocol, core, settings, streamSettings, sniffing, total, expiryTime })
        });
    }
    
    if (res && res.success) {
        document.getElementById("inbound-modal").classList.remove("active");
        if (editInboundId !== null) {
            showToast(t("inbound_updated_toast", "Подключение успешно обновлено!"));
            editInboundId = null;
        } else {
            showToast(t("inbound_created_toast", "Подключение успешно создано!"));
        }
        loadInboundsCallback();
    } else {
        const errMsg = editInboundId !== null 
            ? (res ? res.msg : t("inbound_update_error_toast", "Ошибка обновления подключения"))
            : (res ? res.msg : t("inbound_create_error_toast", "Ошибка создания подключения"));
        showToast(errMsg, "error");
    }
}

export async function openEditInboundModal(id) {
    const listRes = await apiFetch("/panel/api/inbounds/list");
    if (!listRes || !listRes.success) return;
    const target = listRes.obj.find(x => x.id === id);
    if (!target) return;
    
    editInboundId = id;
    
    document.getElementById("ib-remark").value = target.remark;
    document.getElementById("ib-port").value = target.port;
    
    const protoSelect = document.getElementById("ib-protocol");
    protoSelect.value = target.protocol;
    protoSelect.disabled = true; // Lock protocol editing

    handleProtocolChange(target.protocol);

    const coreSelect = document.getElementById("ib-core");
    if (coreSelect) {
        coreSelect.value = target.core || (target.protocol === "hysteria2" ? "hysteria" : "xray");
    }
    
    document.getElementById("inbound-modal-title").innerText = t("inbound_edit_title", "Редактирование подключения");
    document.querySelector("#inbound-form button[type='submit']").innerText = t("client_btn_save", "Сохранить");
    
    const settings = JSON.parse(target.settings || "{}");
    const streamSettings = JSON.parse(target.streamSettings || "{}");
    const sniffing = JSON.parse(target.sniffing || "{}");
    
    originalClients = settings.clients || [];
    
    // Expiry and total limits
    document.getElementById("ib-total").value = target.total ? (target.total / (1024 * 1024 * 1024)) : 0;
    if (target.expiryTime > 0) {
        const date = new Date(target.expiryTime);
        const pad = (num) => String(num).padStart(2, '0');
        const formatted = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
        document.getElementById("ib-expiry-time").value = formatted;
    } else {
        document.getElementById("ib-expiry-time").value = "";
    }
    
    // Sniffing
    const sniffingChecked = sniffing.enabled || false;
    const sniffingInput = document.getElementById("ib-sniffing");
    if (sniffingInput) sniffingInput.checked = sniffingChecked;
    
    if (document.getElementById("ib-sniffing-http")) document.getElementById("ib-sniffing-http").checked = false;
    if (document.getElementById("ib-sniffing-tls")) document.getElementById("ib-sniffing-tls").checked = false;
    if (document.getElementById("ib-sniffing-quic")) document.getElementById("ib-sniffing-quic").checked = false;
    if (document.getElementById("ib-sniffing-fakedns")) document.getElementById("ib-sniffing-fakedns").checked = false;
    if (document.getElementById("ib-sniffing-routeonly")) document.getElementById("ib-sniffing-routeonly").checked = false;
    
    if (sniffingChecked) {
        const dests = sniffing.destOverride || [];
        if (document.getElementById("ib-sniffing-http")) document.getElementById("ib-sniffing-http").checked = dests.includes("http");
        if (document.getElementById("ib-sniffing-tls")) document.getElementById("ib-sniffing-tls").checked = dests.includes("tls");
        if (document.getElementById("ib-sniffing-quic")) document.getElementById("ib-sniffing-quic").checked = dests.includes("quic");
        if (document.getElementById("ib-sniffing-fakedns")) document.getElementById("ib-sniffing-fakedns").checked = dests.includes("fakedns");
        if (document.getElementById("ib-sniffing-routeonly")) document.getElementById("ib-sniffing-routeonly").checked = sniffing.routeOnly || false;
    }

    if (target.protocol === "vless" || target.protocol === "vmess" || target.protocol === "trojan") {
        const net = streamSettings.network || "tcp";
        const sec = streamSettings.security || "none";
        document.getElementById("ib-network").value = net;
        document.getElementById("ib-security").value = sec;
        
        const inboundCore = target.core || (target.protocol === "hysteria2" ? "hysteria" : "xray");
        if (inboundCore === "singbox") {
            populateSingboxSettings(target.protocol, sec, net, streamSettings, settings);
        } else {
            populateXraySettings(target.protocol, sec, net, streamSettings, settings);
        }
    } else if (target.protocol === "shadowsocks") {
        const ssMethodElem = document.getElementById("ib-ss-method");
        if (ssMethodElem) ssMethodElem.value = settings.method || "aes-256-gcm";
    } else if (target.protocol === "hysteria2") {
        populateHysteriaSettings(streamSettings);
    }
    
    ["ib-protocol", "ib-core", "ib-network", "ib-security", "ib-tcp-type", "ib-reality-fp", "ib-tls-fp", "ib-ss-method", "ib-fallback-xver"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.dispatchEvent(new Event("change", { bubbles: true }));
    });

    updateFormToggles();
    updateTabVisibility(target.protocol);
    switchInboundModalTab("basic");
    document.getElementById("inbound-modal").classList.add("active");
}
