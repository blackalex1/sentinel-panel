import { generateRandomPassword, editInboundId, switchInboundModalTab } from "./core.js";
import { t } from "../../i18n.js";

export function updateFormToggles() {
    const proto = document.getElementById("ib-protocol").value;
    const network = document.getElementById("ib-network").value;
    const security = document.getElementById("ib-security").value;
    
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
        coreElem.addEventListener("change", () => {
            updateFormToggles();
            updateTabVisibility(document.getElementById("ib-protocol").value);
        });
    }

    // Toggle Sniffing Overrides display
    const sniffingChecked = document.getElementById("ib-sniffing").checked;
    const sniffingOverrides = document.getElementById("sniffing-overrides");
    if (sniffingOverrides) {
        sniffingOverrides.style.display = sniffingChecked ? "flex" : "none";
    }
    
    // VLESS Encryption/Decryption/ML-KEM options are strictly Xray-only!
    if (vlessProtoGroup) {
        vlessProtoGroup.style.display = (proto === "vless" && core === "xray") ? "block" : "none";
    }
    
    if (proto === "vless" || proto === "vmess" || proto === "trojan") {
        if (xrayRow) xrayRow.style.display = "block";
        if (sniffingGroup) sniffingGroup.style.display = "block";
        if (ssGroup) ssGroup.style.display = "none";
        if (hysteriaGroup) hysteriaGroup.style.display = "none";
        
        if (realityGroup) realityGroup.style.display = (security === "reality") ? "block" : "none";
        if (tlsGroup) tlsGroup.style.display = (security === "tls") ? "block" : "none";
        
        // Transport settings subgroups
        if (tcpGroup) tcpGroup.style.display = (network === "tcp") ? "block" : "none";
        if (wsGroup) wsGroup.style.display = (network === "ws") ? "block" : "none";
        if (grpcGroup) grpcGroup.style.display = (network === "grpc") ? "block" : "none";
        if (h2Group) h2Group.style.display = (network === "h2") ? "block" : "none";
        if (httpupgradeGroup) httpupgradeGroup.style.display = (network === "httpupgrade") ? "block" : "none";
        if (xhttpGroup) xhttpGroup.style.display = (network === "xhttp") ? "block" : "none";
        if (mkcpGroup) mkcpGroup.style.display = (network === "mkcp") ? "block" : "none";
        
        // TCP HTTP masquerade fields toggle
        if (network === "tcp") {
            const tcpType = document.getElementById("ib-tcp-type").value;
            const tcpHttp = document.getElementById("tcp-http-settings");
            if (tcpHttp) tcpHttp.style.display = (tcpType === "http") ? "block" : "none";
        }
        
        // Fallbacks settings display is strictly Xray-only!
        if (fallbacksGroup) fallbacksGroup.style.display = ((proto === "vless" || proto === "trojan") && core === "xray") ? "block" : "none";
        
        // Exclusivity between VLESS Decryption and VLESS Fallbacks
        if (proto === "vless") {
            const decryptionInput = document.getElementById("ib-vless-decryption");
            const fallbackDestInput = document.getElementById("ib-fallback-dest");
            const fallbackPathInput = document.getElementById("ib-fallback-path");
            const fallbackXverSelect = document.getElementById("ib-fallback-xver");
            const fallbackAlpnInput = document.getElementById("ib-fallback-alpn");
            
            const decNote = document.getElementById("ib-vless-decryption-note");
            const fallNote = document.getElementById("ib-fallback-dest-note");
 
            if (decryptionInput && fallbackDestInput) {
                const hasFallback = fallbackDestInput.value.trim() !== "";
                const hasDecryption = decryptionInput.value.trim() !== "" && decryptionInput.value.trim() !== "none";
 
                if (hasFallback) {
                    decryptionInput.value = "none";
                    decryptionInput.disabled = true;
                    if (decNote) {
                        decNote.style.color = "var(--accent-rose)";
                        decNote.innerHTML = t("validation_inbound_vless_decryption_disabled_note", "🛑 Отключено: при использовании Fallbacks функция decryption не поддерживается.");
                    }
                } else {
                    decryptionInput.disabled = false;
                    if (decNote) {
                        decNote.style.color = "var(--text-muted)";
                        decNote.innerHTML = t("validation_inbound_vless_decryption_incompatible_note", "⚠️ Взаимоисключающая опция: несовместима с настройками Fallbacks (перенаправления).");
                    }
                }
 
                if (hasDecryption) {
                    fallbackDestInput.value = "";
                    fallbackPathInput.value = "";
                    fallbackXverSelect.value = "0";
                    fallbackAlpnInput.value = "";
 
                    fallbackDestInput.disabled = true;
                    fallbackPathInput.disabled = true;
                    fallbackXverSelect.disabled = true;
                    fallbackAlpnInput.disabled = true;
 
                    if (fallNote) {
                        fallNote.style.color = "var(--accent-rose)";
                        fallNote.innerHTML = t("validation_inbound_vless_fallbacks_disabled_note", "🛑 Отключено: при использовании VLESS Decryption функция Fallbacks не поддерживается.");
                    }
                } else {
                    fallbackDestInput.disabled = false;
                    fallbackPathInput.disabled = false;
                    fallbackXverSelect.disabled = false;
                    fallbackAlpnInput.disabled = false;
 
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
    } else if (proto === "socks" || proto === "http") {
        if (xrayRow) xrayRow.style.display = "none";
        if (sniffingGroup) sniffingGroup.style.display = "none";
        if (ssGroup) ssGroup.style.display = "none";
        if (hysteriaGroup) hysteriaGroup.style.display = "none";
        if (fallbacksGroup) fallbacksGroup.style.display = "none";
    }
}

export function updateTabVisibility(proto) {
    const tabProtocol = document.getElementById("ib-tab-protocol");
    const tabStream = document.getElementById("ib-tab-stream");
    const tabSecurity = document.getElementById("ib-tab-security");
    const tabSniffing = document.getElementById("ib-tab-sniffing");
    const coreElem = document.getElementById("ib-core");
    const core = coreElem ? coreElem.value : "xray";
    
    if (!tabProtocol || !tabStream || !tabSecurity || !tabSniffing) return;
    
    if (proto === "vless" || proto === "vmess" || proto === "trojan") {
        if (core === "singbox") {
            tabProtocol.style.display = "none";
        } else {
            tabProtocol.style.display = "inline-block";
        }
        tabStream.style.display = "inline-block";
        tabSecurity.style.display = "inline-block";
        tabSniffing.style.display = (core === "xray") ? "inline-block" : "none";
    } else if (proto === "shadowsocks") {
        tabProtocol.style.display = "inline-block";
        tabStream.style.display = "none";
        tabSecurity.style.display = "none";
        tabSniffing.style.display = "none";
    } else if (proto === "hysteria2") {
        tabProtocol.style.display = "none";
        tabStream.style.display = "inline-block";
        tabSecurity.style.display = "none";
        tabSniffing.style.display = "none";
    } else if (proto === "socks" || proto === "http") {
        tabProtocol.style.display = "none";
        tabStream.style.display = "none";
        tabSecurity.style.display = "none";
        tabSniffing.style.display = "none";
    }
    
    // Auto switch to Basic if current active tab is hidden
    const activeTabButton = document.querySelector(".modal-tab-btn.active");
    if (activeTabButton) {
        const activeTab = activeTabButton.getAttribute("data-tab");
        const targetBtn = document.querySelector(`.modal-tab-btn[data-tab='${activeTab}']`);
        if (targetBtn && targetBtn.style.display === "none") {
            switchInboundModalTab("basic");
        }
    }
}

export function updateCoreOptions(proto) {
    const coreSelect = document.getElementById("ib-core");
    if (!coreSelect) return;
    
    const currentCore = coreSelect.value;
    coreSelect.innerHTML = "";
    
    if (proto === "hysteria2") {
        coreSelect.appendChild(new Option("Hysteria 2", "hysteria"));
        coreSelect.appendChild(new Option("sing-box", "singbox"));
    } else {
        coreSelect.appendChild(new Option("Xray-core", "xray"));
        coreSelect.appendChild(new Option("sing-box", "singbox"));
    }
    
    const hasOption = Array.from(coreSelect.options).some(opt => opt.value === currentCore);
    if (hasOption) {
        coreSelect.value = currentCore;
    } else {
        coreSelect.value = coreSelect.options[0].value;
    }
}

export function handleProtocolChange(proto) {
    const networkSelect = document.getElementById("ib-network");
    const securitySelect = document.getElementById("ib-security");
    
    if (proto === "vless") {
        networkSelect.value = "tcp";
        securitySelect.value = "reality";
    } else if (proto === "vmess") {
        networkSelect.value = "ws";
        securitySelect.value = "none";
    } else if (proto === "trojan") {
        networkSelect.value = "tcp";
        securitySelect.value = "tls";
    } else if (proto === "hysteria2") {
        const obfsInput = document.getElementById("ib-hysteria-obfs-password");
        if (obfsInput && !obfsInput.value && !editInboundId) {
            obfsInput.value = generateRandomPassword(16);
        }
    }
    updateCoreOptions(proto);
    updateFormToggles();
    updateTabVisibility(proto);
}
