import { apiFetch } from "./api.js";
import { showToast } from "./ui.js";
import { loadBbrStatus } from "./dashboard.js";
import { t } from "./i18n.js";
import { loadHysteriaCoreInfo, loadHysteriaLogs, setupHysteriaListeners } from "./hysteria.js";
import { loadOutbounds, loadRoutingRules, setupRoutingListeners } from "./routing.js";
import { setupSslListeners } from "./modules/ssl.js";
import { switchTab, currentTab } from "./modules/router.js";
import { setupSettingsListeners, loadSettings } from "./modules/settings-ui.js";
import { setupInboundListeners, loadInbounds, toggleInbound, deleteInbound, openEditInboundModal } from "./inbound-modal.js";
import { setupClientListeners, openClientsModal, setLoadInboundsCallback } from "./clients.js";

import { loadXrayConfig, setupXrayConfigListeners } from "./modules/xray-config.js";
import { loadCoreInfo, loadLogs, setupXrayCoreListeners, setupGeoListeners } from "./modules/xray-core.js";
import { setupSingboxCoreListeners } from "./modules/singbox/core.js";
import { openGlobalTrafficDetailsModal } from "./modules/dashboard/traffic_modal.js";

export async function initPanel() {
    // Expose functions to window scope for HTML inline events compatibility
    window.openClientsModal = openClientsModal;
    window.deleteInbound = deleteInbound;
    window.toggleInbound = toggleInbound;
    window.openEditInboundModal = openEditInboundModal;
    window.openGlobalTrafficDetailsModal = openGlobalTrafficDetailsModal;

    setupAuthorizedEventListeners();
    setLoadInboundsCallback(loadInbounds);

    const initialDataPromise = switchTab("dashboard", loadInbounds, loadCoreInfo, loadLogs);
    loadBbrStatus();
    startGlobalStatusPolling();

    // Загружаем имя администратора для отображения в сайдбаре
    const settingsPromise = (async () => {
        try {
            const res = await apiFetch("/api/settings");
            if (res && res.admin_username) {
                const navUser = document.getElementById("nav-username");
                if (navUser) navUser.innerText = res.admin_username;
            }
        } catch (e) {
            console.error("Failed to load admin username", e);
        }
    })();

    await Promise.all([initialDataPromise, settingsPromise]);
}

function setupAuthorizedEventListeners() {
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", () => switchTab(item.getAttribute("data-tab"), loadInbounds, loadCoreInfo, loadLogs));
    });
    
    document.getElementById("logout-btn").addEventListener("click", async () => {
        await apiFetch("/api/logout", { method: "POST" });
        location.reload();
    });
    
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".copy-btn");
        if (!btn) return;
        
        e.preventDefault();
        const targetId = btn.getAttribute("data-target");
        const element = document.getElementById(targetId);
        if (!element) return;
        
        let textToCopy = "";
        if (element.tagName === "INPUT" || element.tagName === "TEXTAREA") {
            element.select();
            textToCopy = element.value;
        } else {
            textToCopy = element.innerText || element.textContent;
        }
        
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(textToCopy);
        } else {
            document.execCommand("copy");
        }
        showToast(t("copied_to_clipboard", "Скопировано в буфер обмена!"));
    });
    
    document.addEventListener("click", (e) => {
        const closeBtn = e.target.closest ? e.target.closest(".close-modal-btn") : null;
        if (closeBtn) {
            const modal = closeBtn.closest(".modal");
            if (modal) modal.classList.remove("active");
        }

        const detailsBtn = e.target.closest ? e.target.closest("#btn-open-traffic-details, .open-traffic-details-btn") : null;
        if (detailsBtn) {
            e.preventDefault();
            openGlobalTrafficDetailsModal();
        }
    });

    setupSslListeners();
    setupSettingsListeners();
    setupInboundListeners(loadInbounds);
    setupClientListeners(loadInbounds);
    setupHysteriaListeners();
    setupRoutingListeners();
    
    // Bind split xray sub-listeners
    setupXrayCoreListeners();
    setupXrayConfigListeners();
    setupGeoListeners();
    setupSingboxCoreListeners();
}

function startGlobalStatusPolling() {
    setInterval(async () => {
        if (currentTab === "dashboard") return;
        
        try {
            const [xrayRes, hysteriaRes, singboxRes] = await Promise.all([
                apiFetch("/api/xray/status"),
                apiFetch("/api/hysteria/status"),
                apiFetch("/api/singbox/status")
            ]);
            
            if (xrayRes) {
                const badge = document.getElementById("xray-status-badge");
                const statusText = badge ? badge.querySelector(".status-text") : null;
                if (badge && statusText) {
                    if (xrayRes.running) {
                        badge.className = "status-badge running";
                        statusText.innerText = t("xray_status_active", "Xray: Активен");
                    } else {
                        badge.className = "status-badge stopped";
                        statusText.innerText = t("xray_status_stopped", "Xray: Остановлен");
                    }
                }
            }
            
            if (hysteriaRes) {
                const hBadge = document.getElementById("hysteria-status-badge");
                const hStatusText = hBadge ? hBadge.querySelector(".status-text") : null;
                if (hBadge && hStatusText) {
                    if (hysteriaRes.running) {
                        hBadge.className = "status-badge running";
                        hStatusText.innerText = t("hysteria_status_active", "Hysteria: Активен");
                    } else {
                        hBadge.className = "status-badge stopped";
                        hStatusText.innerText = t("hysteria_status_stopped", "Hysteria: Остановлен");
                    }
                }
            }

            if (singboxRes) {
                const sBadge = document.getElementById("singbox-status-badge");
                const sStatusText = sBadge ? sBadge.querySelector(".status-text") : null;
                if (sBadge && sStatusText) {
                    if (singboxRes.running) {
                        sBadge.className = "status-badge running";
                        sStatusText.innerText = t("singbox_status_active", "sing-box: Активен");
                    } else {
                        sBadge.className = "status-badge stopped";
                        sStatusText.innerText = t("singbox_status_stopped", "sing-box: Остановлен");
                    }
                }
            }
        } catch (e) {
            console.error("Global status poll failed", e);
        }
    }, 5000);
}
