import { apiFetch } from "../../../../api.js";
import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { loadOutbounds } from "../../../routing-outbounds.js";
import { validateOutboundForm } from "../validation.js";

export function bindSubmitListener() {
    const outboundForm = document.getElementById("outbound-form");
    if (!outboundForm) return;

    outboundForm.querySelectorAll("input, select, textarea").forEach(el => {
        el.addEventListener("input", () => {
            el.classList.remove("input-invalid");
        });
        el.addEventListener("change", () => {
            el.classList.remove("input-invalid");
        });
    });

    outboundForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        if (!validateOutboundForm()) {
            return;
        }
        
        const id = document.getElementById("ob-id").value;
        const remark = document.getElementById("ob-remark").value.trim();
        const protocol = document.getElementById("ob-protocol").value;
        const tag = document.getElementById("ob-tag").value.trim();
        const enable = document.getElementById("ob-enable").checked ? 1 : 0;
        
        // Prepare settings JSON
        let settings = {};
        let streamSettings = {};
        
        if (protocol === "wireguard") {
            const privateKey = document.getElementById("ob-wg-private-key").value.trim();
            const addressesInput = document.getElementById("ob-wg-addresses").value.trim();
            const addressList = addressesInput ? addressesInput.split(",").map(s => s.trim()).filter(Boolean) : [];
            
            const reservedInput = document.getElementById("ob-wg-reserved").value.trim();
            let reserved = [];
            if (reservedInput) {
                reserved = reservedInput.split(",").map(s => parseInt(s.trim())).filter(x => !isNaN(x));
            }
            
            const peerPublicKey = document.getElementById("ob-wg-peer-public-key").value.trim();
            const peerEndpoint = document.getElementById("ob-wg-endpoint").value.trim();
            
            const mtuInput = document.getElementById("ob-wg-mtu").value.trim();
            const mtu = mtuInput ? parseInt(mtuInput) : null;
            
            settings = {
                "secretKey": privateKey,
                "address": addressList,
                "peers": [{
                    "publicKey": peerPublicKey,
                    "endpoint": peerEndpoint
                }]
            };
            
            if (reserved.length > 0) {
                settings.reserved = reserved;
            }
            if (mtu) {
                settings.mtu = mtu;
            }
        } else if (protocol === "socks" || protocol === "http" || protocol === "shadowsocks" || protocol === "vless" || protocol === "hysteria" || protocol === "hysteria2") {
            const address = document.getElementById("ob-address").value.trim();
            const rawPort = document.getElementById("ob-port").value.trim();
            const port = (rawPort.includes("-") || rawPort.includes(",")) ? rawPort : (parseInt(rawPort) || 443);
            const password = document.getElementById("ob-password").value.trim();
            
            if (!address || (!rawPort.includes("-") && !rawPort.includes(",") && isNaN(parseInt(rawPort)))) {
                showToast(t("routing_err_host_port", "Укажите адрес и порт сервера прокси"), "warning");
                return;
            }
            
            if (protocol === "shadowsocks") {
                const method = document.getElementById("ob-ss-method").value;
                settings = {
                    "servers": [{
                        "address": address,
                        "port": port,
                        "password": password,
                        "method": method
                    }]
                };
            } else if (protocol === "vless") {
                const flow = document.getElementById("ob-flow").value;
                const encryption = document.getElementById("ob-encryption").value.trim() || "none";
                settings = {
                    "vnext": [{
                        "address": address,
                        "port": port,
                        "users": [{
                            "id": password,
                            "encryption": encryption,
                            "flow": flow
                        }]
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
                settings = {
                    "version": 2,
                    "address": address,
                    "port": port
                };
                
                const sni = document.getElementById("ob-sni").value.trim();
                const alpnInput = document.getElementById("ob-alpn").value.trim() || "h3";
                const alpn = alpnInput.split(",").map(s => s.trim()).filter(Boolean);
                const allowInsecure = document.getElementById("ob-allow-insecure").checked;
                
                const upMbps = parseInt(document.getElementById("ob-up-mbps").value);
                const downMbps = parseInt(document.getElementById("ob-down-mbps").value);
                
                let hysteriaSettings = {
                    "version": 2,
                    "auth": password
                };
                if (!isNaN(upMbps) && upMbps > 0) {
                    hysteriaSettings.up = `${upMbps} mbps`;
                }
                if (!isNaN(downMbps) && downMbps > 0) {
                    hysteriaSettings.down = `${downMbps} mbps`;
                }
                
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
            } else {
                const username = document.getElementById("ob-username").value.trim();
                const users = username || password ? [{"user": username, "pass": password}] : [];
                settings = {
                    "servers": [{
                        "address": address,
                        "port": port,
                        "users": users
                    }]
                };
            }
        }

        // Attach backup failover settings if specified
        const selectedBackups = Array.isArray(window.selectedBackupOrder) && window.selectedBackupOrder.length > 0 
            ? [...window.selectedBackupOrder] 
            : Array.from(document.querySelectorAll(".ob-backup-cb:checked")).map(cb => cb.value);
        const fallbackStrategy = document.getElementById("ob-fallback-strategy") ? document.getElementById("ob-fallback-strategy").value : "priority";
        const healthUrl = document.getElementById("ob-health-url").value.trim();
        const healthIntRaw = document.getElementById("ob-health-interval").value.trim();
        const healthInterval = healthIntRaw ? parseInt(healthIntRaw) : 15;

        if (selectedBackups.length > 0) {
            settings.backup_outbounds = selectedBackups;
            settings.fallback_strategy = fallbackStrategy;
            if (healthUrl) settings.health_check_url = healthUrl;
            if (healthInterval) settings.health_check_interval = healthInterval;
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
    });
}
