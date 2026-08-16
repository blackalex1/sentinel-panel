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
    
    if (tabId === "dashboard") {
        document.getElementById("current-tab-title").innerText = t("dashboard_title", "Мониторинг ресурсов");
        const p = Promise.all([
            loadStats(),
            loadGlobalTrafficChart(),
            loadDashboardClients()
        ]);
        statsInterval = setInterval(loadStats, 5000);
        return p;
    } else if (tabId === "inbounds") {
        document.getElementById("current-tab-title").innerText = t("inbounds_title", "Входящие подключения (Inbounds)");
        return loadInbounds();
    } else if (tabId === "xray") {
        document.getElementById("current-tab-title").innerText = t("xray_title", "Логи и управление ядром");
        startLogsStream();
        return Promise.all([loadCoreInfo(), loadLogs(), loadGeoInfo()]);
    } else if (tabId === "xray-config") {
        document.getElementById("current-tab-title").innerText = t("xray_config_title", "Конфигурация Xray");
        return loadXrayConfig();
    } else if (tabId === "hysteria") {
        document.getElementById("current-tab-title").innerText = t("hysteria_title", "Hysteria 2 - Управление");
        startHysteriaLogsStream();
        return Promise.all([loadHysteriaCoreInfo(), loadHysteriaLogs()]);
    } else if (tabId === "hysteria-config") {
        document.getElementById("current-tab-title").innerText = t("hysteria_config_title", "Конфигурация Hysteria 2");
        return loadHysteriaConfig();
    } else if (tabId === "singbox") {
        document.getElementById("current-tab-title").innerText = t("singbox_title", "sing-box - Управление");
        startSingboxLogsStream();
        return Promise.all([loadSingboxCoreInfo(), loadSingboxLogs()]);
    } else if (tabId === "singbox-config") {
        document.getElementById("current-tab-title").innerText = t("singbox_config_title", "Конфигурация sing-box");
        return loadSingboxConfig();
    } else if (tabId === "routing") {
        document.getElementById("current-tab-title").innerText = t("routing_title", "Маршрутизация");
        return Promise.all([loadOutbounds(), loadRoutingRules()]);
    } else if (tabId === "settings") {
        document.getElementById("current-tab-title").innerText = t("settings_title", "Настройки панели");
        return Promise.all([loadSettings(), loadOptimizationStatus()]);
    } else if (tabId === "audit-logs") {
        document.getElementById("current-tab-title").innerText = t("audit_logs_title", "Журнал аудита");
        return loadAuditLogs();
    }
}
