import { apiFetch } from "../../../../api.js";
import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { validateOutboundForm } from "../validation.js";

export function bindTesterListener() {
    const testObBtn = document.getElementById("ob-test-btn");
    if (!testObBtn) return;

    testObBtn.addEventListener("click", async () => {
        if (!validateOutboundForm()) return;
        
        const icon = testObBtn.querySelector("i");
        const btnText = testObBtn.querySelector("span");
        const originalClass = icon.className;
        const originalText = btnText.innerText;
        
        icon.className = "fa-solid fa-spinner fa-spin";
        btnText.innerText = t("routing_testing", "Проверка...");
        testObBtn.disabled = true;
        
        try {
            const protocol = document.getElementById("ob-protocol").value;
            const test_type = document.getElementById("ob-test-type").value;
            const address = document.getElementById("ob-address").value.trim();
            const rawPort = document.getElementById("ob-port").value.trim();
            const port = (rawPort.includes("-") || rawPort.includes(",")) ? rawPort : (parseInt(rawPort) || 443);
            const password = document.getElementById("ob-password").value.trim();
            
            if (!address || (!rawPort.includes("-") && !rawPort.includes(",") && isNaN(parseInt(rawPort)))) {
                showToast(t("routing_err_host_port", "Укажите адрес и порт сервера прокси"), "warning");
                return;
            }
            
            let settings = {};
            let streamSettings = {};
            
            if (protocol === "shadowsocks") {
                const method = document.getElementById("ob-ss-method").value;
                settings = {
                    "servers": [{ "address": address, "port": port, "password": password, "method": method }]
                };
            } else if (protocol === "vless") {
                const flow = document.getElementById("ob-flow").value;
                const encryption = document.getElementById("ob-encryption").value.trim() || "none";
                settings = {
                    "vnext": [{
                        "address": address,
                        "port": port,
                        "users": [{ "id": password, "encryption": encryption, "flow": flow }]
                    }]
                };
                
                const security = document.getElementById("ob-security").value;
                const sni = document.getElementById("ob-sni").value.trim();
                streamSettings = {
                    "network": "tcp",
                    "security": security
                };
                
                if (security === "tls") {
                    const alpnInput = document.getElementById("ob-alpn").value.trim();
                    const alpn = alpnInput ? alpnInput.split(",").map(s => s.trim()).filter(Boolean) : [];
                    const allowInsecure = document.getElementById("ob-allow-insecure").checked;
                    streamSettings.tlsSettings = {
                        "serverName": sni,
                        "allowInsecure": allowInsecure
                    };
                    const pinnedShaInput = document.getElementById("ob-pinned-sha256").value.trim();
                    if (pinnedShaInput) {
                        const pins = pinnedShaInput.split(/[,~]+/)
                            .map(s => s.replace(/:/g, "").trim().toLowerCase())
                            .filter(Boolean);
                        if (pins.length > 0) {
                            streamSettings.tlsSettings.pinnedPeerCertSha256 = pins.join("~");
                        }
                    }
                    if (alpn.length > 0) {
                        streamSettings.tlsSettings.alpn = alpn;
                    }
                } else if (security === "reality") {
                    const pbk = document.getElementById("ob-pbk").value.trim();
                    const shortId = document.getElementById("ob-shortid").value.trim();
                    const fp = document.getElementById("ob-fingerprint").value;
                    const spx = document.getElementById("ob-spx") ? document.getElementById("ob-spx").value.trim() : "";
                    streamSettings.realitySettings = {
                        "serverName": sni,
                        "publicKey": pbk,
                        "shortId": shortId,
                        "fingerprint": fp
                    };
                    if (spx) {
                        streamSettings.realitySettings.spiderX = spx;
                    }
                }
            } else if (protocol === "hysteria" || protocol === "hysteria2") {
                settings = { "version": 2, "address": address, "port": port };
                
                const sni = document.getElementById("ob-sni").value.trim();
                const alpnInput = document.getElementById("ob-alpn").value.trim() || "h3";
                const alpn = alpnInput.split(",").map(s => s.trim()).filter(Boolean);
                const allowInsecure = document.getElementById("ob-allow-insecure").checked;
                
                const upMbps = parseInt(document.getElementById("ob-up-mbps").value);
                const downMbps = parseInt(document.getElementById("ob-down-mbps").value);
                
                let hysteriaSettings = { "version": 2, "auth": password };
                if (!isNaN(upMbps) && upMbps > 0) hysteriaSettings.up = `${upMbps} mbps`;
                if (!isNaN(downMbps) && downMbps > 0) hysteriaSettings.down = `${downMbps} mbps`;
                
                const obfsType = document.getElementById("ob-hysteria-obfs").value;
                if (obfsType) {
                    hysteriaSettings.obfs = obfsType;
                    hysteriaSettings.obfs_type = obfsType;
                    const obfsPwd = document.getElementById("ob-hysteria-obfs-password").value.trim();
                    if (obfsPwd) {
                        hysteriaSettings.obfsPassword = obfsPwd;
                        hysteriaSettings.obfs_password = obfsPwd;
                    }
                }
                
                const pinnedShaInput = document.getElementById("ob-pinned-sha256").value.trim();
                let tlsSettings = {
                    "serverName": sni,
                    "alpn": alpn,
                    "allowInsecure": allowInsecure
                };
                if (pinnedShaInput) {
                    const pins = pinnedShaInput.split(/[,~]+/)
                        .map(s => s.replace(/:/g, "").trim().toLowerCase())
                        .filter(Boolean);
                    if (pins.length > 0) {
                        tlsSettings.pinnedPeerCertSha256 = pins.join("~");
                    }
                }
                
                streamSettings = {
                    "network": "hysteria",
                    "security": "tls",
                    "tlsSettings": tlsSettings,
                    "hysteriaSettings": hysteriaSettings
                };
            } else if (protocol === "socks" || protocol === "http") {
                const username = document.getElementById("ob-username").value.trim();
                const users = username || password ? [{"user": username, "pass": password}] : [];
                settings = {
                    "servers": [{ "address": address, "port": port, "users": users }]
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
            icon.className = originalClass;
            btnText.innerText = originalText;
            testObBtn.disabled = false;
        }
    });
}
