import { apiFetch } from "../../../../api.js";
import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { loadOutbounds } from "../../../routing-outbounds.js";
import { validateOutboundForm } from "../validation.js";
import { getCurrentOutboundValues } from "../modal_manager.js";

export function bindSubmitListener() {
    const outboundForm = document.getElementById("outbound-form");
    const submitBtn = document.getElementById("ob-submit-btn");

    async function handleSave(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        if (!validateOutboundForm()) {
            return;
        }

        const id = document.getElementById("ob-id").value;
        const vals = getCurrentOutboundValues() || {};
        
        // Read top fields
        const remark = (document.getElementById("ob-remark") ? document.getElementById("ob-remark").value.trim() : vals.remark) || "Outbound";
        const protocol = (document.getElementById("ob-protocol") ? document.getElementById("ob-protocol").value : vals.protocol) || "vless";
        const tag = (document.getElementById("ob-tag") ? document.getElementById("ob-tag").value.trim() : vals.tag) || `${protocol}-${Math.floor(Math.random()*1000)}`;
        const enable = (document.getElementById("ob-enable") ? document.getElementById("ob-enable").checked : (vals.enable !== false)) ? 1 : 0;
        
        const host = (document.getElementById("ob-host") ? document.getElementById("ob-host").value.trim() : vals.host) || "";
        const port = (document.getElementById("ob-port") ? (parseInt(document.getElementById("ob-port").value) || 443) : (parseInt(vals.port) || 443));
        const uuid = (document.getElementById("ob-uuid") ? document.getElementById("ob-uuid").value.trim() : (vals.uuid || vals.password)) || "";
        const password = (document.getElementById("ob-password") ? document.getElementById("ob-password").value.trim() : (vals.password || vals.uuid)) || "";
        
        let settings = {};
        let streamSettings = {};

        if (protocol === "freedom" || protocol === "direct") {
            const domainStrategy = document.getElementById("ob-domain-strategy") ? document.getElementById("ob-domain-strategy").value : (vals.domainStrategy || "AsIs");
            settings = { domainStrategy };
        } else if (protocol === "blackhole" || protocol === "block") {
            settings = { response: { type: "none" } };
        } else if (protocol === "wireguard") {
            const secretKey = (document.getElementById("ob-private-key") ? document.getElementById("ob-private-key").value.trim() : vals.privateKey) || "";
            const peerPublicKey = (document.getElementById("ob-peer-public-key") ? document.getElementById("ob-peer-public-key").value.trim() : vals.peerPublicKey) || "";
            const localAddrRaw = (document.getElementById("ob-local-address") ? document.getElementById("ob-local-address").value.trim() : vals.localAddress) || "";
            const addressList = localAddrRaw ? localAddrRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
            const mtu = document.getElementById("ob-mtu") ? (parseInt(document.getElementById("ob-mtu").value) || 1420) : (parseInt(vals.mtu) || 1420);
            const reservedRaw = (document.getElementById("ob-reserved") ? document.getElementById("ob-reserved").value.trim() : vals.reserved) || "";
            const reserved = reservedRaw ? reservedRaw.split(",").map(s => parseInt(s.trim())).filter(x => !isNaN(x)) : [];

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
            const flow = document.getElementById("ob-flow") ? document.getElementById("ob-flow").value : (vals.flow || "");
            const encryption = (document.getElementById("ob-vless-encryption") ? document.getElementById("ob-vless-encryption").value.trim() : (vals.encryption || "none")) || "none";
            settings = {
                vnext: [{
                    address: host,
                    port: port,
                    users: [{
                        id: uuid || password,
                        encryption: encryption,
                        flow: flow
                    }]
                }]
            };

            const security = (document.getElementById("ob-security") ? document.getElementById("ob-security").value : (vals.security || "reality")) || "none";
            const network = (document.getElementById("ob-network") ? document.getElementById("ob-network").value : (vals.network || "tcp")) || "tcp";
            const sni = (document.getElementById("ob-sni") ? document.getElementById("ob-sni").value.trim() : vals.sni) || "";
            const fp = (document.getElementById("ob-fp") ? document.getElementById("ob-fp").value : (vals.fingerprint || "chrome")) || "chrome";
            const path = (document.getElementById("ob-path") ? document.getElementById("ob-path").value.trim() : vals.path) || "";
            const wsHost = (document.getElementById("ob-ws-host") ? document.getElementById("ob-ws-host").value.trim() : vals.wsHost) || "";
            const serviceName = (document.getElementById("ob-service-name") ? document.getElementById("ob-service-name").value.trim() : vals.serviceName) || "";

            streamSettings = {
                network: network,
                security: security
            };

            if (network === "ws" || network === "httpupgrade" || network === "xhttp") {
                streamSettings.wsSettings = {
                    path: path || "/",
                    headers: wsHost ? { Host: wsHost } : {}
                };
            } else if (network === "grpc") {
                streamSettings.grpcSettings = {
                    serviceName: serviceName || "grpc"
                };
            }

            if (security === "reality") {
                const pbk = (document.getElementById("ob-pbk") ? document.getElementById("ob-pbk").value.trim() : vals.publicKey) || "";
                const sid = (document.getElementById("ob-sid") ? document.getElementById("ob-sid").value.trim() : vals.shortId) || "";
                const spx = (document.getElementById("ob-spx") ? document.getElementById("ob-spx").value.trim() : (vals.spiderX || "/")) || "/";
                streamSettings.realitySettings = {
                    serverName: sni,
                    publicKey: pbk,
                    shortId: sid,
                    spiderX: spx,
                    fingerprint: fp
                };
            } else if (security === "tls") {
                const alpnRaw = (document.getElementById("ob-alpn") ? document.getElementById("ob-alpn").value.trim() : vals.alpn) || "";
                const allowInsecure = document.getElementById("ob-insecure") ? document.getElementById("ob-insecure").checked : Boolean(vals.allowInsecure);
                streamSettings.tlsSettings = {
                    serverName: sni,
                    alpn: alpnRaw ? alpnRaw.split(",").map(s => s.trim()) : ["h2", "http/1.1"],
                    allowInsecure: allowInsecure,
                    fingerprint: fp
                };
            }
        } else if (protocol === "hysteria2" || protocol === "hysteria") {
            const upMbps = document.getElementById("ob-up-mbps") ? (parseInt(document.getElementById("ob-up-mbps").value) || 100) : (parseInt(vals.upMbps) || 100);
            const downMbps = document.getElementById("ob-down-mbps") ? (parseInt(document.getElementById("ob-down-mbps").value) || 100) : (parseInt(vals.downMbps) || 100);
            const sni = (document.getElementById("ob-sni") ? document.getElementById("ob-sni").value.trim() : vals.sni) || "";
            const allowInsecure = document.getElementById("ob-insecure") ? document.getElementById("ob-insecure").checked : Boolean(vals.allowInsecure);
            const pinSha = (document.getElementById("ob-pin-sha256") ? document.getElementById("ob-pin-sha256").value.trim() : vals.pinnedPeerCertSha256) || "";
            const obfsType = (document.getElementById("ob-obfs-type") ? document.getElementById("ob-obfs-type").value : vals.obfs) || "";
            const obfsPassword = (document.getElementById("ob-obfs-password") ? document.getElementById("ob-obfs-password").value.trim() : vals.obfsPassword) || "";

            settings = {
                server: host,
                port: port,
                auth: password || uuid,
                up_mbps: upMbps,
                down_mbps: downMbps
            };

            if (obfsType === "salamander") {
                settings.obfs = {
                    type: "salamander",
                    salamander: { password: obfsPassword }
                };
            }

            streamSettings = {
                network: "hysteria",
                security: "tls",
                tlsSettings: {
                    serverName: sni,
                    allowInsecure: allowInsecure,
                    pinnedPeerCertSha256: pinSha
                }
            };
        } else if (protocol === "shadowsocks" || protocol === "ss") {
            const method = (document.getElementById("ob-method") ? document.getElementById("ob-method").value : (vals.method || "2022-blake3-aes-128-gcm")) || "2022-blake3-aes-128-gcm";
            settings = {
                servers: [{
                    address: host,
                    port: port,
                    password: password,
                    method: method
                }]
            };
        } else if (protocol === "trojan") {
            const sni = (document.getElementById("ob-sni") ? document.getElementById("ob-sni").value.trim() : vals.sni) || "";
            const allowInsecure = document.getElementById("ob-insecure") ? document.getElementById("ob-insecure").checked : Boolean(vals.allowInsecure);
            const fp = (document.getElementById("ob-fp") ? document.getElementById("ob-fp").value : (vals.fingerprint || "chrome")) || "chrome";

            settings = {
                servers: [{
                    address: host,
                    port: port,
                    password: password
                }]
            };
            streamSettings = {
                network: "tcp",
                security: "tls",
                tlsSettings: {
                    serverName: sni,
                    allowInsecure: allowInsecure,
                    fingerprint: fp
                }
            };
        } else if (protocol === "socks" || protocol === "socks5" || protocol === "http") {
            const user = (document.getElementById("ob-user") ? document.getElementById("ob-user").value.trim() : vals.user) || "";
            const pass = (document.getElementById("ob-pass") ? document.getElementById("ob-pass").value.trim() : vals.pass) || "";
            const users = user || pass ? [{ user, pass }] : [];
            settings = {
                servers: [{
                    address: host,
                    port: port,
                    users: users
                }]
            };
        } else if (protocol === "warp") {
            const secretKey = (document.getElementById("ob-private-key") ? document.getElementById("ob-private-key").value.trim() : vals.privateKey) || "";
            const peerPublicKey = (document.getElementById("ob-peer-public-key") ? document.getElementById("ob-peer-public-key").value.trim() : (vals.peerPublicKey || "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=")) || "";
            settings = {
                secretKey,
                address: ["172.16.0.2/32", "2606:4700:110:8f81:85b7:83c8:5087:dfc8/128"],
                peers: [{
                    publicKey: peerPublicKey,
                    endpoint: `${host || "162.159.192.1"}:${port || 2408}`
                }]
            };
        }

        // Attach fallback route and failover strategy if set
        const fallbackRoute = (document.getElementById("fallback_outbound") ? document.getElementById("fallback_outbound").value : vals.fallback_outbound) || "";
        const fallbackStrategy = (document.getElementById("fallback_strategy") ? document.getElementById("fallback_strategy").value : vals.fallback_strategy) || "priority";
        const healthCheckInt = parseInt(document.getElementById("health_check_interval") ? document.getElementById("health_check_interval").value : vals.health_check_interval) || 300;

        if (fallbackRoute) {
            settings.backup_outbounds = [fallbackRoute];
            settings.fallback_outbound = fallbackRoute;
            settings.fallback_strategy = fallbackStrategy;
            settings.health_check_interval = healthCheckInt;
        } else {
            delete settings.backup_outbounds;
            delete settings.fallback_outbound;
            delete settings.fallback_strategy;
            delete settings.health_check_interval;
        }

        const url = id ? `/api/routing/outbounds/update/${id}` : "/api/routing/outbounds/create";
        const res = await apiFetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ remark, protocol, tag, settings, streamSettings, enable })
        });
        
        if (res && res.success) {
            showToast(id ? t("routing_outbound_updated", "Исходящее подключение обновлено") : t("routing_outbound_created", "Исходящее подключение создано"));
            document.getElementById("outbound-modal").classList.remove("active");
            loadOutbounds();
        } else {
            showToast(res ? res.msg : "Error", "error");
        }
    }

    if (outboundForm) {
        outboundForm.addEventListener("submit", handleSave);
    }
    if (submitBtn) {
        submitBtn.addEventListener("click", handleSave);
    }
}
