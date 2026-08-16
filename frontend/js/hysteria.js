import {
    loadHysteriaCoreInfo as coreInfo,
    loadHysteriaLogs as coreLogs,
    startHysteriaLogsStream as coreStartLogsStream,
    stopHysteriaLogsStream as coreStopLogsStream,
    setupHysteriaCoreListeners
} from "./modules/hysteria-core.js";
import { loadHysteriaConfig as configLoader, setupHysteriaConfigListeners } from "./modules/hysteria-config.js";

export async function loadHysteriaCoreInfo() {
    return await coreInfo();
}

export async function loadHysteriaLogs() {
    return await coreLogs();
}

export function startHysteriaLogsStream() {
    return coreStartLogsStream();
}

export function stopHysteriaLogsStream() {
    return coreStopLogsStream();
}

export async function loadHysteriaConfig(preferredIndex = 0) {
    return await configLoader(preferredIndex);
}

export function setupHysteriaListeners() {
    setupHysteriaCoreListeners();
    setupHysteriaConfigListeners();
}
