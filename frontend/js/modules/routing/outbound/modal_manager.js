import { apiFetch } from "../../../api.js";
import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { renderDynamicOutboundForm } from "../../inbounds/schema-renderer.js";
import { outboundsCache, loadOutbounds } from "./table_render.js";
import { enhanceAllSelects } from "../../../components/customSelect.js";

let cachedSchema = null;
let currentOutboundValues = {};

export async function fetchOutboundSchema() {
    if (cachedSchema && cachedSchema.outboundProtocols) {
        return cachedSchema;
    }
    try {
        const res = await apiFetch("/api/schema/capabilities");
        if (res && res.success && res.obj) {
            cachedSchema = res.obj;
            return cachedSchema;
        }
    } catch (e) {
        console.warn("Failed to fetch schema from core:", e);
    }
    return null;
}

export async function openOutboundModal(id = null) {
    const modal = document.getElementById("outbound-modal");
    if (!modal) return;

    const form = document.getElementById("outbound-form");
    if (form) form.reset();

    const titleEl = document.getElementById("outbound-modal-title");
    if (titleEl) {
        titleEl.innerText = id ? t("routing_modal_edit_outbound", "Редактирование исходящего подключения") : t("routing_modal_create_outbound", "Создание исходящего подключения");
    }

    const idInput = document.getElementById("ob-id");
    if (idInput) idInput.value = id || "";

    const linkInput = document.getElementById("ob-import-link");
    if (linkInput) linkInput.value = "";

    const schema = await fetchOutboundSchema();
    const outboundProtocols = (schema && schema.outboundProtocols) ? schema.outboundProtocols : {};

    // 1. Populate Protocol Select Options Dynamically from Core Schema
    const protocolSelect = document.getElementById("ob-protocol");
    if (protocolSelect) {
        protocolSelect.innerHTML = "";
        const protoKeys = ["vless", "hysteria2", "trojan", "shadowsocks", "vmess", "wireguard", "socks", "http", "warp", "freedom", "blackhole"];
        
        protoKeys.forEach(pk => {
            const cap = outboundProtocols[pk];
            const opt = document.createElement("option");
            opt.value = pk;
            opt.textContent = cap ? cap.displayName : pk.toUpperCase();
            protocolSelect.appendChild(opt);
        });

        // Add any extra protocols present in schema
        Object.keys(outboundProtocols).forEach(pk => {
            if (!protoKeys.includes(pk) && pk !== "direct" && pk !== "block" && pk !== "ss" && pk !== "socks5") {
                const cap = outboundProtocols[pk];
                const opt = document.createElement("option");
                opt.value = pk;
                opt.textContent = cap ? cap.displayName : pk.toUpperCase();
                protocolSelect.appendChild(opt);
            }
        });
    }

    // 2. Prepare Current Values
    currentOutboundValues = {};

    if (id) {
        // Load existing outbound
        const listRes = await apiFetch("/api/routing/outbounds");
        const allObs = (listRes && listRes.success) ? listRes.obj : outboundsCache;
        const ob = (allObs || []).find(x => String(x.id) === String(id));
        if (ob) {
            let settingsObj = {};
            let streamObj = {};
            try { settingsObj = JSON.parse(ob.settings || "{}"); } catch(e) {}
            try { streamObj = JSON.parse(ob.stream_settings || "{}"); } catch(e) {}

            let proto = (ob.protocol || "vless").toLowerCase();
            if (proto === "direct") proto = "freedom";
            if (proto === "block") proto = "blackhole";

            currentOutboundValues = {
                remark: ob.remark || "",
                tag: ob.tag || "",
                protocol: proto,
                enable: ob.enable !== 0,
                fallback_outbound: settingsObj.fallback_outbound || (settingsObj.backup_outbounds && settingsObj.backup_outbounds[0]) || "",
                fallback_strategy: settingsObj.fallback_strategy || "priority",
                health_check_interval: settingsObj.health_check_interval || 300,
                ...settingsObj,
                ...streamObj
            };

            // Extract direct settings fields with aliases
            currentOutboundValues.host = settingsObj.host || settingsObj.address || settingsObj.server || currentOutboundValues.host || "";
            currentOutboundValues.port = settingsObj.port || settingsObj.server_port || settingsObj.port_hopping || settingsObj.hop || currentOutboundValues.port || 443;
            currentOutboundValues.password = settingsObj.password || settingsObj.auth || settingsObj.auth_str || settingsObj.auth_password || currentOutboundValues.password || "";
            currentOutboundValues.uuid = settingsObj.uuid || settingsObj.id || currentOutboundValues.uuid || currentOutboundValues.password;
            currentOutboundValues.upMbps = settingsObj.upMbps || settingsObj.up_mbps || currentOutboundValues.upMbps || 100;
            currentOutboundValues.downMbps = settingsObj.downMbps || settingsObj.down_mbps || currentOutboundValues.downMbps || 100;
            currentOutboundValues.obfs = settingsObj.obfs_type || (settingsObj.obfs && typeof settingsObj.obfs === "object" ? settingsObj.obfs.type : settingsObj.obfs) || currentOutboundValues.obfs || "";
            currentOutboundValues.obfsPassword = settingsObj.obfs_password || (settingsObj.obfs && settingsObj.obfs.salamander && settingsObj.obfs.salamander.password) || (settingsObj.obfs && settingsObj.obfs.password) || settingsObj.obfsPassword || "";
            currentOutboundValues.sni = settingsObj.sni || settingsObj.server_name || currentOutboundValues.sni || "";
            currentOutboundValues.pinnedPeerCertSha256 = settingsObj.pinnedPeerCertSha256 || settingsObj.pin_sha256 || currentOutboundValues.pinnedPeerCertSha256 || "";
            currentOutboundValues.allowInsecure = (settingsObj.allowInsecure === true || settingsObj.insecure === true || currentOutboundValues.allowInsecure === true);

            // Extract nested structures if present
            if (settingsObj.vnext && settingsObj.vnext[0]) {
                const vn = settingsObj.vnext[0];
                currentOutboundValues.host = vn.address || currentOutboundValues.host;
                currentOutboundValues.port = vn.port || currentOutboundValues.port;
                if (vn.users && vn.users[0]) {
                    currentOutboundValues.uuid = vn.users[0].id || vn.users[0].uuid || currentOutboundValues.uuid;
                    currentOutboundValues.flow = vn.users[0].flow || currentOutboundValues.flow;
                    currentOutboundValues.encryption = vn.users[0].encryption || currentOutboundValues.encryption;
                }
            }

            if (settingsObj.servers && settingsObj.servers[0]) {
                const srv = settingsObj.servers[0];
                currentOutboundValues.host = srv.address || srv.server || currentOutboundValues.host;
                currentOutboundValues.port = srv.port || srv.server_port || currentOutboundValues.port;
                currentOutboundValues.password = srv.password || srv.auth || currentOutboundValues.password;
                currentOutboundValues.method = srv.method || currentOutboundValues.method;
                currentOutboundValues.user = srv.user || currentOutboundValues.user;
                currentOutboundValues.pass = srv.pass || currentOutboundValues.pass;
            }

            if (streamObj.hysteriaSettings) {
                if (streamObj.hysteriaSettings.hop) currentOutboundValues.port = streamObj.hysteriaSettings.hop;
                if (streamObj.hysteriaSettings.auth) currentOutboundValues.password = streamObj.hysteriaSettings.auth;
                if (streamObj.hysteriaSettings.upMbps) currentOutboundValues.upMbps = streamObj.hysteriaSettings.upMbps;
                if (streamObj.hysteriaSettings.downMbps) currentOutboundValues.downMbps = streamObj.hysteriaSettings.downMbps;
                if (streamObj.hysteriaSettings.obfs) currentOutboundValues.obfs = streamObj.hysteriaSettings.obfs;
                if (streamObj.hysteriaSettings.obfsPassword) currentOutboundValues.obfsPassword = streamObj.hysteriaSettings.obfsPassword;
            }

            if (streamObj.realitySettings) {
                currentOutboundValues.security = "reality";
                currentOutboundValues.publicKey = streamObj.realitySettings.publicKey || currentOutboundValues.publicKey;
                currentOutboundValues.shortId = streamObj.realitySettings.shortId || currentOutboundValues.shortId;
                currentOutboundValues.spiderX = streamObj.realitySettings.spiderX || currentOutboundValues.spiderX;
                currentOutboundValues.fingerprint = streamObj.realitySettings.fingerprint || currentOutboundValues.fingerprint;
                currentOutboundValues.sni = streamObj.realitySettings.serverName || currentOutboundValues.sni;
            } else if (streamObj.tlsSettings) {
                currentOutboundValues.security = "tls";
                currentOutboundValues.sni = streamObj.tlsSettings.serverName || currentOutboundValues.sni;
                currentOutboundValues.fingerprint = streamObj.tlsSettings.fingerprint || currentOutboundValues.fingerprint;
                currentOutboundValues.allowInsecure = streamObj.tlsSettings.allowInsecure === true;
                if (streamObj.tlsSettings.pinnedPeerCertSha256) currentOutboundValues.pinnedPeerCertSha256 = streamObj.tlsSettings.pinnedPeerCertSha256;
                if (streamObj.tlsSettings.alpn) {
                    currentOutboundValues.alpn = Array.isArray(streamObj.tlsSettings.alpn) ? streamObj.tlsSettings.alpn.join(",") : streamObj.tlsSettings.alpn;
                }
            }

            if (streamObj.wsSettings) {
                currentOutboundValues.network = "ws";
                currentOutboundValues.path = streamObj.wsSettings.path || currentOutboundValues.path;
                if (streamObj.wsSettings.headers) {
                    currentOutboundValues.wsHost = streamObj.wsSettings.headers.Host || currentOutboundValues.wsHost;
                }
            } else if (streamObj.grpcSettings) {
                currentOutboundValues.network = "grpc";
                currentOutboundValues.serviceName = streamObj.grpcSettings.serviceName || currentOutboundValues.serviceName;
            }

            if (protocolSelect) {
                protocolSelect.value = proto;
                if (ob.is_system === 1) {
                    protocolSelect.disabled = true;
                } else {
                    protocolSelect.disabled = false;
                }
            }
        }
    } else {
        // New Outbound Defaults
        const activeProto = protocolSelect ? protocolSelect.value || "vless" : "vless";
        currentOutboundValues = {
            remark: "VLESS Reality",
            tag: `out-${Math.random().toString(36).substring(2, 7)}`,
            protocol: activeProto,
            host: "",
            port: 443,
            security: "reality",
            network: "tcp",
            fingerprint: "chrome",
            allowInsecure: false,
            enable: true
        };
        if (protocolSelect) {
            protocolSelect.disabled = false;
            protocolSelect.value = activeProto;
        }
    }

    // 3. Render Form via Dynamic Schema Engine
    function renderCurrentProtocolForm() {
        const proto = protocolSelect ? protocolSelect.value : (currentOutboundValues.protocol || "vless");
        const cap = outboundProtocols[proto] || outboundProtocols["vless"] || { tabDefinitions: [] };
        
        const tabsContainer = document.getElementById("outbound-modal-tabs");
        const schemaContainer = document.getElementById("outbound-schema-container");

        renderDynamicOutboundForm(schemaContainer, tabsContainer, cap.tabDefinitions || [], currentOutboundValues, (updatedValues) => {
            currentOutboundValues = updatedValues;
        });

        // Populate fallback routes dropdown options dynamically
        populateFallbackDropdown(currentOutboundValues);
    }

    if (protocolSelect) {
        protocolSelect.onchange = () => {
            currentOutboundValues.protocol = protocolSelect.value;
            renderCurrentProtocolForm();
        };
    }

    renderCurrentProtocolForm();
    enhanceAllSelects(modal);

    modal.classList.add("active");
}

export async function populateFallbackDropdown(customOutboundValues = null) {
    const fallbackSelect = document.getElementById("fallback_outbound") || document.getElementById("ob-fallback-outbound");
    if (!fallbackSelect) return;

    const values = customOutboundValues || currentOutboundValues || {};
    const listRes = await apiFetch("/api/routing/outbounds");
    const allObs = (listRes && listRes.success) ? listRes.obj : outboundsCache;
    const currentTag = values.tag;
    
    fallbackSelect.innerHTML = `<option value="">${t("routing_opt_no_fallback", "Без резервного маршрута")}</option>`;
    (allObs || []).forEach(o => {
        if (o.tag && o.tag !== "api" && o.tag !== currentTag) {
            const opt = document.createElement("option");
            opt.value = o.tag;
            opt.textContent = `${o.remark || o.tag} (${o.tag})`;
            if (values.fallback_outbound === o.tag) {
                opt.selected = true;
            }
            fallbackSelect.appendChild(opt);
        }
    });
    enhanceAllSelects(fallbackSelect.parentElement);
}

export function getCurrentOutboundValues() {
    return currentOutboundValues;
}

export function setCurrentOutboundValues(newValues) {
    currentOutboundValues = { ...currentOutboundValues, ...newValues };
}

export function updateBackupBadges() {
    // Backward compatibility helper
}

