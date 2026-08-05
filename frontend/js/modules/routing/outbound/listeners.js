import { openOutboundModal } from "../../routing-outbounds.js";
import { updateOutboundFormFields } from "./fields.js";
import { bindLinkImporterListener } from "./handlers/link_importer.js";
import { bindTesterListener } from "./handlers/tester.js";
import { bindSubmitListener } from "./handlers/submit.js";

export function setupOutboundFormListeners() {
    const addObBtn = document.getElementById("add-outbound-btn");
    if (addObBtn) {
        addObBtn.addEventListener("click", () => openOutboundModal());
    }
    
    const protocolSelect = document.getElementById("ob-protocol");
    if (protocolSelect) {
        protocolSelect.addEventListener("change", updateOutboundFormFields);
    }
    
    const securitySelect = document.getElementById("ob-security");
    if (securitySelect) {
        securitySelect.addEventListener("change", updateOutboundFormFields);
    }
    
    const obfsSelect = document.getElementById("ob-hysteria-obfs");
    if (obfsSelect) {
        obfsSelect.addEventListener("change", updateOutboundFormFields);
    }

    bindLinkImporterListener();
    bindTesterListener();
    bindSubmitListener();
}
