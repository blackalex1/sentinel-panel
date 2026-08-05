import { apiFetch } from "../../api.js";
import { t } from "../../i18n.js";

export async function loadWarpStatus() {
    const installedBadge = document.getElementById("settings-warp-installed-badge");
    const statusBadge = document.getElementById("settings-warp-status-badge");
    const accountBadge = document.getElementById("settings-warp-account-badge");
    const quotaBadge = document.getElementById("settings-warp-quota-badge");
    const statusRow = document.getElementById("settings-warp-status-row");
    const accountRow = document.getElementById("settings-warp-account-row");
    const quotaRow = document.getElementById("settings-warp-quota-row");
    const installBtn = document.getElementById("btn-warp-install");
    const configPanel = document.getElementById("settings-warp-config-panel");
    const licenseInput = document.getElementById("settings-warp-license");
    const registerFreeBtn = document.getElementById("btn-warp-register-free");
    
    if (!installedBadge) return;
    
    const res = await apiFetch("/api/system/warp/status");
    if (res) {
        if (res.installed) {
            installedBadge.innerText = t("settings_warp_badge_installed", "Установлен");
            installedBadge.className = "badge success-badge";
            installedBadge.style.background = "rgba(46, 213, 115, 0.15)";
            installedBadge.style.color = "#2ed573";
            
            if (installBtn) installBtn.style.display = "none";
            if (configPanel) configPanel.style.display = "flex";
            if (statusRow) statusRow.style.display = "flex";
            if (accountRow) accountRow.style.display = "flex";
            
            if (res.connected) {
                if (statusBadge) {
                    statusBadge.innerText = t("settings_warp_badge_connected", "Подключен");
                    statusBadge.className = "badge success-badge";
                    statusBadge.style.background = "rgba(46, 213, 115, 0.15)";
                    statusBadge.style.color = "#2ed573";
                }
                
                const btnConnect = document.getElementById("btn-warp-connect");
                const btnDisconnect = document.getElementById("btn-warp-disconnect");
                if (btnConnect) btnConnect.style.display = "none";
                if (btnDisconnect) btnDisconnect.style.display = "block";
            } else {
                if (statusBadge) {
                    statusBadge.innerText = t("settings_warp_badge_disconnected", "Отключен");
                    statusBadge.className = "badge warning-badge";
                    statusBadge.style.background = "rgba(255, 165, 2, 0.15)";
                    statusBadge.style.color = "#ffa502";
                }
                
                const btnConnect = document.getElementById("btn-warp-connect");
                const btnDisconnect = document.getElementById("btn-warp-disconnect");
                if (btnConnect) btnConnect.style.display = "block";
                if (btnDisconnect) btnDisconnect.style.display = "none";
            }
            
            const isPlus = res.type === "plus";
            if (accountBadge) {
                accountBadge.innerText = isPlus ? "WARP+" : "Free";
                accountBadge.className = isPlus ? "badge success-badge" : "badge secondary-badge";
                if (isPlus) {
                    accountBadge.style.background = "rgba(52, 152, 219, 0.15)";
                    accountBadge.style.color = "#3498db";
                } else {
                    accountBadge.style.background = "rgba(255, 255, 255, 0.05)";
                    accountBadge.style.color = "var(--text-secondary)";
                }
            }
            
            // Handle quota display
            if (isPlus) {
                if (quotaRow) quotaRow.style.display = "flex";
                if (quotaBadge) {
                    if (res.quota > 0) {
                        const totalGb = (res.quota / (1024 * 1024 * 1024)).toFixed(1);
                        const remainingBytes = Math.max(0, res.quota - res.usage);
                        const remainingGb = (remainingBytes / (1024 * 1024 * 1024)).toFixed(1);
                        quotaBadge.innerText = `${remainingGb} GB / ${totalGb} GB`;
                    } else {
                        quotaBadge.innerText = t("settings_warp_quota_unlimited", "Безлимитно");
                    }
                    quotaBadge.className = "badge success-badge";
                    quotaBadge.style.background = "rgba(52, 152, 219, 0.15)";
                    quotaBadge.style.color = "#3498db";
                }
            } else {
                if (quotaRow) quotaRow.style.display = "none";
            }
            
            if (registerFreeBtn) {
                registerFreeBtn.style.display = isPlus ? "block" : "none";
            }
            
            if (licenseInput) {
                licenseInput.value = res.license || "";
            }
            
            window.warpDependentRules = res.dependent_rules || [];
        } else {
            installedBadge.innerText = t("settings_warp_badge_not_installed", "Не установлен");
            installedBadge.className = "badge warning-badge";
            installedBadge.style.background = "rgba(255, 165, 2, 0.15)";
            installedBadge.style.color = "#ffa502";
            
            if (installBtn) installBtn.style.display = "block";
            if (configPanel) configPanel.style.display = "none";
            if (statusRow) statusRow.style.display = "none";
            if (accountRow) accountRow.style.display = "none";
            if (quotaRow) quotaRow.style.display = "none";
            
            window.warpDependentRules = [];
        }
    }
}
