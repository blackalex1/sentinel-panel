import { setupHysteriaCoreListeners } from "./core.js";
import { setupHysteriaConfigListeners } from "./config_ui/listeners.js";

export { saveHysteriaConfigToServer } from "./config_ui/api.js";
export { loadHysteriaConfig, renderSelectedHysteriaConfig } from "./config_ui/render.js";
export { setupHysteriaConfigListeners };
export {
    loadHysteriaCoreInfo,
    loadHysteriaLogs,
    startHysteriaLogsStream,
    stopHysteriaLogsStream,
    setupHysteriaCoreListeners
} from "./core.js";

export function setupHysteriaModule() {
    setupHysteriaCoreListeners();
    setupHysteriaConfigListeners();
}
