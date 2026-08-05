import { t } from "../i18n.js";

// Compiles Xray security settings (Reality, TLS, or None)
export function compileXraySecuritySettings(security, streamSettings) {
    if (security === "reality") {
        const dest = document.getElementById("ib-reality-dest").value || "yahoo.com:443";
        const sni = document.getElementById("ib-reality-sni").value || "yahoo.com";
        const pbk = document.getElementById("ib-reality-pbk").value;
        const priv = document.getElementById("ib-reality-priv").value;
        const shortIdsInput = document.getElementById("ib-reality-shortids").value;
        const shortIds = shortIdsInput ? shortIdsInput.split(",").map(s => s.trim()).filter(Boolean) : [];
        const fp = document.getElementById("ib-reality-fp").value || "chrome";
        const spx = document.getElementById("ib-reality-spx").value || "/";
        
        const maxTimeDiffInput = document.getElementById("ib-reality-max-time-diff").value.trim();
        
        streamSettings.realitySettings = {
            show: false,
            dest: dest,
            serverNames: [sni],
            privateKey: priv,
            publicKey: pbk,
            shortIds: shortIds.length ? shortIds : ["8f9c2d1b"],
            fingerprint: fp,
            spiderX: spx
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
        const fp = document.getElementById("ib-tls-fp").value || "chrome";
        const minVer = document.getElementById("ib-tls-min-ver").value || "1.3";
        const maxVer = document.getElementById("ib-tls-max-ver").value || "1.3";
        
        streamSettings.tlsSettings = {
            serverName: sni,
            allowInsecure: allowInsecure,
            alpn: alpn,
            fingerprint: fp,
            minVersion: minVer,
            maxVersion: maxVer,
            certificates: []
        };
    }
}

// Populates Xray security form fields
export function populateXraySecuritySettings(security, streamSettings) {
    if (security === "reality") {
        const rs = streamSettings.realitySettings || {};
        document.getElementById("ib-reality-dest").value = rs.dest || "yahoo.com:443";
        document.getElementById("ib-reality-sni").value = (rs.serverNames && rs.serverNames[0]) || "yahoo.com";
        document.getElementById("ib-reality-pbk").value = rs.publicKey || "";
        document.getElementById("ib-reality-priv").value = rs.privateKey || "";
        document.getElementById("ib-reality-shortids").value = (rs.shortIds || []).join(", ");
        document.getElementById("ib-reality-fp").value = rs.fingerprint || "chrome";
        document.getElementById("ib-reality-spx").value = rs.spiderX || "/";
        const mtd = rs.maxTimeDiff || rs.max_time_difference || "";
        document.getElementById("ib-reality-max-time-diff").value = (mtd === "0s" || mtd === "0") ? "" : mtd;
    } else if (security === "tls") {
        const ts = streamSettings.tlsSettings || {};
        document.getElementById("ib-tls-sni").value = ts.serverName || "";
        document.getElementById("ib-tls-alpn").value = (ts.alpn || []).join(", ");
        document.getElementById("ib-tls-insecure").checked = ts.allowInsecure || false;
        document.getElementById("ib-tls-fp").value = ts.fingerprint || "chrome";
        document.getElementById("ib-tls-min-ver").value = ts.minVersion || "1.3";
        document.getElementById("ib-tls-max-ver").value = ts.maxVersion || "1.3";
    }
}

// Compiles transport settings (TCP, WS, gRPC, HTTP/2, mKCP)
export function compileXrayTransportSettings(network, streamSettings) {
    if (network === "tcp") {
        const tcpType = document.getElementById("ib-tcp-type").value;
        if (tcpType === "http") {
            const pathInput = document.getElementById("ib-tcp-path").value || "/";
            const paths = pathInput.split(",").map(s => s.trim()).filter(Boolean);
            const hostInput = document.getElementById("ib-tcp-host").value || "";
            const hosts = hostInput.split(",").map(s => s.trim()).filter(Boolean);
            
            streamSettings.tcpSettings = {
                header: {
                    type: "http",
                    request: {
                        version: "1.1",
                        method: "GET",
                        path: paths.length ? paths : ["/"],
                        headers: {
                            Host: hosts.length ? hosts : ["mydomain.com"]
                        }
                    }
                }
            };
        } else {
            streamSettings.tcpSettings = {
                header: { type: "none" }
            };
        }
    } else if (network === "ws") {
        const path = document.getElementById("ib-ws-path").value || "/";
        const host = document.getElementById("ib-ws-host").value || "";
        const ed = parseInt(document.getElementById("ib-ws-ed").value) || 0;
        streamSettings.wsSettings = {
            path: path,
            headers: host ? { Host: host } : {}
        };
        if (ed > 0) {
            streamSettings.wsSettings.maxEarlyDataHeaderLength = ed;
        }
    } else if (network === "grpc") {
        const serviceName = document.getElementById("ib-grpc-service").value || "grpc";
        const multiMode = document.getElementById("ib-grpc-multi-mode").checked;
        streamSettings.grpcSettings = {
            serviceName: serviceName,
            multiMode: multiMode
        };
    } else if (network === "h2") {
        const path = document.getElementById("ib-h2-path").value || "/";
        const hostInput = document.getElementById("ib-h2-host").value || "";
        const hosts = hostInput.split(",").map(s => s.trim()).filter(Boolean);
        
        streamSettings.httpSettings = {
            path: path,
            host: hosts
        };
    } else if (network === "mkcp") {
        const headerType = document.getElementById("ib-mkcp-header").value || "none";
        const seed = document.getElementById("ib-mkcp-seed").value || "";
        const congestion = document.getElementById("ib-mkcp-congestion").checked;
        
        streamSettings.kcpSettings = {
            header: { type: headerType },
            seed: seed,
            congestion: congestion
        };
    } else if (network === "httpupgrade") {
        const path = document.getElementById("ib-httpupgrade-path").value || "/";
        const host = document.getElementById("ib-httpupgrade-host").value || "";
        streamSettings.httpupgradeSettings = {
            path: path,
            host: host || undefined
        };
    } else if (network === "xhttp") {
        const path = document.getElementById("ib-xhttp-path").value || "/";
        const host = document.getElementById("ib-xhttp-host").value || "";
        const mode = document.getElementById("ib-xhttp-mode").value || "auto";
        const extraStr = document.getElementById("ib-xhttp-extra").value || "";
        const settings = {
            path: path,
            host: host || undefined,
            mode: mode
        };
        if (extraStr) {
            try {
                const extra = JSON.parse(extraStr);
                Object.assign(settings, extra);
            } catch(e) { /* ignore invalid JSON */ }
        }
        streamSettings.xhttpSettings = settings;
    }
}

// Populates transport form fields
export function populateXrayTransportSettings(network, streamSettings) {
    if (network === "tcp") {
        const ts = streamSettings.tcpSettings || {};
        const header = ts.header || {};
        if (header.type === "http") {
            document.getElementById("ib-tcp-type").value = "http";
            const req = header.request || {};
            const paths = req.path || ["/"];
            document.getElementById("ib-tcp-path").value = paths.join(", ");
            const headers = req.headers || {};
            const hosts = headers.Host || [];
            document.getElementById("ib-tcp-host").value = hosts.join(", ");
        } else {
            document.getElementById("ib-tcp-type").value = "none";
        }
    } else if (network === "ws") {
        const ws = streamSettings.wsSettings || {};
        document.getElementById("ib-ws-path").value = ws.path || "/";
        const headers = ws.headers || {};
        document.getElementById("ib-ws-host").value = headers.Host || "";
        document.getElementById("ib-ws-ed").value = ws.maxEarlyDataHeaderLength || 0;
    } else if (network === "grpc") {
        const gs = streamSettings.grpcSettings || {};
        document.getElementById("ib-grpc-service").value = gs.serviceName || "grpc";
        document.getElementById("ib-grpc-multi-mode").checked = gs.multiMode || false;
    } else if (network === "h2") {
        const hs = streamSettings.httpSettings || {};
        document.getElementById("ib-h2-path").value = hs.path || "/";
        document.getElementById("ib-h2-host").value = (hs.host || []).join(", ");
    } else if (network === "mkcp") {
        const ks = streamSettings.kcpSettings || {};
        const header = ks.header || {};
        document.getElementById("ib-mkcp-header").value = header.type || "none";
        document.getElementById("ib-mkcp-seed").value = ks.seed || "";
        document.getElementById("ib-mkcp-congestion").checked = ks.congestion || false;
    } else if (network === "httpupgrade") {
        const hu = streamSettings.httpupgradeSettings || {};
        document.getElementById("ib-httpupgrade-path").value = hu.path || "/";
        document.getElementById("ib-httpupgrade-host").value = hu.host || "";
    } else if (network === "xhttp") {
        const xh = streamSettings.xhttpSettings || {};
        document.getElementById("ib-xhttp-path").value = xh.path || "/";
        document.getElementById("ib-xhttp-host").value = xh.host || "";
        document.getElementById("ib-xhttp-mode").value = xh.mode || "auto";
        // Reconstruct extra JSON from unknown keys
        const knownKeys = ["path", "host", "mode"];
        const extra = {};
        for (const key of Object.keys(xh)) {
            if (!knownKeys.includes(key)) extra[key] = xh[key];
        }
        document.getElementById("ib-xhttp-extra").value = Object.keys(extra).length ? JSON.stringify(extra, null, 2) : "";
    }
}
