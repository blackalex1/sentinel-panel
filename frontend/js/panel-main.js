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
import { initServerMascot } from "./modules/dashboard/metrics.js";

export async function initPanel() {
    // Expose functions to window scope for HTML inline events compatibility
    window.openClientsModal = openClientsModal;
    window.deleteInbound = deleteInbound;
    window.toggleInbound = toggleInbound;
    window.openEditInboundModal = openEditInboundModal;
    window.openGlobalTrafficDetailsModal = openGlobalTrafficDetailsModal;

    setupAuthorizedEventListeners();
    setLoadInboundsCallback(loadInbounds);
    initServerMascot();

    const initialDataPromise = switchTab("dashboard", loadInbounds, loadCoreInfo, loadLogs);
    loadBbrStatus();


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
        showToast(t("copied_to_clipboard"));
    });
    
    document.addEventListener("click", (e) => {
        const closeBtn = e.target.closest ? e.target.closest(".close-modal-btn") : null;
        if (closeBtn) {
            const modal = closeBtn.closest(".modal");
            if (modal) modal.classList.remove("active");
        }

        const detailsBtn = e.target.closest ? e.target.closest("#btn-open-traffic-details, .open-traffic-details-btn") : null;
        if (detailsBtn) {
            import("./modules/traffic/modal.js").then(m => m.openTrafficDetailsModal());
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

