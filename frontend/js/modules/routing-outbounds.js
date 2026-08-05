// Re-export modular functions for backward compatibility
export { parseProxyLink } from "./routing/link-parser.js";
export { updateOutboundFormFields, validateOutboundForm } from "./routing/outbound-form.js";

export { outboundsCache, setOutboundsCache, loadOutbounds, populateOutboundDropdowns } from "./routing/outbound/table_render.js";
export { toggleOutbound, deleteOutbound } from "./routing/outbound/actions.js";
export { updateBackupBadges, openOutboundModal } from "./routing/outbound/modal_manager.js";

// Make global window functions available for inline HTML onclick attributes
import { toggleOutbound, deleteOutbound } from "./routing/outbound/actions.js";
import { openOutboundModal } from "./routing/outbound/modal_manager.js";

window.toggleOutbound = toggleOutbound;
window.deleteOutbound = deleteOutbound;
window.openOutboundModal = openOutboundModal;
