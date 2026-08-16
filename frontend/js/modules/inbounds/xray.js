// Xray Core Inbound Form Handling
import { compileXraySecuritySettings, populateXraySecuritySettings, compileXrayTransportSettings, populateXrayTransportSettings } from "../inbound-protocols.js";

export function compileXraySettings(protocol, security, network, streamSettings, settings) {
    compileXraySecuritySettings(security, streamSettings);
    compileXrayTransportSettings(network, streamSettings);

    if (protocol === "vless") {
        const decElem = document.getElementById("ib-vless-decryption");
        const encElem = document.getElementById("ib-vless-encryption");
        settings.decryption = decElem ? (decElem.value || "none") : "none";
        settings.encryption = encElem ? (encElem.value || "none") : "none";
    }

    const hasDecryption = protocol === "vless" && settings.decryption && settings.decryption.trim() !== "" && settings.decryption.trim().toLowerCase() !== "none";

    if ((protocol === "vless" || protocol === "trojan") && !hasDecryption) {
        const fallbackDestElem = document.getElementById("ib-fallback-dest");
        const fallbackDest = fallbackDestElem ? (fallbackDestElem.value || "") : "";
        if (fallbackDest) {
            const fallbackPathElem = document.getElementById("ib-fallback-path");
            const fallbackXverElem = document.getElementById("ib-fallback-xver");
            const fallbackAlpnElem = document.getElementById("ib-fallback-alpn");
            const fallbackPath = fallbackPathElem ? (fallbackPathElem.value || "") : "";
            const fallbackXver = fallbackXverElem ? (parseInt(fallbackXverElem.value) || 0) : 0;
            const fallbackAlpn = fallbackAlpnElem ? (fallbackAlpnElem.value || "") : "";
            
            const fallback = {
                dest: fallbackDest.includes(":") ? fallbackDest : parseInt(fallbackDest) || fallbackDest,
                xver: fallbackXver
            };
            if (fallbackPath) fallback.path = fallbackPath;
            if (fallbackAlpn) fallback.alpn = fallbackAlpn;
            
            settings.fallbacks = [fallback];
        }
    } else if (hasDecryption) {
        delete settings.fallbacks;
    }
}

export function populateXraySettings(protocol, security, network, streamSettings, settings) {
    populateXraySecuritySettings(security, streamSettings);
    populateXrayTransportSettings(network, streamSettings);

    if (protocol === "vless") {
        const decElem = document.getElementById("ib-vless-decryption");
        const encElem = document.getElementById("ib-vless-encryption");
        if (decElem) decElem.value = settings.decryption || "none";
        if (encElem) encElem.value = settings.encryption || "none";
    }

    const fallbacks = settings.fallbacks || [];
    const destElem = document.getElementById("ib-fallback-dest");
    const pathElem = document.getElementById("ib-fallback-path");
    const xverElem = document.getElementById("ib-fallback-xver");
    const alpnElem = document.getElementById("ib-fallback-alpn");
    if (fallbacks.length > 0) {
        const f = fallbacks[0];
        if (destElem) destElem.value = f.dest || "";
        if (pathElem) pathElem.value = f.path || "";
        if (xverElem) xverElem.value = f.xver || 0;
        if (alpnElem) alpnElem.value = f.alpn || "";
    } else {
        if (destElem) destElem.value = "";
        if (pathElem) pathElem.value = "";
        if (xverElem) xverElem.value = 0;
        if (alpnElem) alpnElem.value = "";
    }
}
