import { generateRandomPassword, editInboundId, switchInboundModalTab } from "./core.js";
import { renderDynamicModalTabs, normalizeEngineId } from "./schema-renderer.js";
import { t } from "../../i18n.js";
import { apiFetch } from "../../api.js";

export function updateFormToggles() {
    const protoElem = document.getElementById("ib-protocol");
    const netElem = document.getElementById("ib-network");
    const secElem = document.getElementById("ib-security");
    
    const proto = protoElem ? protoElem.value : "vless";
    const network = netElem ? netElem.value : "tcp";
    const security = secElem ? secElem.value : "reality";
    
    const xrayRow = document.getElementById("xray-network-security-row");
    const sniffingGroup = document.getElementById("ib-sniffing-group");
    const realityGroup = document.getElementById("reality-settings-group");
    const tlsGroup = document.getElementById("tls-settings-group");
    const wsGroup = document.getElementById("ws-settings-group");
    const grpcGroup = document.getElementById("grpc-settings-group");
    const tcpGroup = document.getElementById("tcp-settings-group");
    const h2Group = document.getElementById("h2-settings-group");
    const httpupgradeGroup = document.getElementById("httpupgrade-settings-group");
    const xhttpGroup = document.getElementById("xhttp-settings-group");
    const mkcpGroup = document.getElementById("mkcp-settings-group");
    const ssGroup = document.getElementById("shadowsocks-settings-group");
    const hysteriaGroup = document.getElementById("hysteria-settings-group");
    const fallbacksGroup = document.getElementById("fallbacks-settings-group");
    const vlessProtoGroup = document.getElementById("vless-protocol-settings-group");
    
    const coreElem = document.getElementById("ib-core");
    const core = coreElem ? coreElem.value : "xray";
    
    // Bind change listener on ib-core if not already bound
    if (coreElem && !coreElem.dataset.bound) {
        coreElem.dataset.bound = "true";
        coreElem.addEventListener("change", async () => {
            const p = document.getElementById("ib-protocol") ? document.getElementById("ib-protocol").value : "vless";
            await syncInboundOptionsFromSchema(p, coreElem.value);
            updateFormToggles();
            await updateTabVisibility(p);
        });
    }

    // Toggle Sniffing Overrides display
    const sniffingInput = document.getElementById("ib-sniffing");
    const sniffingChecked = sniffingInput ? sniffingInput.checked : false;
    const sniffingOverrides = document.getElementById("sniffing-overrides");
    if (sniffingOverrides) {
        sniffingOverrides.style.display = sniffingChecked ? "flex" : "none";
    }
    
    // VLESS Encryption/Decryption/ML-KEM options are strictly Xray-only!
    const isXray = (core === "xray" || core === "xray-core" || !core || core === "");
    if (vlessProtoGroup) {
        vlessProtoGroup.style.display = (proto === "vless" && isXray) ? "block" : "none";
    }
    
    if (proto === "vless" || proto === "vmess" || proto === "trojan") {
        if (xrayRow) xrayRow.style.display = "block";
        if (sniffingGroup) sniffingGroup.style.display = "block";
        if (ssGroup) ssGroup.style.display = "none";
        if (hysteriaGroup) hysteriaGroup.style.display = "none";
        
        if (realityGroup) realityGroup.style.display = (security === "reality") ? "block" : "none";
        if (tlsGroup) tlsGroup.style.display = (security === "tls") ? "block" : "none";
        
        // Transport settings subgroups (Xray-only controls hidden when core is sing-box)
        if (tcpGroup) tcpGroup.style.display = (network === "tcp" && isXray) ? "block" : "none";
        if (wsGroup) wsGroup.style.display = (network === "ws") ? "block" : "none";
        if (grpcGroup) grpcGroup.style.display = (network === "grpc") ? "block" : "none";
        if (h2Group) h2Group.style.display = (network === "h2" && !isXray) ? "block" : "none";
        if (httpupgradeGroup) httpupgradeGroup.style.display = (network === "httpupgrade") ? "block" : "none";
        if (xhttpGroup) xhttpGroup.style.display = (network === "xhttp" && isXray) ? "block" : "none";
        if (mkcpGroup) mkcpGroup.style.display = (network === "mkcp" && isXray) ? "block" : "none";

        const grpcMultiGroup = document.getElementById("ib-grpc-multi-mode")?.closest(".input-group");
        if (grpcMultiGroup) grpcMultiGroup.style.display = isXray ? "block" : "none";

        const realitySpxGroup = document.getElementById("ib-reality-spx")?.closest(".input-group");
        if (realitySpxGroup) realitySpxGroup.style.display = isXray ? "block" : "none";

        // TCP HTTP masquerade fields toggle
        if (network === "tcp" && isXray) {
            const tcpTypeElem = document.getElementById("ib-tcp-type");
            const tcpType = tcpTypeElem ? tcpTypeElem.value : "none";
            const tcpHttp = document.getElementById("tcp-http-settings");
            if (tcpHttp) tcpHttp.style.display = (tcpType === "http") ? "block" : "none";
        } else {
            const tcpHttp = document.getElementById("tcp-http-settings");
            if (tcpHttp) tcpHttp.style.display = "none";
        }
        
        // Fallbacks settings display is strictly Xray-only!
        if (fallbacksGroup) fallbacksGroup.style.display = ((proto === "vless" || proto === "trojan") && isXray) ? "block" : "none";
        
        // Exclusivity between VLESS Decryption and VLESS Fallbacks
        if (proto === "vless") {
            const decryptionInput = document.getElementById("ib-vless-decryption");
            const encryptionInput = document.getElementById("ib-vless-encryption");
            const genX25519Btn = document.getElementById("gen-vless-x25519-btn");
            const genMlkemBtn = document.getElementById("gen-vless-mlkem-btn");

            const fallbackDestInput = document.getElementById("ib-fallback-dest");
            const fallbackPathInput = document.getElementById("ib-fallback-path");
            const fallbackXverSelect = document.getElementById("ib-fallback-xver");
            const fallbackAlpnInput = document.getElementById("ib-fallback-alpn");
            
            const decNote = document.getElementById("ib-vless-decryption-note");
            const fallNote = document.getElementById("ib-fallback-dest-note");

            if (decryptionInput && fallbackDestInput) {
                const hasDecryption = decryptionInput.value.trim() !== "" && decryptionInput.value.trim().toLowerCase() !== "none";
                const hasFallback = fallbackDestInput.value.trim() !== "";

                if (hasDecryption) {
                    fallbackDestInput.value = "";
                    if (fallbackPathInput) fallbackPathInput.value = "";
                    if (fallbackXverSelect) fallbackXverSelect.value = "0";
                    if (fallbackAlpnInput) fallbackAlpnInput.value = "";

                    fallbackDestInput.disabled = true;
                    if (fallbackPathInput) fallbackPathInput.disabled = true;
                    if (fallbackXverSelect) fallbackXverSelect.disabled = true;
                    if (fallbackAlpnInput) fallbackAlpnInput.disabled = true;

                    if (fallNote) {
                        fallNote.style.color = "var(--accent-rose)";
                        fallNote.innerHTML = t("validation_inbound_vless_fallbacks_disabled_note", "🛑 Отключено: при использовании VLESS Decryption функция Fallbacks не поддерживается.");
                    }

                    decryptionInput.disabled = false;
                    if (encryptionInput) encryptionInput.disabled = false;
                    if (genX25519Btn) genX25519Btn.disabled = false;
                    if (genMlkemBtn) genMlkemBtn.disabled = false;
                    if (decNote) {
                        decNote.style.color = "var(--text-muted)";
                        decNote.innerHTML = t("validation_inbound_vless_decryption_incompatible_note", "⚠️ Взаимоисключающая опция: несовместима с настройками Fallbacks (перенаправления).");
                    }
                } else if (hasFallback) {
                    decryptionInput.value = "none";
                    decryptionInput.disabled = true;
                    if (encryptionInput) {
                        encryptionInput.value = "none";
                        encryptionInput.disabled = true;
                    }
                    if (genX25519Btn) genX25519Btn.disabled = true;
                    if (genMlkemBtn) genMlkemBtn.disabled = true;

                    if (decNote) {
                        decNote.style.color = "var(--accent-rose)";
                        decNote.innerHTML = t("validation_inbound_vless_decryption_disabled_note", "🛑 Отключено: при использовании Fallbacks функция decryption не поддерживается.");
                    }

                    fallbackDestInput.disabled = false;
                    if (fallbackPathInput) fallbackPathInput.disabled = false;
                    if (fallbackXverSelect) fallbackXverSelect.disabled = false;
                    if (fallbackAlpnInput) fallbackAlpnInput.disabled = false;
                    if (fallNote) {
                        fallNote.style.color = "var(--text-muted)";
                        fallNote.innerHTML = t("validation_inbound_vless_fallbacks_incompatible_note", "⚠️ Взаимоисключающая опция: несовместима с VLESS Decryption (Расшифрование).");
                    }
                } else {
                    decryptionInput.disabled = false;
                    if (encryptionInput) encryptionInput.disabled = false;
                    if (genX25519Btn) genX25519Btn.disabled = false;
                    if (genMlkemBtn) genMlkemBtn.disabled = false;

                    fallbackDestInput.disabled = false;
                    if (fallbackPathInput) fallbackPathInput.disabled = false;
                    if (fallbackXverSelect) fallbackXverSelect.disabled = false;
                    if (fallbackAlpnInput) fallbackAlpnInput.disabled = false;

                    if (decNote) {
                        decNote.style.color = "var(--text-muted)";
                        decNote.innerHTML = t("validation_inbound_vless_decryption_incompatible_note", "⚠️ Взаимоисключающая опция: несовместима с настройками Fallbacks (перенаправления).");
                    }
                    if (fallNote) {
                        fallNote.style.color = "var(--text-muted)";
                        fallNote.innerHTML = t("validation_inbound_vless_fallbacks_incompatible_note", "⚠️ Взаимоисключающая опция: несовместима с VLESS Decryption (Расшифрование).");
                    }
                }
            }
        }
        
        // Custom security restrictions
        if (proto === "vmess" || proto === "trojan") {
            const realityOption = document.querySelector("#ib-security option[value='reality']");
            if (realityOption) {
                if (security === "reality") {
                    document.getElementById("ib-security").value = "tls";
                    if (realityGroup) realityGroup.style.display = "none";
                    if (tlsGroup) tlsGroup.style.display = "block";
                }
                realityOption.disabled = true;
            }
        } else {
            const realityOption = document.querySelector("#ib-security option[value='reality']");
            if (realityOption) realityOption.disabled = false;
        }
    } else if (proto === "shadowsocks") {
        if (xrayRow) xrayRow.style.display = "none";
        if (sniffingGroup) sniffingGroup.style.display = "none";
        if (realityGroup) realityGroup.style.display = "none";
        if (tlsGroup) tlsGroup.style.display = "none";
        if (tcpGroup) tcpGroup.style.display = "none";
        if (wsGroup) wsGroup.style.display = "none";
        if (grpcGroup) grpcGroup.style.display = "none";
        if (h2Group) h2Group.style.display = "none";
        if (httpupgradeGroup) httpupgradeGroup.style.display = "none";
        if (xhttpGroup) xhttpGroup.style.display = "none";
        if (mkcpGroup) mkcpGroup.style.display = "none";
        if (ssGroup) ssGroup.style.display = "block";
        if (hysteriaGroup) hysteriaGroup.style.display = "none";
        if (fallbacksGroup) fallbacksGroup.style.display = "none";
    } else if (proto === "hysteria2") {
        if (xrayRow) xrayRow.style.display = "none";
        if (sniffingGroup) sniffingGroup.style.display = "none";
        if (realityGroup) realityGroup.style.display = "none";
        if (tlsGroup) tlsGroup.style.display = "none";
        if (tcpGroup) tcpGroup.style.display = "none";
        if (wsGroup) wsGroup.style.display = "none";
        if (grpcGroup) grpcGroup.style.display = "none";
        if (h2Group) h2Group.style.display = "none";
        if (httpupgradeGroup) httpupgradeGroup.style.display = "none";
        if (xhttpGroup) xhttpGroup.style.display = "none";
        if (mkcpGroup) mkcpGroup.style.display = "none";
        if (ssGroup) ssGroup.style.display = "none";
        if (hysteriaGroup) hysteriaGroup.style.display = "block";
        const hy2RoutingGroup = document.getElementById("ib-hysteria-routing-xray")?.closest(".input-group");
        if (hy2RoutingGroup) hy2RoutingGroup.style.display = (core === "sing-box") ? "none" : "block";
        
        // Hysteria 2 Protection Mode (masq vs obfs)
        const hystModeElem = document.getElementById("ib-hysteria-mode");
        if (hystModeElem && !hystModeElem.dataset.bound) {
            hystModeElem.dataset.bound = "true";
            hystModeElem.addEventListener("change", () => {
                updateFormToggles();
            });
        }
        const hystMode = hystModeElem ? hystModeElem.value : "masq";
        const masqGroup = document.getElementById("hysteria-masq-group");
        const obfsGroup = document.getElementById("hysteria-obfs-group");
        if (masqGroup) masqGroup.style.display = (hystMode === "masq") ? "block" : "none";
        if (obfsGroup) obfsGroup.style.display = (hystMode === "obfs") ? "block" : "none";

        // Hysteria 2 Certificate Mode (self vs custom)
        const certModeElem = document.getElementById("ib-hysteria-cert-mode");
        if (certModeElem && !certModeElem.dataset.bound) {
            certModeElem.dataset.bound = "true";
            certModeElem.addEventListener("change", () => {
                updateFormToggles();
            });
        }
        const certMode = certModeElem ? certModeElem.value : "self";
        const customCertFields = document.getElementById("hysteria-custom-cert-fields");
        if (customCertFields) customCertFields.style.display = (certMode === "custom") ? "block" : "none";
    } else if (proto === "socks" || proto === "http") {
        if (xrayRow) xrayRow.style.display = "none";
        if (sniffingGroup) sniffingGroup.style.display = "none";
        if (ssGroup) ssGroup.style.display = "none";
        if (hysteriaGroup) hysteriaGroup.style.display = "none";
        if (fallbacksGroup) fallbacksGroup.style.display = "none";
    }

    const noProtoGroup = document.getElementById("no-protocol-settings-group");
    if (noProtoGroup) {
        const hasVisibleProtoSettings = (
            (vlessProtoGroup && vlessProtoGroup.style.display === "block") ||
            (fallbacksGroup && fallbacksGroup.style.display === "block") ||
            (ssGroup && ssGroup.style.display === "block")
        );
        noProtoGroup.style.display = hasVisibleProtoSettings ? "none" : "block";
    }
}

export async function updateTabVisibility(proto) {
    const tabsContainer = document.querySelector("#inbound-modal .modal-tabs");
    const coreElem = document.getElementById("ib-core");
    const core = (coreElem && coreElem.value) ? coreElem.value : "xray";
    const isXray = (core === "xray" || core === "xray-core" || !core);
    const protoKey = (proto === "hysteria") ? "hysteria2" : proto;

    try {
        const schema = await fetchCapabilitiesSchema();
        const protoCap = (schema && schema.protocols) ? schema.protocols[protoKey] : null;

        if (protoCap && Array.isArray(protoCap.tabDefinitions) && protoCap.tabDefinitions.length > 0) {
            const activeTabBtn = tabsContainer ? tabsContainer.querySelector(".modal-tab-btn.active") : null;
            let currentActiveTab = activeTabBtn ? activeTabBtn.getAttribute("data-tab") : "basic";

            // Filter out protocol tab if not supported on current core
            let visibleTabDefs = protoCap.tabDefinitions.filter(tab => {
                if (tab.id === "protocol" && proto === "vless" && !isXray) return false;
                return true;
            });

            // If current active tab is not in visible definitions, default to basic
            if (!visibleTabDefs.some(t => t.id === currentActiveTab)) {
                currentActiveTab = "basic";
            }

            renderDynamicModalTabs(tabsContainer, visibleTabDefs, currentActiveTab, (tabId) => {
                switchInboundModalTab(tabId);
            });

            switchInboundModalTab(currentActiveTab);
            return;
        }

        // Fallback for legacy schema format
        const tabProtocol = document.getElementById("ib-tab-protocol");
        const tabStream = document.getElementById("ib-tab-stream");
        const tabSecurity = document.getElementById("ib-tab-security");
        const tabSniffing = document.getElementById("ib-tab-sniffing");
        const tabAdvanced = document.getElementById("ib-tab-advanced");

        if (protoCap && Array.isArray(protoCap.tabs)) {
            const tabs = protoCap.tabs;
            const showProtoTab = tabs.includes("protocol") && (proto !== "vless" || isXray);
            if (tabProtocol) tabProtocol.style.display = showProtoTab ? "inline-block" : "none";
            if (tabStream) tabStream.style.display = tabs.includes("stream") ? "inline-block" : "none";
            if (tabSecurity) tabSecurity.style.display = tabs.includes("security") ? "inline-block" : "none";
            if (tabSniffing) tabSniffing.style.display = tabs.includes("sniffing") ? "inline-block" : "none";
            if (tabAdvanced) tabAdvanced.style.display = tabs.includes("advanced") ? "inline-block" : "none";
        }
    } catch (e) {
        console.warn("Error resolving dynamic schema tabs:", e);
    }
}

let cachedCapabilitiesSchema = null;

export async function fetchCapabilitiesSchema() {
    if (!cachedCapabilitiesSchema) {
        try {
            const res = await apiFetch("/api/v1/schema/capabilities");
            if (res && res.success && res.obj) {
                cachedCapabilitiesSchema = res.obj;
            }
        } catch (e) {
            console.warn("Failed to fetch capabilities schema:", e);
        }
    }
    return cachedCapabilitiesSchema;
}

export async function updateCoreOptions(proto) {
    const coreSelect = document.getElementById("ib-core");
    if (!coreSelect) return;
    
    const protoKey = (proto === "hysteria") ? "hysteria2" : proto;

    try {
        const schema = await fetchCapabilitiesSchema();
        if (schema && schema.protocols && schema.protocols[protoKey]) {
            const supportedEngines = schema.protocols[protoKey].supportedEngines || [];
            
            const newOptions = [];
            (schema.engines || []).forEach(eng => {
                const engId = eng.id;
                let val = engId;
                if (engId === "xray-core") val = "xray";
                if (engId === "sing-box") val = "singbox";
                if (engId === "hysteria2") val = "hysteria";

                if (supportedEngines.includes(engId) || supportedEngines.includes(val)) {
                    newOptions.push({ name: eng.name, val });
                }
            });

            // Check if options actually changed before touching DOM
            const currentOpts = Array.from(coreSelect.options).map(o => o.value);
            const newOptVals = newOptions.map(o => o.val);
            const isSame = currentOpts.length === newOptVals.length && currentOpts.every((v, i) => v === newOptVals[i]);

            if (!isSame) {
                const previousVal = coreSelect.value;
                coreSelect.innerHTML = "";
                newOptions.forEach(opt => {
                    coreSelect.appendChild(new Option(opt.name, opt.val));
                });
                const valid = newOptVals.includes(previousVal);
                if (valid) {
                    coreSelect.value = previousVal;
                } else if (coreSelect.options.length > 0) {
                    coreSelect.value = coreSelect.options[0].value;
                }
                await syncInboundOptionsFromSchema(proto, coreSelect.value);
                coreSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
    } catch (e) {
        console.warn("Error updating core options from schema:", e);
    }
}

function syncSelectOptionsFromList(selectEl, values, labelMap = {}, preferredDefault = null) {
    if (!selectEl || !Array.isArray(values) || values.length === 0) return false;
    const currentOpts = Array.from(selectEl.options).map(o => o.value);
    const same = currentOpts.length === values.length && currentOpts.every((v, i) => v === values[i]);
    const prevVal = selectEl.value;
    if (!same) {
        selectEl.innerHTML = "";
        values.forEach(v => {
            selectEl.appendChild(new Option(labelMap[v] || v, v));
        });
    }
    if (values.includes(prevVal)) {
        selectEl.value = prevVal;
        return false;
    }
    if (preferredDefault && values.includes(preferredDefault)) {
        selectEl.value = preferredDefault;
    } else {
        selectEl.value = values[0];
    }
    return selectEl.value !== prevVal;
}

export async function syncInboundOptionsFromSchema(proto, coreOverride = null) {
    const schema = await fetchCapabilitiesSchema();
    if (!schema || !schema.protocols) return;

    const protoKey = (proto === "hysteria") ? "hysteria2" : proto;
    const cap = schema.protocols[protoKey];
    if (!cap) return;

    const coreElem = document.getElementById("ib-core");
    const normEngine = normalizeEngineId(coreOverride !== null ? coreOverride : (coreElem ? coreElem.value : ""));

    // 1. Transports for active engine
    const netLabels = {
        tcp: "TCP (Raw)",
        ws: "WebSocket (ws)",
        grpc: "gRPC",
        h2: "HTTP/2 (h2)",
        http: "HTTP/2 (http)",
        httpupgrade: "HTTPUpgrade",
        xhttp: "XHTTP (SplitHTTP)",
        mkcp: "mKCP (UDP)",
        quic: "QUIC"
    };
    const engTransports = (cap.engineTransports && normEngine && Array.isArray(cap.engineTransports[normEngine]))
        ? cap.engineTransports[normEngine]
        : cap.supportedTransports;
    if (Array.isArray(engTransports) && engTransports.length > 0) {
        const netSelect = document.getElementById("ib-network");
        syncSelectOptionsFromList(netSelect, engTransports, netLabels, cap.defaultTransport || engTransports[0]);
    }

    // 2. Security modes for active engine
    const secLabels = {
        reality: "REALITY",
        tls: "TLS",
        none: "None",
        shadowtls: "ShadowTLS"
    };
    const engSec = (cap.engineSecurity && normEngine && Array.isArray(cap.engineSecurity[normEngine]))
        ? cap.engineSecurity[normEngine]
        : cap.supportedSecurity;
    if (Array.isArray(engSec) && engSec.length > 0) {
        const secSelect = document.getElementById("ib-security");
        syncSelectOptionsFromList(secSelect, engSec, secLabels, cap.defaultSecurity || engSec[0]);
    }

    // 3. uTLS Fingerprints (from schema engineFingerprints or outbound fallback, never hardcoded 'opera')
    let fps = (cap.engineFingerprints && normEngine && Array.isArray(cap.engineFingerprints[normEngine]))
        ? cap.engineFingerprints[normEngine]
        : null;
    if (!fps && cap.engineFingerprints) {
        const firstKey = Object.keys(cap.engineFingerprints)[0];
        if (firstKey) fps = cap.engineFingerprints[firstKey];
    }
    if (Array.isArray(fps) && fps.length > 0) {
        syncSelectOptionsFromList(document.getElementById("ib-tls-fp"), fps, {}, "chrome");
        syncSelectOptionsFromList(document.getElementById("ib-reality-fp"), fps, {}, "chrome");
    }
}

export async function handleProtocolChange(proto) {
    const networkSelect = document.getElementById("ib-network");
    const securitySelect = document.getElementById("ib-security");
    
    if (proto === "vless") {
        if (networkSelect) networkSelect.value = "tcp";
        if (securitySelect) securitySelect.value = "reality";
    } else if (proto === "vmess") {
        if (networkSelect) networkSelect.value = "ws";
        if (securitySelect) securitySelect.value = "none";
    } else if (proto === "trojan") {
        if (networkSelect) networkSelect.value = "tcp";
        if (securitySelect) securitySelect.value = "tls";
    } else if (proto === "hysteria2" || proto === "hysteria") {
        if (networkSelect) networkSelect.value = "quic";
        if (securitySelect) securitySelect.value = "tls";
    }
    
    await updateCoreOptions(proto);
    await syncInboundOptionsFromSchema(proto);
    updateFormToggles();
    await updateTabVisibility(proto);
}

