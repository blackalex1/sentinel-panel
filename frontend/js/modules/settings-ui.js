import { setupGeneralListeners } from "./settings/core.js";
import { setupSecurityListeners } from "./settings/security.js";
import { setupBackupsListeners } from "./settings/backups.js";
import { setupTelegramListeners } from "./settings/telegram.js";
import { setupNetworkListeners } from "./settings/network.js";
import { setupUpdateListeners, checkPanelUpdates, checkCoreUpdates } from "./settings/update.js";

export { originalSecretPath, setOriginalSecretPath, loadSettings, updateDecoyUI } from "./settings/core.js";
export { loadActiveSessions } from "./settings/security.js";
export { loadOptimizationStatus, loadIpv6Status } from "./settings/network.js";
export { setupUpdateListeners, checkPanelUpdates, checkCoreUpdates };

export function setupSettingsListeners() {
    setupGeneralListeners();
    setupSecurityListeners();
    setupBackupsListeners();
    setupTelegramListeners();
    setupNetworkListeners();
    setupUpdateListeners();
}
