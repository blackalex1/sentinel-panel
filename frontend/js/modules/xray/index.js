import { setupXrayConfigListeners } from "./config_ui/listeners.js";
import { setupXrayCoreListeners } from "./core.js";
import { setupGeoListeners } from "./geo.js";

export { saveXrayConfigToServer } from "./config_ui/api.js";
export { loadXrayConfig } from "./config_ui/render.js";
export { setupXrayConfigListeners };
export { initEditorModal } from "./config_ui/editor_modal.js";
export { loadCoreInfo, loadLogs, setupXrayCoreListeners, startLogsStream, stopLogsStream } from "./core.js";
export { loadGeoInfo, setupGeoListeners } from "./geo.js";

export function setupXrayModule() {
    setupXrayCoreListeners();
    setupGeoListeners();
    setupXrayConfigListeners();
}
