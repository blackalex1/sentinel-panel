// Hysteria 2 Core Inbound Form Handling

export function compileHysteriaSettings(streamSettings, settings, originalClients) {
    const hystModeElem = document.getElementById("ib-hysteria-mode");
    const hystMode = hystModeElem ? hystModeElem.value : "masq";
    const obfsPassword = hystMode === "obfs" ? ((document.getElementById("ib-hysteria-obfs-password") || {}).value || "") : "";
    const ignoreClientBandwidth = (document.getElementById("ib-hysteria-ignore-bw") || {}).checked || false;
    const rawUpMbps = parseInt((document.getElementById("ib-hysteria-up-mbps") || {}).value) || 0;
    const rawDownMbps = parseInt((document.getElementById("ib-hysteria-down-mbps") || {}).value) || 0;
    const upMbps = ignoreClientBandwidth ? 0 : rawUpMbps;
    const downMbps = ignoreClientBandwidth ? 0 : rawDownMbps;
    
    const certMode = (document.getElementById("ib-hysteria-cert-mode") || {}).value || "self";
    const certPath = (document.getElementById("ib-hysteria-cert-path") || {}).value || "";
    const keyPath = (document.getElementById("ib-hysteria-key-path") || {}).value || "";
    
    let masqType = "proxy";
    let masqValue = "";
    if (hystMode === "masq") {
        masqType = (document.getElementById("ib-hysteria-masq-type") || {}).value || "proxy";
        masqValue = ((document.getElementById("ib-hysteria-masq-value") || {}).value || "").trim();
        if (masqType === "proxy" && masqValue && !masqValue.startsWith("http://") && !masqValue.startsWith("https://")) {
            masqValue = `https://${masqValue}`;
        }
    } else {
        masqType = "string";
        masqValue = "";
    }
    
    const hop = (document.getElementById("ib-hysteria-hop") || {}).value || "";
    const routingViaXray = (document.getElementById("ib-hysteria-routing-xray") || {}).checked || false;
    const hystSni = (document.getElementById("ib-hysteria-sni") || {}).value || "";

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
    const modeElem = document.getElementById("ib-hysteria-mode");
    if (modeElem) modeElem.value = hystMode;
    
    const obfsPassElem = document.getElementById("ib-hysteria-obfs-password");
    if (obfsPassElem) obfsPassElem.value = ho.obfsPassword || "";
    
    const upElem = document.getElementById("ib-hysteria-up-mbps");
    if (upElem) upElem.value = ho.upMbps || 0;
    
    const downElem = document.getElementById("ib-hysteria-down-mbps");
    if (downElem) downElem.value = ho.downMbps || 0;
    
    const certModeElem = document.getElementById("ib-hysteria-cert-mode");
    if (certModeElem) certModeElem.value = ho.certMode || "self";
    
    const certPathElem = document.getElementById("ib-hysteria-cert-path");
    if (certPathElem) certPathElem.value = ho.certPath || "";
    
    const keyPathElem = document.getElementById("ib-hysteria-key-path");
    if (keyPathElem) keyPathElem.value = ho.keyPath || "";
    
    const masqTypeElem = document.getElementById("ib-hysteria-masq-type");
    if (masqTypeElem) masqTypeElem.value = ho.masqType || "proxy";
    
    const masqValElem = document.getElementById("ib-hysteria-masq-value");
    if (masqValElem) masqValElem.value = ho.masqValue || "";
    
    const hopElem = document.getElementById("ib-hysteria-hop");
    if (hopElem) hopElem.value = ho.hop || "";
    
    const sniElem = document.getElementById("ib-hysteria-sni");
    if (sniElem) sniElem.value = ho.sni || "";
    
    const xrayRouteElem = document.getElementById("ib-hysteria-routing-xray");
    if (xrayRouteElem) xrayRouteElem.checked = ho.routingViaXray || false;
    
    const ignoreBwElem = document.getElementById("ib-hysteria-ignore-bw");
    if (ignoreBwElem) ignoreBwElem.checked = ho.ignoreClientBandwidth || false;
}
