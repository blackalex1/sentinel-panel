// Hysteria 2 Core Inbound Form Handling

export function compileHysteriaSettings(streamSettings, settings, originalClients) {
    const hystMode = document.getElementById("ib-hysteria-mode").value || "masq";
    const obfsPassword = hystMode === "obfs" ? (document.getElementById("ib-hysteria-obfs-password").value || "") : "";
    const ignoreClientBandwidth = document.getElementById("ib-hysteria-ignore-bw").checked;
    const rawUpMbps = parseInt(document.getElementById("ib-hysteria-up-mbps").value) || 0;
    const rawDownMbps = parseInt(document.getElementById("ib-hysteria-down-mbps").value) || 0;
    const upMbps = ignoreClientBandwidth ? 0 : rawUpMbps;
    const downMbps = ignoreClientBandwidth ? 0 : rawDownMbps;
    
    const certMode = document.getElementById("ib-hysteria-cert-mode").value || "self";
    const certPath = document.getElementById("ib-hysteria-cert-path").value || "";
    const keyPath = document.getElementById("ib-hysteria-key-path").value || "";
    const masqType = hystMode === "masq" ? (document.getElementById("ib-hysteria-masq-type").value || "proxy") : "proxy";
    const masqValue = hystMode === "masq" ? (document.getElementById("ib-hysteria-masq-value").value || "") : (document.getElementById("ib-hysteria-masq-value").value || "https://yahoo.com");
    const hop = document.getElementById("ib-hysteria-hop").value || "";
    const routingViaXray = document.getElementById("ib-hysteria-routing-xray").checked;
    const hystSni = document.getElementById("ib-hysteria-sni").value || "";

    if (settings.clients && Array.isArray(settings.clients)) {
        settings.clients = settings.clients.map(c => {
            const copy = { ...c };
            delete copy.flow;
            return copy;
        });
    }
    
    streamSettings.hysteria = {
        obfsPassword: obfsPassword,
        upMbps: upMbps,
        downMbps: downMbps,
        ignoreClientBandwidth: ignoreClientBandwidth,
        certMode: certMode,
        certPath: certPath,
        keyPath: keyPath,
        masqType: masqType,
        masqValue: masqValue,
        hop: hop,
        sni: hystSni,
        routingViaXray: routingViaXray
    };
}

export function populateHysteriaSettings(streamSettings) {
    const ho = streamSettings.hysteria || {};
    const hystMode = ho.obfsPassword ? "obfs" : "masq";
    document.getElementById("ib-hysteria-mode").value = hystMode;
    
    document.getElementById("ib-hysteria-obfs-password").value = ho.obfsPassword || "";
    document.getElementById("ib-hysteria-up-mbps").value = ho.upMbps || 0;
    document.getElementById("ib-hysteria-down-mbps").value = ho.downMbps || 0;
    document.getElementById("ib-hysteria-cert-mode").value = ho.certMode || "self";
    document.getElementById("ib-hysteria-cert-path").value = ho.certPath || "";
    document.getElementById("ib-hysteria-key-path").value = ho.keyPath || "";
    document.getElementById("ib-hysteria-masq-type").value = ho.masqType || "proxy";
    document.getElementById("ib-hysteria-masq-value").value = ho.masqValue || "";
    document.getElementById("ib-hysteria-hop").value = ho.hop || "";
    document.getElementById("ib-hysteria-sni").value = ho.sni || "";
    document.getElementById("ib-hysteria-routing-xray").checked = ho.routingViaXray || false;
    document.getElementById("ib-hysteria-ignore-bw").checked = ho.ignoreClientBandwidth || false;
}
