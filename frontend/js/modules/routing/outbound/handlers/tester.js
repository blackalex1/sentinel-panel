import { apiFetch } from "../../../../api.js";
import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { validateOutboundForm } from "../validation.js";
import { getCurrentOutboundValues } from "../modal_manager.js";

export function bindTesterListener() {
    const testObBtn = document.getElementById("ob-test-btn");
    if (!testObBtn) return;

    testObBtn.addEventListener("click", async () => {
        if (!validateOutboundForm()) return;
        
        const icon = testObBtn.querySelector("i");
        const btnText = testObBtn.querySelector("span");
        const originalClass = icon ? icon.className : "";
        const originalText = btnText ? btnText.innerText : "";
        
        if (icon) icon.className = "fa-solid fa-spinner fa-spin";
        if (btnText) btnText.innerText = t("routing_testing", "Проверка...");
        testObBtn.disabled = true;
        
        try {
            const vals = getCurrentOutboundValues() || {};
            const protocol = (document.getElementById("ob-protocol") ? document.getElementById("ob-protocol").value : vals.protocol) || "vless";
            
            const testTypeEl = document.getElementById("ob-test-type");
            const test_type = testTypeEl ? testTypeEl.value : "http";
            
            const host = (document.getElementById("ob-host") ? document.getElementById("ob-host").value.trim() : (document.getElementById("ob-address") ? document.getElementById("ob-address").value.trim() : vals.host)) || "";
            const rawPort = document.getElementById("ob-port") ? document.getElementById("ob-port").value.trim() : String(vals.port || 443);
            const port = (rawPort.includes("-") || rawPort.includes(",") || rawPort.includes(":") || isNaN(Number(rawPort))) ? rawPort : (parseInt(rawPort) || 443);
            const uuid = (document.getElementById("ob-uuid") ? document.getElementById("ob-uuid").value.trim() : (vals.uuid || vals.password)) || "";
            const password = (document.getElementById("ob-password") ? document.getElementById("ob-password").value.trim() : (vals.password || vals.uuid)) || "";
            
            if (protocol !== "freedom" && protocol !== "direct" && protocol !== "blackhole" && protocol !== "block" && protocol !== "warp") {
                if (!host || (!String(rawPort).includes("-") && !String(rawPort).includes(",") && isNaN(parseInt(rawPort)))) {
                    showToast(t("routing_err_host_port", "Укажите адрес и порт сервера прокси"), "warning");
                    return;
                }
            }
            
            let settings = {};
            let streamSettings = {};
            
            if (protocol === "freedom" || protocol === "direct") {
                const domainStrategy = document.getElementById("ob-domain-strategy") ? document.getElementById("ob-domain-strategy").value : (vals.domainStrategy || "AsIs");
                settings = { domainStrategy };
            } else if (protocol === "blackhole" || protocol === "block") {
                settings = { response: { type: "none" } };
            } else if (protocol === "shadowsocks" || protocol === "ss") {
                const method = (document.getElementById("ob-method") ? document.getElementById("ob-method").value : (document.getElementById("ob-ss-method") ? document.getElementById("ob-ss-method").value : (vals.method || "2022-blake3-aes-128-gcm"))) || "2022-blake3-aes-128-gcm";
                settings = {
                    servers: [{ address: host, port: port, password: password, method: method }]
                };
            } else if (protocol === "vless") {
                const flow = document.getElementById("ob-flow") ? document.getElementById("ob-flow").value : (vals.flow || "");
                const encryption = (document.getElementById("ob-vless-encryption") ? document.getElementById("ob-vless-encryption").value.trim() : (vals.encryption || "none")) || "none";
                settings = {
                    vnext: [{
                        address: host,
                        port: port,
                        users: [{ id: uuid || password, encryption: encryption, flow: flow }]
                    }]
                };
                
                const security = (document.getElementById("ob-security") ? document.getElementById("ob-security").value : (vals.security || "reality")) || "none";
                const network = (document.getElementById("ob-network") ? document.getElementById("ob-network").value : (vals.network || "tcp")) || "tcp";
                const sni = (document.getElementById("ob-sni") ? document.getElementById("ob-sni").value.trim() : vals.sni) || "";
                const fp = (document.getElementById("ob-fp") ? document.getElementById("ob-fp").value : (document.getElementById("ob-fingerprint") ? document.getElementById("ob-fingerprint").value : (vals.fingerprint || "chrome"))) || "chrome";
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
                    const pbk = (document.getElementById("ob-pbk") ? document.getElementById("ob-pbk").value.trim() : (vals.publicKey || vals.pbk)) || "";
                    const sid = (document.getElementById("ob-sid") ? document.getElementById("ob-sid").value.trim() : (document.getElementById("ob-shortid") ? document.getElementById("ob-shortid").value.trim() : (vals.shortId || vals.sid))) || "";
                    const spx = (document.getElementById("ob-spx") ? document.getElementById("ob-spx").value.trim() : (vals.spiderX || "/")) || "/";
                    streamSettings.realitySettings = {
                        serverName: sni,
                        publicKey: pbk,
                        shortId: sid,
                        spiderX: spx,
                        fingerprint: fp
                    };
                } else if (security === "tls") {
                    const alpnInput = document.getElementById("ob-alpn") ? document.getElementById("ob-alpn").value.trim() : (vals.alpn || "");
                    const alpn = alpnInput ? alpnInput.split(",").map(s => s.trim()).filter(Boolean) : ["h2", "http/1.1"];
                    const allowInsecure = document.getElementById("ob-insecure") ? document.getElementById("ob-insecure").checked : (document.getElementById("ob-allow-insecure") ? document.getElementById("ob-allow-insecure").checked : Boolean(vals.allowInsecure));
                    streamSettings.tlsSettings = {
                        serverName: sni,
                        alpn: alpn,
                        allowInsecure: allowInsecure,
                        fingerprint: fp
                    };
                }
            } else if (protocol === "hysteria" || protocol === "hysteria2") {
                const upMbps = document.getElementById("ob-up-mbps") ? (parseInt(document.getElementById("ob-up-mbps").value) || 100) : (parseInt(vals.upMbps) || 100);
                const downMbps = document.getElementById("ob-down-mbps") ? (parseInt(document.getElementById("ob-down-mbps").value) || 100) : (parseInt(vals.downMbps) || 100);
                const sni = (document.getElementById("ob-sni") ? document.getElementById("ob-sni").value.trim() : vals.sni) || "";
                const allowInsecure = document.getElementById("ob-insecure") ? document.getElementById("ob-insecure").checked : (document.getElementById("ob-allow-insecure") ? document.getElementById("ob-allow-insecure").checked : Boolean(vals.allowInsecure));
                const pinSha = (document.getElementById("ob-pin-sha256") ? document.getElementById("ob-pin-sha256").value.trim() : (document.getElementById("ob-pinned-sha256") ? document.getElementById("ob-pinned-sha256").value.trim() : vals.pinnedPeerCertSha256)) || "";
                const obfsType = (document.getElementById("ob-obfs-type") ? document.getElementById("ob-obfs-type").value : (document.getElementById("ob-hysteria-obfs") ? document.getElementById("ob-hysteria-obfs").value : (vals.obfs || ""))) || "";
                const obfsPassword = (document.getElementById("ob-obfs-password") ? document.getElementById("ob-obfs-password").value.trim() : (document.getElementById("ob-hysteria-obfs-password") ? document.getElementById("ob-hysteria-obfs-password").value.trim() : (vals.obfsPassword || ""))) || "";

                settings = {
                    server: host,
                    address: host,
                    port: port,
                    password: password || uuid,
                    auth: password || uuid,
                    up_mbps: upMbps,
                    down_mbps: downMbps
                };

                if (obfsType === "salamander") {
                    settings.obfs = {
                        type: "salamander",
                        password: obfsPassword
                    };
                    settings.obfs_type = "salamander";
                    settings.obfs_password = obfsPassword;
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
            } else if (protocol === "trojan") {
                const sni = (document.getElementById("ob-sni") ? document.getElementById("ob-sni").value.trim() : vals.sni) || "";
                const allowInsecure = document.getElementById("ob-insecure") ? document.getElementById("ob-insecure").checked : (document.getElementById("ob-allow-insecure") ? document.getElementById("ob-allow-insecure").checked : Boolean(vals.allowInsecure));
                const fp = (document.getElementById("ob-fp") ? document.getElementById("ob-fp").value : (vals.fingerprint || "chrome")) || "chrome";

                settings = {
                    servers: [{
                        address: host,
                        port: port,
                        password: password || uuid
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
                const user = (document.getElementById("ob-user") ? document.getElementById("ob-user").value.trim() : (document.getElementById("ob-username") ? document.getElementById("ob-username").value.trim() : (vals.user || ""))) || "";
                const pass = (document.getElementById("ob-pass") ? document.getElementById("ob-pass").value.trim() : (document.getElementById("ob-password") ? document.getElementById("ob-password").value.trim() : (vals.pass || vals.password || ""))) || "";
                const users = user || pass ? [{ user, pass }] : [];
                settings = {
                    servers: [{ address: host, port: port, users: users }]
                };
            }
            
            const res = await apiFetch("/api/routing/outbounds/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ protocol, settings, streamSettings, test_type })
            });
            
            if (res && res.success) {
                showToast(t("routing_test_success", "Соединение успешно!") + ` (${res.ping} ms)`);
            } else {
                showToast(res ? res.msg : t("routing_toast_connection_error", "Ошибка соединения"), "error");
            }
        } catch (err) {
            showToast("Error: " + err.message, "error");
        } finally {
            if (icon) icon.className = originalClass;
            if (btnText) btnText.innerText = originalText;
            testObBtn.disabled = false;
        }
    });
}
