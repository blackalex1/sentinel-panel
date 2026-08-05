import { apiFetch } from "../../../api.js";
import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { updateOutboundFormFields } from "./fields.js";
import { outboundsCache } from "./table_render.js";

window.selectedBackupOrder = [];

export function updateBackupBadges() {
    document.querySelectorAll(".backup-option-row").forEach(label => {
        const cb = label.querySelector(".ob-backup-cb");
        let badge = label.querySelector(".backup-priority-badge");
        if (!cb) return;
        
        const idx = (window.selectedBackupOrder || []).indexOf(cb.value);
        if (idx !== -1) {
            cb.checked = true;
            if (!badge) {
                badge = document.createElement("span");
                badge.className = "backup-priority-badge";
                badge.style.cssText = "margin-left: auto; background: linear-gradient(135deg, #7c3aed, #6366f1); color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 600; box-shadow: 0 2px 4px rgba(0,0,0,0.2);";
                label.appendChild(badge);
            }
            badge.innerText = `${t("routing_modal_priority_badge", "Приоритет №")}${idx + 1}`;
        } else {
            cb.checked = false;
            if (badge) {
                badge.remove();
            }
        }
    });
}

export async function openOutboundModal(id = null) {
    const form = document.getElementById("outbound-form");
    if (!form) return;
    form.reset();
    
    const protocolSelect = document.getElementById("ob-protocol");
    protocolSelect.disabled = false;

    // Populate backup outbounds checkbox list
    const backupContainer = document.getElementById("ob-backup-outbounds-container");
    if (backupContainer) {
        backupContainer.innerHTML = "";
        const allObsRes = await apiFetch("/api/routing/outbounds");
        const allObs = (allObsRes && allObsRes.success) ? allObsRes.obj : outboundsCache;
        const seenTags = new Set();
        const validObs = allObs.filter(o => {
            if (!o.tag || o.tag === "api" || o.tag === "blocked" || o.protocol === "blackhole" || (id && o.id === id)) {
                return false;
            }
            if (seenTags.has(o.tag)) {
                return false;
            }
            seenTags.add(o.tag);
            return true;
        });
        
        if (validObs.length === 0) {
            backupContainer.innerHTML = `<span style="color: var(--text-secondary); font-size: 12px;">${t("routing_modal_no_other_outbounds", "Нет доступных других исходящих подключений")}</span>`;
        } else {
            validObs.forEach(o => {
                const label = document.createElement("label");
                label.className = "backup-option-row";
                label.style.cssText = "display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 6px 10px; border-radius: 6px; background: rgba(255,255,255,0.03); transition: background 0.2s;";
                label.addEventListener("mouseenter", () => label.style.background = "rgba(255,255,255,0.08)");
                label.addEventListener("mouseleave", () => label.style.background = "rgba(255,255,255,0.03)");
                
                const cb = document.createElement("input");
                cb.type = "checkbox";
                cb.className = "ob-backup-cb";
                cb.value = o.tag;
                cb.style.cssText = "width: 16px; height: 16px; accent-color: var(--primary-color); cursor: pointer;";
                cb.addEventListener("change", () => {
                    if (!Array.isArray(window.selectedBackupOrder)) {
                        window.selectedBackupOrder = [];
                    }
                    if (cb.checked) {
                        if (!window.selectedBackupOrder.includes(cb.value)) {
                            window.selectedBackupOrder.push(cb.value);
                        }
                    } else {
                        window.selectedBackupOrder = window.selectedBackupOrder.filter(t => t !== cb.value);
                    }
                    updateBackupBadges();
                });
                
                const span = document.createElement("span");
                span.style.cssText = "font-size: 13px; color: var(--text-primary); font-weight: 500;";
                span.innerText = `${o.remark} (${o.tag})`;
                
                label.appendChild(cb);
                label.appendChild(span);
                backupContainer.appendChild(label);
            });
        }
    }

    if (id) {
        document.getElementById("outbound-modal-title").innerText = t("routing_modal_edit_outbound", "Редактирование исходящего подключения");
        const res = await apiFetch(`/api/routing/outbounds`);
        const ob = res.obj.find(x => x.id === id);
        if (ob) {
            document.getElementById("ob-id").value = ob.id;
            document.getElementById("ob-remark").value = ob.remark;
            protocolSelect.value = ob.protocol;
            // Prevent changing protocol/tag of system outbounds to avoid breaking rules
            if (ob.is_system === 1) {
                protocolSelect.disabled = true;
                document.getElementById("ob-tag").disabled = true;
            } else {
                document.getElementById("ob-tag").disabled = false;
            }
            document.getElementById("ob-tag").value = ob.tag;
            document.getElementById("ob-enable").checked = ob.enable === 1;
            
            // Populate proxy settings
            const settingsObj = JSON.parse(ob.settings || "{}");
            const streamSettingsObj = JSON.parse(ob.stream_settings || "{}");
            
            let address = "";
            let port = "";
            let password = "";
            
            document.getElementById("ob-username").value = "";
            document.getElementById("ob-password").value = "";
            document.getElementById("ob-ss-method").value = "aes-256-gcm";
            document.getElementById("ob-sni").value = "";
            document.getElementById("ob-pbk").value = "";
            document.getElementById("ob-shortid").value = "";
            document.getElementById("ob-fingerprint").value = "chrome";
            const spxEl = document.getElementById("ob-spx");
            if (spxEl) spxEl.value = "";
            document.getElementById("ob-alpn").value = "";
            document.getElementById("ob-flow").value = "";
            document.getElementById("ob-encryption").value = "";
            document.getElementById("ob-security").value = "none";
            document.getElementById("ob-up-mbps").value = "";
            document.getElementById("ob-down-mbps").value = "";
            document.getElementById("ob-allow-insecure").checked = false;
            document.getElementById("ob-pinned-sha256").value = "";
            document.getElementById("ob-hysteria-obfs").value = "";
            document.getElementById("ob-hysteria-obfs-password").value = "";
            
            document.getElementById("ob-wg-private-key").value = "";
            document.getElementById("ob-wg-addresses").value = "";
            document.getElementById("ob-wg-reserved").value = "";
            document.getElementById("ob-wg-peer-public-key").value = "";
            document.getElementById("ob-wg-endpoint").value = "";
            document.getElementById("ob-wg-mtu").value = "";
            
            if (ob.protocol === "socks" || ob.protocol === "http" || ob.protocol === "shadowsocks") {
                const server = settingsObj.servers ? settingsObj.servers[0] : null;
                if (server) {
                    address = server.address || "";
                    port = server.port || "";
                    
                    if (server.users && server.users.length > 0) {
                        document.getElementById("ob-username").value = server.users[0].user || "";
                        password = server.users[0].pass || "";
                    } else if (server.password) {
                        password = server.password || "";
                    }
                }
                if (server && server.method) {
                    document.getElementById("ob-ss-method").value = server.method;
                }
            } else if (ob.protocol === "vless") {
                const server = settingsObj.vnext ? settingsObj.vnext[0] : null;
                if (server) {
                    address = server.address || "";
                    port = server.port || "";
                    if (server.users && server.users.length > 0) {
                        password = server.users[0].id || "";
                        document.getElementById("ob-flow").value = server.users[0].flow || "";
                        document.getElementById("ob-encryption").value = server.users[0].encryption || "";
                    }
                }
                
                const security = streamSettingsObj.security || "none";
                document.getElementById("ob-security").value = security;
                
                if (security === "tls") {
                    const ts = streamSettingsObj.tlsSettings || {};
                    document.getElementById("ob-sni").value = ts.serverName || "";
                    document.getElementById("ob-alpn").value = (ts.alpn || []).join(", ");
                    document.getElementById("ob-allow-insecure").checked = ts.allowInsecure === true;
                    let pins = ts.pinnedPeerCertSha256 || "";
                    if (typeof pins === "string") {
                        pins = pins.replace(/~/g, ", ");
                    } else if (Array.isArray(pins)) {
                        pins = pins.join(", ");
                    }
                    document.getElementById("ob-pinned-sha256").value = pins;
                } else if (security === "reality") {
                    const rs = streamSettingsObj.realitySettings || {};
                    document.getElementById("ob-sni").value = rs.serverName || "";
                    document.getElementById("ob-pbk").value = rs.publicKey || "";
                    document.getElementById("ob-shortid").value = rs.shortId || "";
                    document.getElementById("ob-fingerprint").value = rs.fingerprint || "chrome";
                    const spxEl = document.getElementById("ob-spx");
                    if (spxEl) spxEl.value = rs.spiderX || "";
                }
            } else if (ob.protocol === "hysteria" || ob.protocol === "hysteria2") {
                address = settingsObj.address || "";
                port = settingsObj.port || "";
                
                const ts = streamSettingsObj.tlsSettings || {};
                document.getElementById("ob-sni").value = ts.serverName || "";
                document.getElementById("ob-alpn").value = (ts.alpn || []).join(", ");
                document.getElementById("ob-allow-insecure").checked = ts.allowInsecure === true;
                let pins = ts.pinnedPeerCertSha256 || "";
                if (typeof pins === "string") {
                    pins = pins.replace(/~/g, ", ");
                } else if (Array.isArray(pins)) {
                    pins = pins.join(", ");
                }
                document.getElementById("ob-pinned-sha256").value = pins;
                
                const hs = streamSettingsObj.hysteriaSettings || {};
                password = hs.auth || "";
                if (hs.hop) {
                    port = hs.hop;
                }
                
                const upRaw = hs.up || "";
                const downRaw = hs.down || "";
                document.getElementById("ob-up-mbps").value = upRaw ? parseInt(upRaw) : "";
                document.getElementById("ob-down-mbps").value = downRaw ? parseInt(downRaw) : "";
                
                // Populate obfs settings
                const obfsVal = hs.obfs || hs.obfs_type || "";
                const obfsPwd = hs.obfsPassword || hs.obfs_password || "";
                document.getElementById("ob-hysteria-obfs").value = obfsVal;
                document.getElementById("ob-hysteria-obfs-password").value = obfsPwd;
            } else if (ob.protocol === "wireguard") {
                document.getElementById("ob-wg-private-key").value = settingsObj.secretKey || "";
                document.getElementById("ob-wg-addresses").value = Array.isArray(settingsObj.address) ? settingsObj.address.join(", ") : (settingsObj.address || "");
                document.getElementById("ob-wg-reserved").value = Array.isArray(settingsObj.reserved) ? settingsObj.reserved.join(",") : "";
                
                const peer = settingsObj.peers ? settingsObj.peers[0] : null;
                if (peer) {
                    document.getElementById("ob-wg-peer-public-key").value = peer.publicKey || "";
                    document.getElementById("ob-wg-endpoint").value = peer.endpoint || "";
                }
                document.getElementById("ob-wg-mtu").value = settingsObj.mtu || "";
            }
            
            document.getElementById("ob-address").value = address;
            document.getElementById("ob-port").value = port;
            document.getElementById("ob-password").value = password;

            // Populate backup outbounds selections
            const backups = settingsObj.backup_outbounds;
            window.selectedBackupOrder = Array.isArray(backups) ? [...backups] : [];
            updateBackupBadges();
            
            const fallbackStratEl = document.getElementById("ob-fallback-strategy");
            if (fallbackStratEl) {
                fallbackStratEl.value = settingsObj.fallback_strategy || "priority";
            }
            document.getElementById("ob-health-url").value = settingsObj.health_check_url || "";
            document.getElementById("ob-health-interval").value = settingsObj.health_check_interval || "";
        }
    } else {
        document.getElementById("outbound-modal-title").innerText = t("routing_modal_create_outbound", "Создание исходящего подключения");
        document.getElementById("ob-id").value = "";
        document.getElementById("ob-tag").disabled = false;
        document.getElementById("ob-enable").checked = true;
        
        window.selectedBackupOrder = [];
        updateBackupBadges();
        
        const fallbackStratEl = document.getElementById("ob-fallback-strategy");
        if (fallbackStratEl) {
            fallbackStratEl.value = "priority";
        }
        document.getElementById("ob-health-url").value = "";
        document.getElementById("ob-health-interval").value = "";
    }
    
    const btnWarp = document.getElementById("btn-generate-warp-profile");
    if (btnWarp && !btnWarp.dataset.bound) {
        btnWarp.dataset.bound = "true";
        btnWarp.addEventListener("click", async () => {
            btnWarp.disabled = true;
            btnWarp.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> ' + t("routing_warp_btn_registering", "Регистрация...");
            showToast(t("routing_warp_toast_registering", "Регистрация аккаунта Cloudflare WARP..."), "info");
            
            try {
                const res = await apiFetch("/api/routing/outbounds/generate-warp", { method: "POST" });
                if (res && res.success) {
                    const data = res.obj;
                    document.getElementById("ob-wg-private-key").value = data.private_key || "";
                    document.getElementById("ob-wg-addresses").value = `${data.address_v4 || ""}, ${data.address_v6 || ""}`.replace(/,\s*$/, "");
                    document.getElementById("ob-wg-reserved").value = (data.reserved || []).join(",");
                    document.getElementById("ob-wg-peer-public-key").value = data.peer_public_key || "";
                    document.getElementById("ob-wg-endpoint").value = data.endpoint || "";
                    document.getElementById("ob-wg-mtu").value = "1280";
                    showToast(t("routing_warp_toast_register_success", "Аккаунт Cloudflare WARP успешно сгенерирован!"));
                } else {
                    showToast(res ? res.msg : t("routing_warp_toast_register_error", "Не удалось сгенерировать WARP-профиль"), "error");
                }
            } catch (err) {
                showToast(t("routing_warp_toast_register_err_msg", "Ошибка генерации WARP: {error}").replace("{error}", err), "error");
            } finally {
                btnWarp.disabled = false;
                btnWarp.innerHTML = '<i class="fa-solid fa-cloud-bolt" style="margin-right: 4px;"></i>' + t("routing_warp_btn_generate", "Сгенерировать WARP");
            }
        });
    }

    updateOutboundFormFields();
    document.getElementById("outbound-modal").classList.add("active");
}
