// Re-export modular functions for backward compatibility
export { parseProxyLink } from "./link-parser.js";
export { updateOutboundFormFields, validateOutboundForm } from "./outbound-form.js";

export { outboundsCache, setOutboundsCache, loadOutbounds, populateOutboundDropdowns } from "./outbound/table_render.js";
export { toggleOutbound, deleteOutbound } from "./outbound/actions.js";
export { updateBackupBadges, openOutboundModal } from "./outbound/modal_manager.js";

// Make global window functions available for inline HTML onclick attributes
import { toggleOutbound, deleteOutbound } from "./outbound/actions.js";
import { openOutboundModal } from "./outbound/modal_manager.js";

window.toggleOutbound = toggleOutbound;
window.deleteOutbound = deleteOutbound;
window.openOutboundModal = openOutboundModal;
