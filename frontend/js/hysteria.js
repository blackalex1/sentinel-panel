import { loadHysteriaCoreInfo as coreInfo, loadHysteriaLogs as coreLogs, setupHysteriaCoreListeners } from "./modules/hysteria-core.js";
import { loadHysteriaConfig as configLoader, setupHysteriaConfigListeners } from "./modules/hysteria-config.js";

export async function loadHysteriaCoreInfo() {
    return await coreInfo();
}

export async function loadHysteriaLogs() {
    return await coreLogs();
}

export async function loadHysteriaConfig(preferredIndex = 0) {
    return await configLoader(preferredIndex);
}

export function setupHysteriaListeners() {
    setupHysteriaCoreListeners();
    setupHysteriaConfigListeners();
}
