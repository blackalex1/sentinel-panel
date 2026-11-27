import { setupGeneralListeners } from "./core.js";
import { setupSecurityListeners } from "./security.js";
import { setupBackupsListeners } from "./backups.js";
import { setupTelegramListeners } from "./telegram.js";
import { setupNetworkListeners } from "./network.js";
import { setupUpdateListeners, checkPanelUpdates, checkCoreUpdates } from "./update.js";

export { originalSecretPath, setOriginalSecretPath, loadSettings, updateDecoyUI } from "./core.js";
export { loadActiveSessions } from "./security.js";
export { loadOptimizationStatus, loadIpv6Status } from "./network.js";
export { setupUpdateListeners, checkPanelUpdates, checkCoreUpdates };

export function setupSettingsListeners() {
    setupGeneralListeners();
    setupSecurityListeners();
    setupBackupsListeners();
    setupTelegramListeners();
    setupNetworkListeners();
    setupUpdateListeners();
}
