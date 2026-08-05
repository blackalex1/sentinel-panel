import { loadStats } from "../dashboard.js";
import { loadHysteriaCoreInfo, loadHysteriaLogs, loadHysteriaConfig } from "../hysteria.js";
import { loadSingboxCoreInfo, loadSingboxLogs } from "./singbox/core.js";
import { loadSingboxConfig } from "./singbox/config.js";
import { loadXrayConfig } from "./xray-config.js";
import { loadOutbounds, loadRoutingRules } from "../routing.js";
import { loadSettings, loadOptimizationStatus } from "./settings-ui.js";
import { loadAuditLogs } from "./audit-logs.js";
import { loadGeoInfo } from "./xray-core.js";
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
        loadStats();
        setTimeout(loadStats, 1500);
        statsInterval = setInterval(loadStats, 5000);
    } else if (tabId === "inbounds") {
        document.getElementById("current-tab-title").innerText = t("inbounds_title", "Входящие подключения (Inbounds)");
        loadInbounds();
    } else if (tabId === "xray") {
        document.getElementById("current-tab-title").innerText = t("xray_title", "Логи и управление ядром");
        loadCoreInfo();
        loadGeoInfo();
        loadXrayConfig();
        loadLogs();
        logsInterval = setInterval(loadLogs, 2000);
    } else if (tabId === "hysteria") {
        document.getElementById("current-tab-title").innerText = t("hysteria_title", "Логи и управление ядром Hysteria");
        loadHysteriaCoreInfo();
        loadHysteriaConfig();
        loadHysteriaLogs();
        logsInterval = setInterval(loadHysteriaLogs, 2000);
    } else if (tabId === "singbox") {
        document.getElementById("current-tab-title").innerText = t("singbox_title", "Логи и управление ядром sing-box");
        loadSingboxCoreInfo();
        loadSingboxConfig();
        loadSingboxLogs();
        logsInterval = setInterval(loadSingboxLogs, 2000);
    } else if (tabId === "routing") {
        document.getElementById("current-tab-title").innerText = t("routing_title", "Маршрутизация и правила трафика");
        loadOutbounds();
        loadRoutingRules();
    } else if (tabId === "settings") {
        document.getElementById("current-tab-title").innerText = t("settings_title", "Системные настройки");
        loadSettings();
        loadAuditLogs();
        loadOptimizationStatus();
    }
}
