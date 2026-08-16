// Sing-box Core Inbound Form Handling

export function compileSingboxSettings(protocol, security, network, streamSettings, settings) {
    if (security === "reality") {
        const dest = document.getElementById("ib-reality-dest").value.trim();
        const sni = document.getElementById("ib-reality-sni").value.trim();
        const pbk = document.getElementById("ib-reality-pbk").value.trim();
        const priv = document.getElementById("ib-reality-priv").value.trim();
        const shortIdsInput = document.getElementById("ib-reality-shortids").value.trim();
        const shortIds = shortIdsInput ? shortIdsInput.split(",").map(s => s.trim()).filter(Boolean) : [];
        const maxTimeDiffInput = document.getElementById("ib-reality-max-time-diff").value.trim();
        
        streamSettings.realitySettings = {
            dest: dest,
            serverName: sni,
            serverNames: sni ? sni.split(",").map(s => s.trim()).filter(Boolean) : [],
            privateKey: priv,
            publicKey: pbk,
            shortIds: shortIds
        };

        if (maxTimeDiffInput && maxTimeDiffInput !== "0s" && maxTimeDiffInput !== "0") {
            streamSettings.realitySettings.maxTimeDiff = maxTimeDiffInput;
            streamSettings.realitySettings.max_time_difference = maxTimeDiffInput;
        }
    } else if (security === "tls") {
        const sni = document.getElementById("ib-tls-sni").value || "";
        const alpnInput = document.getElementById("ib-tls-alpn").value || "h2,http/1.1";
        const alpn = alpnInput.split(",").map(s => s.trim()).filter(Boolean);
        const allowInsecure = document.getElementById("ib-tls-insecure").checked;
        
        streamSettings.tlsSettings = {
            serverName: sni,
            allowInsecure: allowInsecure,
            alpn: alpn
        };
    }

    if (network === "ws") {
        const path = document.getElementById("ib-ws-path").value || "/";
        const host = document.getElementById("ib-ws-host").value || "";
        streamSettings.wsSettings = {
            path: path,
            headers: host ? { Host: host } : {}
        };
    } else if (network === "grpc") {
        const serviceName = document.getElementById("ib-grpc-service").value || "grpc";
        streamSettings.grpcSettings = {
            serviceName: serviceName
        };
    } else if (network === "httpupgrade") {
        const path = document.getElementById("ib-httpupgrade-path").value || "/";
        const host = document.getElementById("ib-httpupgrade-host").value || "";
        streamSettings.httpupgradeSettings = {
            path: path,
            host: host || undefined
        };
    } else if (network === "h2" || network === "http") {
        const path = document.getElementById("ib-h2-path").value || "/";
        const hostInput = document.getElementById("ib-h2-host").value || "";
        const hosts = hostInput.split(",").map(s => s.trim()).filter(Boolean);
        streamSettings.httpSettings = {
            path: path,
            host: hosts
        };
    }
}

export function populateSingboxSettings(protocol, security, network, streamSettings, settings) {
    if (security === "reality") {
        const rs = streamSettings.realitySettings || {};
        document.getElementById("ib-reality-dest").value = rs.dest || "";
        document.getElementById("ib-reality-sni").value = rs.serverName || (rs.serverNames && rs.serverNames.join(", ")) || "";
        document.getElementById("ib-reality-pbk").value = rs.publicKey || "";
        document.getElementById("ib-reality-priv").value = rs.privateKey || "";
        document.getElementById("ib-reality-shortids").value = (rs.shortIds || []).join(", ");
        const mtd = rs.maxTimeDiff || rs.max_time_difference || "";
        document.getElementById("ib-reality-max-time-diff").value = (mtd === "0s" || mtd === "0") ? "" : mtd;
    } else if (security === "tls") {
        const ts = streamSettings.tlsSettings || {};
        document.getElementById("ib-tls-sni").value = ts.serverName || "";
        document.getElementById("ib-tls-alpn").value = (ts.alpn || []).join(", ");
        document.getElementById("ib-tls-insecure").checked = ts.allowInsecure || false;
    }

    if (network === "ws") {
        const ws = streamSettings.wsSettings || {};
        document.getElementById("ib-ws-path").value = ws.path || "/";
        const headers = ws.headers || {};
        document.getElementById("ib-ws-host").value = headers.Host || "";
    } else if (network === "grpc") {
        const gs = streamSettings.grpcSettings || {};
        document.getElementById("ib-grpc-service").value = gs.serviceName || "grpc";
    } else if (network === "httpupgrade") {
        const hu = streamSettings.httpupgradeSettings || {};
        document.getElementById("ib-httpupgrade-path").value = hu.path || "/";
        document.getElementById("ib-httpupgrade-host").value = hu.host || "";
    } else if (network === "h2" || network === "http") {
        const hs = streamSettings.httpSettings || {};
        document.getElementById("ib-h2-path").value = hs.path || "/";
        document.getElementById("ib-h2-host").value = (hs.host || []).join(", ");
    }
}
