import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadSettings } from "./core.js";

export async function loadActiveSessions() {
    const tbody = document.getElementById("active-sessions-tbody");
    if (!tbody) return;
    
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center;"><i class="fa-solid fa-spinner fa-spin"></i> ${t("sessions_loading", "Loading sessions...")}</td></tr>`;
    
    const res = await apiFetch("/api/security/sessions");
    if (res && res.success) {
        if (!res.sessions || res.sessions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center;">${t("sessions_not_found", "No active sessions found")}</td></tr>`;
            return;
        }
        
        tbody.innerHTML = "";
        res.sessions.forEach(s => {
            const tr = document.createElement("tr");
            
            const created = new Date(s.created_at * 1000).toLocaleString();
            const expires = new Date(s.expires_at * 1000).toLocaleString();
            
            let deviceText = s.user_agent;
            // Simple parsing to make User Agent user-friendly
            if (s.user_agent.includes("Windows")) {
                deviceText = "Windows / ";
            } else if (s.user_agent.includes("Macintosh")) {
                deviceText = "macOS / ";
            } else if (s.user_agent.includes("Linux")) {
                deviceText = "Linux / ";
            } else if (s.user_agent.includes("iPhone")) {
                deviceText = "iPhone / ";
            } else if (s.user_agent.includes("Android")) {
                deviceText = "Android / ";
            } else {
                deviceText = "";
            }
            
            if (s.user_agent.includes("Chrome")) {
                deviceText += "Chrome";
            } else if (s.user_agent.includes("Firefox")) {
                deviceText += "Firefox";
            } else if (s.user_agent.includes("Safari")) {
                deviceText += "Safari";
            } else if (s.user_agent.includes("Edge")) {
                deviceText += "Edge";
            } else if (s.user_agent.includes("Opera")) {
                deviceText += "Opera";
            } else {
                deviceText += s.user_agent.split(" ")[0] || "Unknown Client";
            }
            
            // Highlight current device
            const currentBadge = s.is_current ? ` <span class="badge success-badge" style="font-size: 10px; background: rgba(46, 213, 115, 0.15); color: #2ed573; padding: 2px 6px; margin-left: 6px;">${t("sessions_this_device", "This device")}</span>` : '';
            
            // Terminate button
            const actionHtml = s.is_current 
                ? `<span style="color: var(--text-secondary); font-size: 13px;">${t("sessions_current_session", "Current session")}</span>` 
                : `<button class="btn danger-btn btn-terminate-session" data-id="${s.session_id}" style="padding: 4px 8px; font-size: 12px; height: auto;"><i class="fa-solid fa-right-from-bracket"></i> ${t("sessions_btn_terminate", "Terminate")}</button>`;
            
            tr.innerHTML = `
                <td style="white-space: nowrap;"><strong>${s.ip_address}</strong>${currentBadge}</td>
                <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${s.user_agent}">${deviceText}</td>
                <td style="white-space: nowrap;">${created}</td>
                <td style="white-space: nowrap;">${expires}</td>
                <td style="text-align: right; white-space: nowrap;">${actionHtml}</td>
            `;
            tbody.appendChild(tr);
        });
        
        // Add click listener for terminate buttons
        document.querySelectorAll(".btn-terminate-session").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const sid = e.currentTarget.getAttribute("data-id");
                if (!confirm(t("sessions_confirm_terminate", "Are you sure you want to terminate this session?"))) return;
                
                const deleteRes = await apiFetch("/api/security/sessions/terminate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ session_id: sid })
                });
                
                if (deleteRes && deleteRes.success) {
                    showToast(t("sessions_terminated_success", "Session terminated successfully!"));
                    loadActiveSessions();
                } else {
                    showToast(deleteRes ? deleteRes.msg : t("sessions_terminate_error", "Failed to terminate session"), "error");
                }
            });
        });
    } else {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--danger-color);">${t("sessions_load_error", "Failed to load active sessions")}</td></tr>`;
    }
}

export function setupSecurityListeners() {
    // Смена логина и пароля
    const btnSaveCredentials = document.getElementById("btn-save-credentials");
    if (btnSaveCredentials) {
        btnSaveCredentials.addEventListener("click", async () => {
            const currentPassword = document.getElementById("setting-cred-current-pwd").value;
            const newUsername = document.getElementById("setting-cred-new-user").value.trim();
            const newPassword = document.getElementById("setting-cred-new-pwd").value;
            const confirmPassword = document.getElementById("setting-cred-confirm-pwd").value;

            if (!currentPassword) {
                showToast(t("settings_current_password_required", "Введите текущий пароль"), "error");
                return;
            }
            if (!newUsername) {
                showToast(t("settings_new_username_required", "Введите новый логин"), "error");
                return;
            }
            if (newPassword && newPassword !== confirmPassword) {
                showToast(t("settings_passwords_mismatch", "Новые пароли не совпадают"), "error");
                return;
            }

            btnSaveCredentials.disabled = true;
            const res = await apiFetch("/api/settings/credentials", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    current_password: currentPassword,
                    new_username: newUsername,
                    new_password: newPassword || null
                })
            });
            btnSaveCredentials.disabled = false;

            if (res && res.success) {
                showToast(res.msg || t("settings_saved_toast", "Настройки успешно сохранены!"));
                document.getElementById("setting-cred-current-pwd").value = "";
                document.getElementById("setting-cred-new-pwd").value = "";
                document.getElementById("setting-cred-confirm-pwd").value = "";
                
                setTimeout(async () => {
                    await apiFetch("/api/logout", { method: "POST" });
                    window.location.reload();
                }, 2000);
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
            }
        });
    }

    // 2FA Setup Panel Trigger
    const btn2faSetupTrigger = document.getElementById("btn-2fa-setup-trigger");
    if (btn2faSetupTrigger) {
        btn2faSetupTrigger.addEventListener("click", async () => {
            const setupPanel = document.getElementById("2fa-setup-panel");
            const disablePanel = document.getElementById("2fa-disable-panel");
            if (!setupPanel) return;

            setupPanel.style.display = "flex";
            if (disablePanel) disablePanel.style.display = "none";

            const res = await apiFetch("/api/settings/2fa/setup");
            if (res && res.success) {
                document.getElementById("setting-2fa-secret").value = res.secret;
                const qrContainer = document.getElementById("2fa-qrcode");
                if (qrContainer) {
                    qrContainer.innerHTML = "";
                    new QRCode(qrContainer, {
                        text: res.qr_uri,
                        width: 160,
                        height: 160,
                        correctLevel: QRCode.CorrectLevel.M
                    });
                }
            } else {
                showToast(res ? res.msg : "Не удалось настроить 2FA", "error");
                setupPanel.style.display = "none";
            }
        });
    }

    // 2FA Enable Confirmation
    const btn2faConfirm = document.getElementById("btn-2fa-confirm");
    if (btn2faConfirm) {
        btn2faConfirm.addEventListener("click", async () => {
            const codeInput = document.getElementById("setting-2fa-code-input");
            const code = codeInput ? codeInput.value.trim() : "";

            if (!code || code.length !== 6 || isNaN(code)) {
                showToast("Введите корректный 6-значный код", "error");
                return;
            }

            btn2faConfirm.disabled = true;
            const res = await apiFetch("/api/settings/2fa/enable", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });
            btn2faConfirm.disabled = false;

            if (res && res.success) {
                showToast(res.msg || "2FA успешно включена!");
                if (codeInput) codeInput.value = "";
                await loadSettings();
            } else {
                showToast(res ? res.msg : "Ошибка при включении 2FA", "error");
            }
        });
    }

    // 2FA Disable Trigger
    const btn2faDisableTrigger = document.getElementById("btn-2fa-disable-trigger");
    if (btn2faDisableTrigger) {
        btn2faDisableTrigger.addEventListener("click", () => {
            const setupPanel = document.getElementById("2fa-setup-panel");
            const disablePanel = document.getElementById("2fa-disable-panel");
            if (disablePanel) {
                disablePanel.style.display = "flex";
            }
            if (setupPanel) setupPanel.style.display = "none";
        });
    }

    // 2FA Disable Confirmation
    const btn2faDisableConfirm = document.getElementById("btn-2fa-disable-confirm");
    if (btn2faDisableConfirm) {
        btn2faDisableConfirm.addEventListener("click", async () => {
            const codeInput = document.getElementById("setting-2fa-disable-code-input");
            const code = codeInput ? codeInput.value.trim() : "";

            if (!code || code.length !== 6 || isNaN(code)) {
                showToast("Введите корректный 6-значный код", "error");
                return;
            }

            btn2faDisableConfirm.disabled = true;
            const res = await apiFetch("/api/settings/2fa/disable", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });
            btn2faDisableConfirm.disabled = false;

            if (res && res.success) {
                showToast(res.msg || "2FA успешно отключена!");
                if (codeInput) codeInput.value = "";
                await loadSettings();
            } else {
                showToast(res ? res.msg : "Ошибка при отключении 2FA", "error");
            }
        });
    }
}
