import { apiFetch } from "../../../api.js";
import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { renderDynamicOutboundForm, isSupportedByEngine } from "../../inbounds/schema-renderer.js";
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
    const engineSelect = document.getElementById("ob-engine");
    const protocolSelect = document.getElementById("ob-protocol");

    // 1a. Populate Target Engine Selector dynamically from schema.engines
    if (engineSelect) {
        const prevEng = engineSelect.value || "";
        engineSelect.innerHTML = `<option value="">${t("routing_opt_engine_auto", "Auto (Все доступные опции)")}</option>`;
        (schema && Array.isArray(schema.engines) ? schema.engines : []).forEach(eng => {
            const opt = document.createElement("option");
            opt.value = eng.id;
            opt.textContent = eng.name || eng.id;
            engineSelect.appendChild(opt);
        });
        engineSelect.value = prevEng;
    }

    // 1b. Populate Protocol Select Options Dynamically from Core Schema (filtered by engine if chosen)
    function populateProtocolSelect(activeEngine = "") {
        if (!protocolSelect) return;
        const prevProto = protocolSelect.value || currentOutboundValues.protocol || "vless";
        protocolSelect.innerHTML = "";
        const protoKeys = ["vless", "hysteria2", "trojan", "shadowsocks", "vmess", "tuic", "shadowtls", "wireguard", "socks", "http", "warp", "freedom", "blackhole"];

        const addOptionIfSupported = (pk) => {
            const cap = outboundProtocols[pk];
            if (activeEngine && cap && !isSupportedByEngine(cap.supportedEngines, activeEngine)) {
                return;
            }
            const opt = document.createElement("option");
            opt.value = pk;
            opt.textContent = cap ? cap.displayName : pk.toUpperCase();
            protocolSelect.appendChild(opt);
        };

        protoKeys.forEach(addOptionIfSupported);
        Object.keys(outboundProtocols).forEach(pk => {
            if (!protoKeys.includes(pk) && pk !== "direct" && pk !== "block" && pk !== "ss" && pk !== "socks5" && pk !== "wg") {
                addOptionIfSupported(pk);
            }
        });

        const allowedVals = Array.from(protocolSelect.options).map(o => o.value);
        if (allowedVals.includes(prevProto)) {
            protocolSelect.value = prevProto;
        } else if (allowedVals.length > 0) {
            protocolSelect.value = allowedVals[0];
            currentOutboundValues.protocol = allowedVals[0];
        }
    }

    populateProtocolSelect(engineSelect ? engineSelect.value : "");

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
                health_check_interval: settingsObj.health_check_interval || 30,
                ...settingsObj,
                ...streamObj
            };

            // Extract direct settings fields with aliases
            currentOutboundValues.host = settingsObj.host || settingsObj.address || settingsObj.server || currentOutboundValues.host || "";
            currentOutboundValues.port = settingsObj.port || settingsObj.server_port || settingsObj.port_hopping || settingsObj.hop || currentOutboundValues.port || 443;
            currentOutboundValues.portHopping = settingsObj.port_hopping || settingsObj.portHopping || settingsObj.hop || settingsObj.ports || currentOutboundValues.portHopping || "";
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
                if (streamObj.hysteriaSettings.hop) {
                    currentOutboundValues.portHopping = streamObj.hysteriaSettings.hop;
                    if (!settingsObj.port && !settingsObj.server_port) {
                        currentOutboundValues.port = streamObj.hysteriaSettings.hop;
                    }
                }
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

            if (streamObj.tcpSettings) {
                currentOutboundValues.network = currentOutboundValues.network || "tcp";
                const hdr = streamObj.tcpSettings.header;
                if (hdr && hdr.type) {
                    currentOutboundValues.headerType = hdr.type === "none" ? "" : hdr.type;
                }
                if (hdr && hdr.request) {
                    if (Array.isArray(hdr.request.path) && hdr.request.path[0] && !currentOutboundValues.path) {
                        currentOutboundValues.path = hdr.request.path[0];
                    }
                    const hdrHosts = hdr.request.headers && hdr.request.headers.Host;
                    if (Array.isArray(hdrHosts) && hdrHosts[0] && !currentOutboundValues.wsHost) {
                        currentOutboundValues.wsHost = hdrHosts[0];
                    }
                }
            } else if (streamObj.wsSettings) {
                currentOutboundValues.network = "ws";
                currentOutboundValues.path = streamObj.wsSettings.path || currentOutboundValues.path;
                if (streamObj.wsSettings.headers) {
                    currentOutboundValues.wsHost = streamObj.wsSettings.headers.Host || currentOutboundValues.wsHost;
                }
            } else if (streamObj.httpupgradeSettings) {
                currentOutboundValues.network = "httpupgrade";
                currentOutboundValues.path = streamObj.httpupgradeSettings.path || currentOutboundValues.path;
                currentOutboundValues.wsHost = streamObj.httpupgradeSettings.host || currentOutboundValues.wsHost;
            } else if (streamObj.xhttpSettings) {
                currentOutboundValues.network = "xhttp";
                currentOutboundValues.path = streamObj.xhttpSettings.path || currentOutboundValues.path;
                currentOutboundValues.wsHost = streamObj.xhttpSettings.host || currentOutboundValues.wsHost;
                currentOutboundValues.xhttpMode = streamObj.xhttpSettings.mode || currentOutboundValues.xhttpMode || "auto";
            } else if (streamObj.httpSettings) {
                currentOutboundValues.network = "h2";
                currentOutboundValues.path = streamObj.httpSettings.path || currentOutboundValues.path;
                const h2Hosts = streamObj.httpSettings.host;
                if (Array.isArray(h2Hosts) && h2Hosts[0]) {
                    currentOutboundValues.wsHost = h2Hosts[0];
                }
            } else if (streamObj.grpcSettings) {
                currentOutboundValues.network = "grpc";
                currentOutboundValues.serviceName = streamObj.grpcSettings.serviceName || currentOutboundValues.serviceName;
                currentOutboundValues.multiMode = Boolean(streamObj.grpcSettings.multiMode);
            }
            if (settingsObj.congestionControl || settingsObj.congestion_control) {
                currentOutboundValues.congestionControl = settingsObj.congestionControl || settingsObj.congestion_control;
            }
            if (settingsObj.udpRelayMode || settingsObj.udp_relay_mode) {
                currentOutboundValues.udpRelayMode = settingsObj.udpRelayMode || settingsObj.udp_relay_mode;
            }
            if (settingsObj.zeroRttHandshake !== undefined || settingsObj.zero_rtt_handshake !== undefined) {
                currentOutboundValues.zeroRttHandshake = Boolean(settingsObj.zeroRttHandshake ?? settingsObj.zero_rtt_handshake);
            }
            if (settingsObj.shadowTlsVersion || settingsObj.version) {
                currentOutboundValues.shadowTlsVersion = String(settingsObj.shadowTlsVersion || settingsObj.version);
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

    function syncDefaultsForProtocol(cap, resetSelectsToAllowed = false) {
        if (!cap || !Array.isArray(cap.tabDefinitions)) return;
        for (const tab of cap.tabDefinitions) {
            for (const group of (tab.groups || [])) {
                for (const field of (group.fields || [])) {
                    if (!field.targetField) continue;
                    const cur = currentOutboundValues[field.targetField];
                    if (field.type === "select" && Array.isArray(field.options) && field.options.length > 0) {
                        const allowed = field.options.map(o => String(o.value ?? ""));
                        if (cur === undefined || (resetSelectsToAllowed && !allowed.includes(String(cur)))) {
                            currentOutboundValues[field.targetField] = field.default !== undefined ? field.default : (field.options[0].value ?? "");
                        }
                    } else if (cur === undefined && field.default !== undefined) {
                        currentOutboundValues[field.targetField] = field.default;
                    }
                }
            }
        }
    }

    // 3. Render Form via Dynamic Schema Engine
    function renderCurrentProtocolForm(resetInvalidSelects = false) {
        const proto = protocolSelect ? protocolSelect.value : (currentOutboundValues.protocol || "vless");
        const activeEngine = engineSelect ? (engineSelect.value || "") : "";
        const cap = outboundProtocols[proto] || outboundProtocols["vless"] || { tabDefinitions: [] };
        syncDefaultsForProtocol(cap, resetInvalidSelects);
        
        const tabsContainer = document.getElementById("outbound-modal-tabs");
        const schemaContainer = document.getElementById("outbound-schema-container");

        renderDynamicOutboundForm(schemaContainer, tabsContainer, cap.tabDefinitions || [], currentOutboundValues, (updatedValues) => {
            currentOutboundValues = updatedValues;
        }, activeEngine);

        // Populate fallback routes dropdown options dynamically
        populateFallbackDropdown(currentOutboundValues);
    }

    if (engineSelect) {
        engineSelect.onchange = () => {
            populateProtocolSelect(engineSelect.value || "");
            renderCurrentProtocolForm(true);
            enhanceAllSelects(modal);
        };
    }

    if (protocolSelect) {
        protocolSelect.onchange = () => {
            currentOutboundValues.protocol = protocolSelect.value;
            renderCurrentProtocolForm(true);
        };
    }

    renderCurrentProtocolForm(false);
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

