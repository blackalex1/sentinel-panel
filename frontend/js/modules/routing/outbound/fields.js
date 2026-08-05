import { t } from "../../../i18n.js";

export function updateOutboundFormFields() {
    const protocol = document.getElementById("ob-protocol").value;
    const proxyFields = document.getElementById("ob-proxy-fields");
    const ssMethodGroup = document.getElementById("ob-ss-method-group");
    const usernameField = document.getElementById("ob-username").parentElement;
    
    const securityFields = document.getElementById("ob-security-fields");
    const securityGroup = document.getElementById("ob-security-group");
    const realityFields = document.getElementById("ob-reality-fields");
    const alpnGroup = document.getElementById("ob-alpn-group");
    const flowGroup = document.getElementById("ob-flow-group");
    const encryptionGroup = document.getElementById("ob-encryption-group");
    
    const hysteriaFields = document.getElementById("ob-hysteria-fields");
    const wireguardFields = document.getElementById("ob-wireguard-fields");
    
    if (wireguardFields) {
        wireguardFields.style.display = (protocol === "wireguard") ? "block" : "none";
    }
    
    if (encryptionGroup) {
        encryptionGroup.style.display = (protocol === "vless") ? "block" : "none";
    }
    
    // Label for password field
    const passLabel = document.querySelector("label[for='ob-password']");
    if (passLabel) {
        if (protocol === "vless") {
            passLabel.innerText = "UUID";
        } else if (protocol === "hysteria" || protocol === "hysteria2") {
            passLabel.innerText = t("validation_outbound_password_auth_label", "Пароль (Auth)");
        } else {
            passLabel.innerText = t("routing_modal_password", "Пароль / Ключ");
        }
    }
    
    if (protocol === "socks" || protocol === "http" || protocol === "shadowsocks" || protocol === "vless" || protocol === "hysteria" || protocol === "hysteria2") {
        proxyFields.style.display = "block";
        
        if (protocol === "shadowsocks") {
            ssMethodGroup.style.display = "block";
            usernameField.style.display = "none";
            
            securityFields.style.display = "none";
            hysteriaFields.style.display = "none";
        } else if (protocol === "vless") {
            ssMethodGroup.style.display = "none";
            usernameField.style.display = "none";
            
            securityFields.style.display = "block";
            securityGroup.style.display = "block";
            
            const security = document.getElementById("ob-security").value;
            realityFields.style.display = (security === "reality") ? "block" : "none";
            alpnGroup.style.display = (security === "tls") ? "block" : "none";
            flowGroup.style.display = "block";
            
            hysteriaFields.style.display = "none";
            
            const insecureGroup = document.getElementById("ob-insecure-group");
            const pinnedGroup = document.getElementById("ob-pinned-sha256-group");
            if (insecureGroup) {
                insecureGroup.style.display = (security === "tls") ? "block" : "none";
            }
            if (pinnedGroup) {
                pinnedGroup.style.display = (security === "tls") ? "block" : "none";
            }
        } else if (protocol === "hysteria" || protocol === "hysteria2") {
            ssMethodGroup.style.display = "none";
            usernameField.style.display = "none";
            
            securityFields.style.display = "block";
            securityGroup.style.display = "none"; // Hysteria always uses TLS
            realityFields.style.display = "none";
            alpnGroup.style.display = "block";
            flowGroup.style.display = "none";
            
            hysteriaFields.style.display = "block";
            
            const insecureGroup = document.getElementById("ob-insecure-group");
            if (insecureGroup) {
                insecureGroup.style.display = "block";
            }
            const pinnedGroup = document.getElementById("ob-pinned-sha256-group");
            if (pinnedGroup) {
                pinnedGroup.style.display = "block";
            }

            const obfsVal = document.getElementById("ob-hysteria-obfs").value;
            const obfsPwdGroup = document.getElementById("ob-hysteria-obfs-password-group");
            if (obfsPwdGroup) {
                obfsPwdGroup.style.display = (obfsVal === "salamander") ? "block" : "none";
            }
        } else {
            // SOCKS, HTTP
            ssMethodGroup.style.display = "none";
            usernameField.style.display = "block";
            
            securityFields.style.display = "none";
            hysteriaFields.style.display = "none";
            if (usernameField) usernameField.style.display = "block";
            
            const insecureGroup = document.getElementById("ob-insecure-group");
            if (insecureGroup) insecureGroup.style.display = "none";
            const pinnedGroup = document.getElementById("ob-pinned-sha256-group");
            if (pinnedGroup) pinnedGroup.style.display = "none";
        }
    } else {
        proxyFields.style.display = "none";
        securityFields.style.display = "none";
        hysteriaFields.style.display = "none";
        const insecureGroup = document.getElementById("ob-insecure-group");
        if (insecureGroup) insecureGroup.style.display = "none";
        const pinnedGroup = document.getElementById("ob-pinned-sha256-group");
        if (pinnedGroup) pinnedGroup.style.display = "none";
    }
}
