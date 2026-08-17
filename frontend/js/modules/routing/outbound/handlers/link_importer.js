import { apiFetch } from "../../../../api.js";
import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { parseProxyLink } from "../../link-parser.js";
import { fetchOutboundSchema, setCurrentOutboundValues, getCurrentOutboundValues, populateFallbackDropdown } from "../modal_manager.js";
import { renderDynamicOutboundForm } from "../../../inbounds/schema-renderer.js";

export function bindLinkImporterListener() {
    const importLinkInput = document.getElementById("ob-import-link");
    if (!importLinkInput) return;

    importLinkInput.addEventListener("input", async (e) => {
        const val = e.target.value.trim();
        if (!val) return;
        
        const lowerVal = val.toLowerCase();
        if (lowerVal.startsWith("vless://") || 
            lowerVal.startsWith("vmess://") || 
            lowerVal.startsWith("trojan://") || 
            lowerVal.startsWith("ss://") || 
            lowerVal.startsWith("socks://") || 
            lowerVal.startsWith("socks5://") || 
            lowerVal.startsWith("http://") || 
            lowerVal.startsWith("https://") || 
            lowerVal.startsWith("hysteria2://") || 
            lowerVal.startsWith("hy2://") || 
            lowerVal.startsWith("hysteria://") ||
            lowerVal.startsWith("wireguard://") ||
            lowerVal.startsWith("wg://") ||
            lowerVal.startsWith("tuic://")) {
            
            let parsed = null;
            try {
                const res = await apiFetch("/api/routing/outbounds/parse-link", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ link: val })
                });
                if (res && res.success && res.obj) {
                    const obj = res.obj;
                    let proto = (obj.protocol || "").toLowerCase();
                    if (proto === "ss") proto = "shadowsocks";
                    if (proto === "hy2" || proto === "hysteria") proto = "hysteria2";

                    const hopPort = obj.portHopping || obj.hop || obj.ports || obj.mport || "";
                    parsed = {
                        protocol: proto,
                        remark: obj.name || obj.remark || `${proto.toUpperCase()} Proxy`,
                        tag: `${proto}-${(obj.address || "out").replace(/[^a-zA-Z0-9]/g, "-").toLowerCase()}`,
                        host: obj.address || "",
                        port: hopPort || obj.port || 443,
                        uuid: obj.uuid || "",
                        password: obj.password || obj.uuid || "",
                        security: obj.security || (proto === "vless" ? "reality" : (proto === "hysteria2" || proto === "trojan" ? "tls" : "none")),
                        sni: obj.sni || "",
                        publicKey: obj.publicKey || "",
                        shortId: obj.shortId || "",
                        spiderX: obj.spiderX || "",
                        fingerprint: obj.fingerprint || "chrome",
                        alpn: obj.alpn ? (Array.isArray(obj.alpn) ? obj.alpn.join(",") : obj.alpn) : "",
                        flow: obj.flow || "",
                        encryption: obj.encryption || "",
                        method: obj.method || "2022-blake3-aes-128-gcm",
                        allowInsecure: Boolean(obj.allowInsecure || obj.insecure || obj.allow_insecure),
                        upMbps: parseInt(obj.upMbps || obj.bandwidthUp || obj.up || 100) || 100,
                        downMbps: parseInt(obj.downMbps || obj.bandwidthDown || obj.down || 100) || 100,
                        obfs: obj.obfs || obj.obfsType || obj.obfs_type || "",
                        obfsPassword: obj.obfsPassword || obj.obfs_password || "",
                        pinnedPeerCertSha256: obj.pinnedPeerCertSha256 || obj.pinSHA256 || obj.pin_sha256 || "",
                        network: obj.network || obj.type || "tcp",
                        path: obj.path || "",
                        wsHost: obj.host || obj.wsHost || "",
                        serviceName: obj.serviceName || "",
                        privateKey: obj.privateKey || obj.secretKey || "",
                        peerPublicKey: obj.peerPublicKey || "",
                        localAddress: obj.localAddress || (Array.isArray(obj.address) ? obj.address.join(",") : ""),
                        mtu: obj.mtu || 1420,
                        reserved: obj.reserved ? (Array.isArray(obj.reserved) ? obj.reserved.join(",") : obj.reserved) : "",
                        enable: true
                    };
                }
            } catch (err) {
                console.warn("Failed to parse via core bridge, using fallback:", err);
            }

            if (!parsed) {
                // Fallback to local JS parser
                const fallbackParsed = parseProxyLink(val);
                if (fallbackParsed) {
                    let proto = fallbackParsed.protocol;
                    if (proto === "ss") proto = "shadowsocks";
                    if (proto === "hy2" || proto === "hysteria") proto = "hysteria2";

                    parsed = {
                        protocol: proto,
                        remark: fallbackParsed.remark || `${proto.toUpperCase()} Proxy`,
                        tag: `${proto}-${(fallbackParsed.host || "out").replace(/[^a-zA-Z0-9]/g, "-").toLowerCase()}`,
                        host: fallbackParsed.host || "",
                        port: fallbackParsed.port || 443,
                        uuid: fallbackParsed.uuid || "",
                        password: fallbackParsed.password || fallbackParsed.uuid || "",
                        security: fallbackParsed.security || (proto === "vless" ? "reality" : (proto === "hysteria2" || proto === "trojan" ? "tls" : "none")),
                        sni: fallbackParsed.sni || "",
                        publicKey: fallbackParsed.pbk || "",
                        shortId: fallbackParsed.sid || "",
                        spiderX: fallbackParsed.spx || "",
                        fingerprint: fallbackParsed.fp || "chrome",
                        flow: fallbackParsed.flow || "",
                        encryption: fallbackParsed.encryption || "",
                        method: fallbackParsed.method || "2022-blake3-aes-128-gcm",
                        allowInsecure: Boolean(fallbackParsed.insecure || fallbackParsed.allowInsecure),
                        upMbps: parseInt(fallbackParsed.up) || 100,
                        downMbps: parseInt(fallbackParsed.down) || 100,
                        obfs: fallbackParsed.obfs || fallbackParsed.obfsType || "",
                        obfsPassword: fallbackParsed.obfsPassword || "",
                        pinnedPeerCertSha256: fallbackParsed.pinSHA256 || fallbackParsed.pinnedPeerCertSha256 || "",
                        enable: true
                    };
                }
            }

            if (parsed && parsed.protocol) {
                setCurrentOutboundValues(parsed);
                const currentVals = getCurrentOutboundValues();

                const protocolSelect = document.getElementById("ob-protocol");
                if (protocolSelect) {
                    protocolSelect.value = parsed.protocol;
                }

                const schema = await fetchOutboundSchema();
                const outboundProtocols = (schema && schema.outboundProtocols) ? schema.outboundProtocols : {};
                const cap = outboundProtocols[parsed.protocol] || outboundProtocols["vless"] || { tabDefinitions: [] };

                const tabsContainer = document.getElementById("outbound-modal-tabs");
                const schemaContainer = document.getElementById("outbound-schema-container");

                renderDynamicOutboundForm(schemaContainer, tabsContainer, cap.tabDefinitions || [], currentVals, (updated) => {
                    setCurrentOutboundValues(updated);
                });

                // Populate fallback routes dropdown in the newly rendered form
                await populateFallbackDropdown(currentVals);

                showToast(t("routing_link_imported_success", "Ссылка успешно импортирована из ядра!"));
            } else {
                showToast(t("routing_link_parse_failed", "Не удалось распознать ссылку"), "error");
            }
        }
    });
}
