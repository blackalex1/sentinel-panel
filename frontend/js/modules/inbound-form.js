export {
    editInboundId,
    originalClients,
    setEditInboundId,
    generateRandomPassword,
    switchInboundModalTab,
    serializeFormToJson,
    populateFormFromJson,
    handleInboundFormSubmit,
    openEditInboundModal
} from "./inbounds/core.js";

export {
    updateFormToggles,
    updateTabVisibility,
    handleProtocolChange
} from "./inbounds/toggles.js";

export { validateInboundForm } from "./inbounds/validation.js";
