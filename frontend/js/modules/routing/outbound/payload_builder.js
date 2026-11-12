function readElement(ids) {
    const list = Array.isArray(ids) ? ids : [ids];
    for (const id of list) {
        const el = document.getElementById(id);
        if (el) return el;
    }
    return null;
}

function readTrimmed(ids, fallback = "") {
    const el = readElement(ids);
    if (el) return (el.value || "").trim();
    return fallback == null ? "" : String(fallback).trim();
}

function readRawValue(ids, fallback = "") {
    const el = readElement(ids);
    if (el) return el.value ?? "";
    return fallback == null ? "" : String(fallback);
}

function readCheckbox(ids, fallback = false) {
    const el = readElement(ids);
    if (el) return Boolean(el.checked);
    return Boolean(fallback);
}

function parsePortValue(rawPort) {
    const portStr = String(rawPort ?? "").trim();
    if (!portStr) return 443;
    if (portStr.includes("-") || portStr.includes(",") || portStr.includes(":") || isNaN(Number(portStr))) {
        return portStr;
    }
    return parseInt(portStr, 10) || 443;
}

function buildStreamSettings(vals, defaults = {}) {
    const network = readRawValue(["ob-network"], vals.network || defaults.network || "tcp") || defaults.network || "tcp";
    const security = readRawValue(["ob-security"], vals.security || defaults.security || "none") || defaults.security || "none";
    const headerType = readRawValue(["ob-header-type"], vals.headerType || "");
    const path = readTrimmed(["ob-path"], vals.path);
    const wsHost = readTrimmed(["ob-ws-host"], vals.wsHost);
    const serviceName = readTrimmed(["ob-service-name"], vals.serviceName);
    const sni = readTrimmed(["ob-sni"], vals.sni);
    const fp = readRawValue(["ob-fp", "ob-fingerprint"], vals.fingerprint || "chrome") || "chrome";

    const streamSettings = {
        network,
        security
    };

    if (network === "tcp" && headerType === "http") {
        const tcpHeader = { type: "http" };
        if (path || wsHost) {
            tcpHeader.request = {
                path: [path || "/"],
                headers: wsHost ? { Host: [wsHost] } : {}
            };
        }
        streamSettings.tcpSettings = { header: tcpHeader };
    } else if (network === "ws") {
        streamSettings.wsSettings = {
            path: path || "/",
            headers: wsHost ? { Host: wsHost } : {}
        };
    } else if (network === "httpupgrade") {
        streamSettings.httpupgradeSettings = {
            path: path || "/",
            ...(wsHost ? { host: wsHost } : {})
        };
    } else if (network === "xhttp" || network === "splithttp") {
        const xhttpMode = readRawValue(["ob-xhttp-mode"], vals.xhttpMode || "auto") || "auto";
        streamSettings.xhttpSettings = {
            path: path || "/",
            ...(wsHost ? { host: wsHost } : {}),
            mode: xhttpMode
        };
    } else if (network === "grpc") {
        const multiMode = readCheckbox(["ob-grpc-multi-mode"], vals.multiMode);
        streamSettings.grpcSettings = {
            serviceName: serviceName || "grpc",
            ...(multiMode ? { multiMode: true } : {})
        };
    } else if (network === "h2" || network === "http") {
        streamSettings.httpSettings = {
            path: path || "/",
            ...(wsHost ? { host: [wsHost] } : {})
        };
    }

    if (security === "reality") {
        const pbk = readTrimmed(["ob-pbk"], vals.publicKey || vals.pbk);
        const sid = readTrimmed(["ob-sid", "ob-shortid"], vals.shortId || vals.sid);
        const spx = readTrimmed(["ob-spx"], vals.spiderX || "/") || "/";
        streamSettings.realitySettings = {
            serverName: sni,
            publicKey: pbk,
            shortId: sid,
            spiderX: spx,
            fingerprint: fp
        };
    } else if (security === "tls") {
        const alpnRaw = readTrimmed(["ob-alpn"], vals.alpn);
        const allowInsecure = readCheckbox(["ob-insecure", "ob-allow-insecure"], vals.allowInsecure);
        const tlsSettings = {
            serverName: sni,
            allowInsecure,
            fingerprint: fp
        };
        if (alpnRaw) {
            const alpnList = alpnRaw.split(",").map(s => s.trim()).filter(Boolean);
            if (alpnList.length > 0) {
                tlsSettings.alpn = alpnList;
            }
        }
        streamSettings.tlsSettings = tlsSettings;
    }

    return streamSettings;
}

/**
 * Builds outbound settings and streamSettings payloads directly from form inputs / cached values.
 * Shared across outbound save and outbound connectivity testing.
 */
export function buildOutboundPayload(vals = {}) {
    const protocol = (readRawValue(["ob-protocol"], vals.protocol || "vless") || "vless").toLowerCase();
    const host = readTrimmed(["ob-host", "ob-address"], vals.host);
    const rawPort = readTrimmed(["ob-port"], vals.port || 443);
    const port = parsePortValue(rawPort);
    const uuid = readTrimmed(["ob-uuid"], vals.uuid || vals.password);
    const password = readTrimmed(["ob-password"], vals.password || vals.uuid);

    let settings = {};
    let streamSettings = {};

    if (protocol === "freedom" || protocol === "direct") {
        const domainStrategy = readRawValue(["ob-domain-strategy"], vals.domainStrategy || "AsIs") || "AsIs";
        settings = { domainStrategy };
    } else if (protocol === "blackhole" || protocol === "block") {
        settings = { response: { type: "none" } };
    } else if (protocol === "wireguard") {
        const secretKey = readTrimmed(["ob-private-key"], vals.privateKey);
        const peerPublicKey = readTrimmed(["ob-peer-public-key"], vals.peerPublicKey);
        const localAddrRaw = readTrimmed(["ob-local-address"], vals.localAddress);
        const addressList = localAddrRaw ? localAddrRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
        const mtu = parseInt(readTrimmed(["ob-mtu"], vals.mtu || 1420), 10) || 1420;
        const reservedRaw = readTrimmed(["ob-reserved"], vals.reserved);
        const reserved = reservedRaw ? reservedRaw.split(",").map(s => parseInt(s.trim(), 10)).filter(x => !isNaN(x)) : [];

        settings = {
            secretKey,
            address: addressList,
            peers: [{
                publicKey: peerPublicKey,
                endpoint: host ? `${host}:${port}` : ""
            }],
            mtu
        };
        if (reserved.length > 0) settings.reserved = reserved;
    } else if (protocol === "vless") {
        const flow = readRawValue(["ob-flow"], vals.flow || "");
        const encryption = readTrimmed(["ob-vless-encryption"], vals.encryption || "none") || "none";
        settings = {
            vnext: [{
                address: host,
                port,
                users: [{
                    id: uuid || password,
                    encryption,
                    flow
                }]
            }]
        };
        streamSettings = buildStreamSettings(vals, { network: "tcp", security: "reality" });
    } else if (protocol === "vmess") {
        const alterId = parseInt(readTrimmed(["ob-alterid"], vals.alterId || 0), 10) || 0;
        settings = {
            vnext: [{
                address: host,
                port,
                users: [{
                    id: uuid || password,
                    alterId,
                    security: "auto"
                }]
            }]
        };
        streamSettings = buildStreamSettings(vals, { network: "ws", security: "tls" });
    } else if (protocol === "trojan") {
        settings = {
            servers: [{
                address: host,
                port,
                password: password || uuid
            }]
        };
        streamSettings = buildStreamSettings(vals, { network: "tcp", security: "tls" });
    } else if (protocol === "hysteria2" || protocol === "hysteria") {
        const upMbps = parseInt(readTrimmed(["ob-up-mbps"], vals.upMbps || 100), 10) || 100;
        const downMbps = parseInt(readTrimmed(["ob-down-mbps"], vals.downMbps || 100), 10) || 100;
        const portHopping = readTrimmed(["ob-port-hopping"], vals.portHopping || vals.port_hopping);
        const sni = readTrimmed(["ob-sni"], vals.sni);
        const allowInsecure = readCheckbox(["ob-insecure", "ob-allow-insecure"], vals.allowInsecure);
        const pinSha = readTrimmed(["ob-pin-sha256", "ob-pinned-sha256"], vals.pinnedPeerCertSha256);
        const obfsType = readRawValue(["ob-obfs-type", "ob-hysteria-obfs"], vals.obfs || "");
        const obfsPassword = readTrimmed(["ob-obfs-password", "ob-hysteria-obfs-password"], vals.obfsPassword);

        settings = {
            server: host,
            address: host,
            port,
            password: password || uuid,
            auth: password || uuid,
            up_mbps: upMbps,
            down_mbps: downMbps
        };

        if (portHopping) {
            settings.port_hopping = portHopping;
        }

        if (obfsType === "salamander") {
            settings.obfs = {
                type: "salamander",
                password: obfsPassword
            };
            settings.obfs_type = "salamander";
            settings.obfs_password = obfsPassword;
        }

        const alpnRaw = readTrimmed(["ob-alpn"], vals.alpn);
        const tlsObj = {
            serverName: sni,
            allowInsecure,
            pinnedPeerCertSha256: pinSha
        };
        if (alpnRaw) {
            const alpnList = alpnRaw.split(",").map(s => s.trim()).filter(Boolean);
            if (alpnList.length > 0) tlsObj.alpn = alpnList;
        }
        streamSettings = {
            network: "hysteria",
            security: "tls",
            tlsSettings: tlsObj
        };
    } else if (protocol === "tuic") {
        const sni = readTrimmed(["ob-sni"], vals.sni);
        const alpnRaw = readTrimmed(["ob-alpn"], vals.alpn || "h3");
        const allowInsecure = readCheckbox(["ob-insecure", "ob-allow-insecure"], vals.allowInsecure);
        const congestionControl = readRawValue(["ob-tuic-cc"], vals.congestionControl || "bbr") || "bbr";
        const udpRelayMode = readRawValue(["ob-tuic-udp-relay"], vals.udpRelayMode || "native") || "native";
        const zeroRttHandshake = readCheckbox(["ob-tuic-zero-rtt"], vals.zeroRttHandshake);
        settings = {
            server: host,
            host,
            port,
            uuid: uuid || password,
            password,
            congestionControl,
            udpRelayMode,
            zeroRttHandshake
        };
        const alpnList = alpnRaw ? alpnRaw.split(",").map(s => s.trim()).filter(Boolean) : ["h3"];
        streamSettings = {
            network: "quic",
            security: "tls",
            tlsSettings: {
                serverName: sni,
                allowInsecure,
                alpn: alpnList
            }
        };
    } else if (protocol === "shadowtls") {
        const version = parseInt(readRawValue(["ob-shadowtls-version"], vals.shadowTlsVersion || "3"), 10) || 3;
        const sni = readTrimmed(["ob-sni"], vals.sni);
        const fp = readRawValue(["ob-fp"], vals.fingerprint || "chrome") || "chrome";
        settings = {
            server: host,
            host,
            port,
            password,
            shadowTlsVersion: version,
            sni,
            fingerprint: fp
        };
        streamSettings = {
            network: "tcp",
            security: "tls",
            tlsSettings: {
                serverName: sni,
                fingerprint: fp
            }
        };
    } else if (protocol === "shadowsocks" || protocol === "ss") {
        const method = readRawValue(["ob-method", "ob-ss-method"], vals.method || "2022-blake3-aes-128-gcm") || "2022-blake3-aes-128-gcm";
        settings = {
            servers: [{
                address: host,
                port,
                password,
                method
            }]
        };
    } else if (protocol === "socks" || protocol === "socks5" || protocol === "http") {
        const user = readTrimmed(["ob-user", "ob-username"], vals.user);
        const pass = readTrimmed(["ob-pass", "ob-password"], vals.pass || vals.password);
        const users = user || pass ? [{ user, pass }] : [];
        settings = {
            servers: [{
                address: host,
                port,
                users
            }]
        };
    } else if (protocol === "warp") {
        const secretKey = readTrimmed(["ob-private-key"], vals.privateKey);
        const peerPublicKey = readTrimmed(["ob-peer-public-key"], vals.peerPublicKey || "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=") || "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=";
        settings = {
            secretKey,
            address: ["172.16.0.2/32", "2606:4700:110:8f81:85b7:83c8:5087:dfc8/128"],
            peers: [{
                publicKey: peerPublicKey,
                endpoint: `${host || "162.159.192.1"}:${port || 2408}`
            }]
        };
    }

    return {
        protocol,
        host,
        rawPort,
        port,
        settings,
        streamSettings
    };
}
