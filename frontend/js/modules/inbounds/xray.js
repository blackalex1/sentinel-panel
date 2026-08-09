// Xray Core Inbound Form Handling
import { compileXraySecuritySettings, populateXraySecuritySettings, compileXrayTransportSettings, populateXrayTransportSettings } from "../inbound-protocols.js";

export function compileXraySettings(protocol, security, network, streamSettings, settings) {
    compileXraySecuritySettings(security, streamSettings);
    compileXrayTransportSettings(network, streamSettings);

    if (protocol === "vless") {
        settings.decryption = document.getElementById("ib-vless-decryption").value || "none";
        settings.encryption = document.getElementById("ib-vless-encryption").value || "none";
    }

    const hasDecryption = protocol === "vless" && settings.decryption && settings.decryption.trim() !== "" && settings.decryption.trim().toLowerCase() !== "none";

    if ((protocol === "vless" || protocol === "trojan") && !hasDecryption) {
        const fallbackDest = document.getElementById("ib-fallback-dest").value || "";
        if (fallbackDest) {
            const fallbackPath = document.getElementById("ib-fallback-path").value || "";
            const fallbackXver = parseInt(document.getElementById("ib-fallback-xver").value) || 0;
            const fallbackAlpn = document.getElementById("ib-fallback-alpn").value || "";
            
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
        document.getElementById("ib-vless-decryption").value = settings.decryption || "none";
        document.getElementById("ib-vless-encryption").value = settings.encryption || "none";
    }

    const fallbacks = settings.fallbacks || [];
    if (fallbacks.length > 0) {
        const f = fallbacks[0];
        document.getElementById("ib-fallback-dest").value = f.dest || "";
        document.getElementById("ib-fallback-path").value = f.path || "";
        document.getElementById("ib-fallback-xver").value = f.xver || 0;
        document.getElementById("ib-fallback-alpn").value = f.alpn || "";
    } else {
        document.getElementById("ib-fallback-dest").value = "";
        document.getElementById("ib-fallback-path").value = "";
        document.getElementById("ib-fallback-xver").value = 0;
        document.getElementById("ib-fallback-alpn").value = "";
    }
}
