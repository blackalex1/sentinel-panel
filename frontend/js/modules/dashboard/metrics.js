import { apiFetch } from "../../api.js";
import { formatBytes } from "../../ui.js";
import { t } from "../../i18n.js";
import { updateChart, loadGlobalTrafficChart } from "./charts.js";
import { loadDashboardClients } from "./clients_table.js";
import { SentinelServerMascot } from "./mascot.js";

let lastNetUp = null;
let lastNetDown = null;
let lastStatsTime = null;
let serverMascotInstance = null;

export function initServerMascot() {
    if (!serverMascotInstance && document.getElementById("sentinelMascotCanvas")) {
        serverMascotInstance = new SentinelServerMascot("sentinelMascotCanvas", "sentinel-mascot-wrapper");
        serverMascotInstance.setOnClick(() => {
            loadStats();
        });
    }
    return serverMascotInstance;
}


export async function loadStats() {
    const res = await apiFetch("/panel/api/server/status");
    if (!res || !res.success) return;
    
    const obj = res.obj;
    
    // Render Xray status badge
    const badge = document.getElementById("xray-status-badge");
    const statusText = badge ? badge.querySelector(".status-text") : null;
    if (badge && statusText) {
        if (obj.xray.state === "running") {
            badge.className = "status-badge running";
            statusText.innerHTML = `<span data-i18n="xray_status_active">${t("xray_status_active")}</span>`;
            const stateEl = document.getElementById("sys-xray-state");
            if (stateEl) {
                stateEl.innerText = t("xray_state_running");
                stateEl.setAttribute("data-i18n", "xray_state_running");
            }
        } else {
            badge.className = "status-badge stopped";
            statusText.innerHTML = `<span data-i18n="xray_status_stopped">${t("xray_status_stopped")}</span>`;
            const stateEl = document.getElementById("sys-xray-state");
            if (stateEl) {
                stateEl.innerText = t("xray_state_stopped");
                stateEl.setAttribute("data-i18n", "xray_state_stopped");
            }
        }
    }
    
    // Render Hysteria status badge
    const hBadge = document.getElementById("hysteria-status-badge");
    const hStatusText = hBadge ? hBadge.querySelector(".status-text") : null;
    if (hBadge && hStatusText) {
        if (obj.hysteria.state === "running") {
            hBadge.className = "status-badge running";
            hStatusText.innerHTML = `<span data-i18n="hysteria_status_active">${t("hysteria_status_active")}</span>`;
            const stateEl = document.getElementById("sys-hysteria-state");
            if (stateEl) {
                stateEl.innerText = t("hysteria_state_running");
                stateEl.setAttribute("data-i18n", "hysteria_state_running");
            }
        } else {
            hBadge.className = "status-badge stopped";
            hStatusText.innerHTML = `<span data-i18n="hysteria_status_stopped">${t("hysteria_status_stopped")}</span>`;
            const stateEl = document.getElementById("sys-hysteria-state");
            if (stateEl) {
                stateEl.innerText = t("hysteria_state_stopped");
                stateEl.setAttribute("data-i18n", "hysteria_state_stopped");
            }
        }
    }
    
    // Metrics values
    const cpuVal = document.getElementById("cpu-value");
    if (cpuVal) cpuVal.innerText = `${obj.cpu.toFixed(1)}%`;
    
    const ramVal = document.getElementById("ram-value");
    const memCurrent = obj.mem.current / (1024**3);
    const memTotal = obj.mem.total / (1024**3);
    if (ramVal) ramVal.innerText = `${memCurrent.toFixed(1)} / ${memTotal.toFixed(1)} GB`;
    
    const swapVal = document.getElementById("swap-value");
    let swapPercent = 0;
    if (swapVal && obj.swap) {
        const swapCurrent = obj.swap.current / (1024**3);
        const swapTotal = obj.swap.total / (1024**3);
        swapVal.innerText = `${swapCurrent.toFixed(1)} / ${swapTotal.toFixed(1)} GB`;
        swapPercent = obj.swap.percent || 0;
    }
    
    const netUpVal = document.getElementById("net-up-value");
    if (netUpVal) netUpVal.innerText = formatBytes(obj.netIO.up);
    
    const netDownVal = document.getElementById("net-down-value");
    if (netDownVal) netDownVal.innerText = formatBytes(obj.netIO.down);
    
    let speedUp = 0;
    let speedDown = 0;
    const now = Date.now();
    if (lastNetUp !== null && lastNetDown !== null && lastStatsTime !== null) {
        const elapsedSeconds = (now - lastStatsTime) / 1000;
        if (elapsedSeconds > 0) {
            const diffUp = obj.netIO.up - lastNetUp;
            const diffDown = obj.netIO.down - lastNetDown;
            speedUp = diffUp >= 0 ? diffUp / elapsedSeconds : 0;
            speedDown = diffDown >= 0 ? diffDown / elapsedSeconds : 0;
            
            const netSpeedUpValUsage = document.getElementById("net-speed-up-value-usage");
            if (netSpeedUpValUsage) netSpeedUpValUsage.innerText = `${formatBytes(speedUp)}/s`;
            
            const netSpeedDownValUsage = document.getElementById("net-speed-down-value-usage");
            if (netSpeedDownValUsage) netSpeedDownValUsage.innerText = `${formatBytes(speedDown)}/s`;
        }
    }

    lastNetUp = obj.netIO.up;
    lastNetDown = obj.netIO.down;
    lastStatsTime = now;
    
    const diskVal = document.getElementById("disk-value");
    if (diskVal && obj.disk) {
        const diskCurrent = obj.disk.current / (1024**3);
        const diskTotal = obj.disk.total / (1024**3);
        diskVal.innerText = `${diskCurrent.toFixed(1)} / ${diskTotal.toFixed(1)} GB`;
    }
    
    // Uptime and version
    const hours = Math.floor(obj.uptime / 3600);
    const minutes = Math.floor((obj.uptime % 3600) / 60);
    const uptimeEl = document.getElementById("sys-uptime");
    if (uptimeEl) uptimeEl.innerText = t("uptime_format", "{hours}ч {minutes}м").replace("{hours}", hours).replace("{minutes}", minutes);
    
    const xrayVerEl = document.getElementById("sys-xray-version");
    if (xrayVerEl) xrayVerEl.innerText = obj.xray.version;
    
    const hysteriaVerEl = document.getElementById("sys-hysteria-version");
    if (hysteriaVerEl) hysteriaVerEl.innerText = obj.hysteria.version;

    if (obj.singbox) {
        const sbStateEl = document.getElementById("sys-singbox-state");
        if (sbStateEl) {
            const isRunning = obj.singbox.state === "running";
            sbStateEl.innerText = isRunning ? t("singbox_state_running") : t("singbox_state_stopped");
            sbStateEl.setAttribute("data-i18n", isRunning ? "singbox_state_running" : "singbox_state_stopped");
            sbStateEl.style.color = isRunning ? "var(--accent-green)" : "var(--accent-rose)";
        }
        const sbVerEl = document.getElementById("sys-singbox-version");
        if (sbVerEl) sbVerEl.innerText = obj.singbox.version || "—";
    }
    
    if (obj.bbr !== undefined) {
        renderBbrStatus(obj.bbr.enabled);
    }
    
    const sysIpEl = document.getElementById("sys-ip");
    if (sysIpEl) sysIpEl.innerText = window.location.hostname;
    
    // Count active cores
    let activeCores = 0;
    if (obj.xray && obj.xray.state === "running") activeCores++;
    if (obj.hysteria && obj.hysteria.state === "running") activeCores++;
    if (obj.singbox && obj.singbox.state === "running") activeCores++;

    const isAnyCoreRunning = activeCores > 0;

    // Update Mascot Engine
    const mascot = initServerMascot();
    if (mascot) {
        mascot.setRunningState(isAnyCoreRunning);
        mascot.setMetrics(obj.cpu, (memCurrent / memTotal) * 100, (typeof speedUp !== 'undefined' ? speedUp : 0), (typeof speedDown !== 'undefined' ? speedDown : 0));
    }

    // Update Mascot UI telemetry badges
    const mascotStatusPill = document.getElementById("mascot-status-pill");
    const mascotStatusText = document.getElementById("mascot-status-text");
    const mascotActiveCores = document.getElementById("mascot-active-cores");
    const mascotLoadLevel = document.getElementById("mascot-load-level");

    if (mascotStatusPill && mascotStatusText) {
        if (isAnyCoreRunning) {
            mascotStatusPill.className = mascotStatusPill.classList.contains("sidebar-mascot-badge") ? "sidebar-mascot-badge" : "mascot-status-pill";
            mascotStatusText.innerText = t("mascot_status_online", "ONLINE");
        } else {
            mascotStatusPill.className = (mascotStatusPill.classList.contains("sidebar-mascot-badge") ? "sidebar-mascot-badge" : "mascot-status-pill") + " standby";
            mascotStatusText.innerText = t("mascot_status_standby", "STANDBY");
        }
    }


    if (mascotActiveCores) {
        const specificKey = `mascot_cores_active_${activeCores}`;
        const translated = t(specificKey);
        if (translated && translated !== specificKey) {
            mascotActiveCores.innerText = translated;
        } else {
            mascotActiveCores.innerText = t("mascot_cores_active", "{count} ЯДРА АКТИВНО").replace("{count}", activeCores);
        }
    }


    if (mascotLoadLevel) {
        if (obj.cpu > 75) {
            mascotLoadLevel.innerText = t("mascot_load_high", "HIGH");
            mascotLoadLevel.style.color = "var(--accent-rose)";
        } else {
            mascotLoadLevel.innerText = t("mascot_load_normal", "NORMAL");
            mascotLoadLevel.style.color = "var(--text-primary)";
        }
    }

    // Update chart
    updateChart(obj.cpu, (memCurrent / memTotal) * 100, swapPercent, obj.disk ? obj.disk.percent : 0);
}


export function renderBbrStatus(bbrEnabled) {
    const bbrEl = document.getElementById("sys-bbr");
    const enableBtn = document.getElementById("enable-bbr-btn");
    if (!bbrEl) return;

    if (bbrEnabled) {
        bbrEl.innerText = t("bbr_status_active");
        bbrEl.setAttribute("data-i18n", "bbr_status_active");
        bbrEl.style.color = "var(--accent-green)";
        if (enableBtn) enableBtn.style.display = "none";
    } else {
        bbrEl.innerText = t("bbr_status_disabled");
        bbrEl.setAttribute("data-i18n", "bbr_status_disabled");
        bbrEl.style.color = "var(--accent-rose)";
        if (enableBtn) enableBtn.style.display = "inline-block";
    }
}

export async function loadBbrStatus() {
    const bbrRes = await apiFetch("/api/system/bbr");
    if (bbrRes && bbrRes.success) {
        renderBbrStatus(bbrRes.bbr_enabled);
    } else {
        const bbrEl = document.getElementById("sys-bbr");
        const enableBtn = document.getElementById("enable-bbr-btn");
        if (bbrEl) {
            bbrEl.innerText = t("bbr_status_error");
            bbrEl.setAttribute("data-i18n", "bbr_status_error");
            bbrEl.style.color = "var(--accent-rose)";
        }
        if (enableBtn) enableBtn.style.display = "none";
    }
}
