import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { parseProxyLink } from "../../link-parser.js";
import { updateOutboundFormFields } from "../fields.js";

export function bindLinkImporterListener() {
    const importLinkInput = document.getElementById("ob-import-link");
    if (!importLinkInput) return;

    importLinkInput.addEventListener("input", (e) => {
        const val = e.target.value.trim();
        if (!val) return;
        
        const lowerVal = val.toLowerCase();
        if (lowerVal.startsWith("vless://") || 
            lowerVal.startsWith("ss://") || 
            lowerVal.startsWith("socks://") || 
            lowerVal.startsWith("socks5://") || 
            lowerVal.startsWith("http://") || 
            lowerVal.startsWith("hysteria2://") || 
            lowerVal.startsWith("hy2://") || 
            lowerVal.startsWith("hysteria://")) {
            
            const parsed = parseProxyLink(val);
            if (parsed) {
                document.getElementById("ob-protocol").value = parsed.protocol;
                document.getElementById("ob-remark").value = parsed.remark || "";
                
                const sanitizedHost = (parsed.host || "").replace(/[^a-zA-Z0-9]/g, "-").toLowerCase();
                document.getElementById("ob-tag").value = `${parsed.protocol}-${sanitizedHost || Math.floor(Math.random() * 1000)}`;
                
                document.getElementById("ob-address").value = parsed.host || "";
                document.getElementById("ob-port").value = parsed.port || "";
                
                document.getElementById("ob-username").value = "";
                document.getElementById("ob-password").value = "";
                
                if (parsed.protocol === "vless") {
                    document.getElementById("ob-password").value = parsed.uuid || "";
                    document.getElementById("ob-security").value = parsed.security || "none";
                    document.getElementById("ob-sni").value = parsed.sni || "";
                    document.getElementById("ob-pbk").value = parsed.pbk || "";
                    document.getElementById("ob-shortid").value = parsed.sid || "";
                    document.getElementById("ob-fingerprint").value = parsed.fp || "chrome";
                    document.getElementById("ob-alpn").value = parsed.alpn || "";
                    document.getElementById("ob-flow").value = parsed.flow || "";
                    document.getElementById("ob-encryption").value = parsed.encryption || "";
                    document.getElementById("ob-pinned-sha256").value = parsed.pinSHA256 || "";
                    const spxEl = document.getElementById("ob-spx");
                    if (spxEl) spxEl.value = parsed.spx || "";
                } else if (parsed.protocol === "hysteria" || parsed.protocol === "hysteria2") {
                    document.getElementById("ob-port").value = parsed.hop || parsed.mport || parsed.ports || parsed.port || "";
                    document.getElementById("ob-password").value = parsed.password || "";
                    document.getElementById("ob-sni").value = parsed.sni || "";
                    document.getElementById("ob-alpn").value = parsed.alpn || "";
                    document.getElementById("ob-up-mbps").value = parsed.up || "";
                    document.getElementById("ob-down-mbps").value = parsed.down || "";
                    document.getElementById("ob-allow-insecure").checked = parsed.insecure === true;
                    document.getElementById("ob-hysteria-obfs").value = parsed.obfs || "";
                    document.getElementById("ob-hysteria-obfs-password").value = parsed.obfsPassword || "";
                    document.getElementById("ob-pinned-sha256").value = parsed.pinSHA256 || "";
                } else if (parsed.protocol === "shadowsocks") {
                    document.getElementById("ob-password").value = parsed.password || "";
                    document.getElementById("ob-ss-method").value = parsed.method || "aes-256-gcm";
                } else if (parsed.protocol === "socks" || parsed.protocol === "http") {
                    document.getElementById("ob-username").value = parsed.username || "";
                    document.getElementById("ob-password").value = parsed.password || "";
                }
                
                e.target.value = ""; 
                updateOutboundFormFields();
                
                const inputs = document.querySelectorAll("#outbound-form input, #outbound-form select, #outbound-form textarea");
                inputs.forEach(el => el.classList.remove("input-invalid"));
                
                showToast(t("routing_modal_import_success", "Ссылка успешно импортирована!"));
            } else {
                showToast(t("routing_modal_import_error", "Не удалось распознать ссылку. Проверьте формат."), "warning");
            }
        }
    });
}
