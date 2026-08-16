import { loadStats, loadGlobalTrafficChart, loadDashboardClients } from "../dashboard.js";
import { loadHysteriaCoreInfo, loadHysteriaLogs, loadHysteriaConfig, startHysteriaLogsStream, stopHysteriaLogsStream } from "../hysteria.js";
import { loadSingboxCoreInfo, loadSingboxLogs, startSingboxLogsStream, stopSingboxLogsStream } from "./singbox/core.js";
import { loadSingboxConfig } from "./singbox/config.js";
import { loadXrayConfig } from "./xray-config.js";
import { loadOutbounds, loadRoutingRules } from "../routing.js";
import { loadSettings, loadOptimizationStatus } from "./settings-ui.js";
import { loadAuditLogs } from "./audit-logs.js";
import { loadGeoInfo, startLogsStream, stopLogsStream } from "./xray-core.js";
import { t } from "../i18n.js";

export let currentTab = "dashboard";
let logsInterval = null;
let statsInterval = null;

export function updateCurrentTabTitle() {
    const titleEl = document.getElementById("current-tab-title");
    if (!titleEl) return;

    switch (currentTab) {
        case "dashboard":
            titleEl.innerText = t("dashboard_title", "Мониторинг ресурсов");
            break;
        case "inbounds":
            titleEl.innerText = t("inbounds_title", "Входящие подключения (Inbounds)");
            break;
        case "xray":
            titleEl.innerText = t("xray_title", "Логи и управление ядром");
            break;
        case "xray-config":
            titleEl.innerText = t("xray_config_title", "Конфигурация Xray");
            break;
        case "hysteria":
            titleEl.innerText = t("hysteria_title", "Hysteria 2 - Управление");
            break;
        case "hysteria-config":
            titleEl.innerText = t("hysteria_config_title", "Конфигурация Hysteria 2");
            break;
        case "singbox":
            titleEl.innerText = t("singbox_title", "sing-box - Управление");
            break;
        case "singbox-config":
            titleEl.innerText = t("singbox_config_title", "Конфигурация sing-box");
            break;
        case "routing":
            titleEl.innerText = t("routing_title", "Маршрутизация");
            break;
        case "settings":
            titleEl.innerText = t("settings_title", "Настройки панели");
            break;
        case "audit-logs":
            titleEl.innerText = t("audit_logs_title", "Журнал аудита");
            break;
        default:
            break;
    }
}

export function switchTab(tabId, loadInbounds, loadCoreInfo, loadLogs) {
    currentTab = tabId;
    
    document.querySelectorAll(".nav-item").forEach(btn => {
        if (btn.getAttribute("data-tab") === tabId) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    
    document.querySelectorAll(".tab-content").forEach(content => {
        if (content.id === `tab-${tabId}`) {
            content.classList.add("active");
        } else {
            content.classList.remove("active");
        }
    });
    
    // Stop any active real-time SSE streams when switching tabs
    stopLogsStream();
    stopHysteriaLogsStream();
    stopSingboxLogsStream();

    if (logsInterval) {
        clearInterval(logsInterval);
        logsInterval = null;
    }
    
    if (statsInterval) {
        clearInterval(statsInterval);
        statsInterval = null;
    }

    updateCurrentTabTitle();
    
    if (tabId === "dashboard") {
        const p = Promise.all([
            loadStats(),
            loadGlobalTrafficChart(),
            loadDashboardClients()
        ]);
        statsInterval = setInterval(loadStats, 5000);
        return p;
    } else if (tabId === "inbounds") {
        return loadInbounds();
    } else if (tabId === "xray") {
        startLogsStream();
        return Promise.all([loadCoreInfo(), loadLogs(), loadGeoInfo()]);
    } else if (tabId === "xray-config") {
        return loadXrayConfig();
    } else if (tabId === "hysteria") {
        startHysteriaLogsStream();
        return Promise.all([loadHysteriaCoreInfo(), loadHysteriaLogs()]);
    } else if (tabId === "hysteria-config") {
        return loadHysteriaConfig();
    } else if (tabId === "singbox") {
        startSingboxLogsStream();
        return Promise.all([loadSingboxCoreInfo(), loadSingboxLogs()]);
    } else if (tabId === "singbox-config") {
        return loadSingboxConfig();
    } else if (tabId === "routing") {
        return Promise.all([loadOutbounds(), loadRoutingRules()]);
    } else if (tabId === "settings") {
        return Promise.all([loadSettings(), loadOptimizationStatus()]);
    } else if (tabId === "audit-logs") {
        return loadAuditLogs();
    }
}
