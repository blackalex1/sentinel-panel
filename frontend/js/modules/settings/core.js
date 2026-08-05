import { apiFetch, getCsrfToken } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadWarpStatus, setupWarpListeners } from "../warp-ui.js";
import { loadAuditLogs, setupAuditLogsListeners } from "../audit-logs.js";
import { loadOptimizationStatus } from "./network.js";
import { loadActiveSessions } from "./security.js";

export let originalSecretPath = "";

export function setOriginalSecretPath(val) {
    originalSecretPath = val;
}

export async function loadSettings() {
    const setRes = await fetch("/api/settings", {
        headers: { "Authorization": `Bearer ${getCsrfToken()}` }
    });
    
    if (setRes.status === 200) {
        const setObj = await setRes.json();
        document.getElementById("setting-api-token").value = setObj.api_token;
        
        const secretPathInput = document.getElementById("setting-secret-path-input");
        if (secretPathInput) {
            secretPathInput.value = setObj.secret_path;
            originalSecretPath = setObj.secret_path;
        }
        
        const credNewUserInput = document.getElementById("setting-cred-new-user");
        if (credNewUserInput) {
            credNewUserInput.value = setObj.admin_username || "";
        }

        const navUsername = document.getElementById("nav-username");
        if (navUsername && setObj.admin_username) {
            navUsername.innerText = setObj.admin_username;
        }
        
        const badge2fa = document.getElementById("2fa-status-badge");
        const btnSetup2fa = document.getElementById("btn-2fa-setup-trigger");
        const btnDisable2fa = document.getElementById("btn-2fa-disable-trigger");
        const setupPanel2fa = document.getElementById("2fa-setup-panel");
        const disablePanel2fa = document.getElementById("2fa-disable-panel");

        if (badge2fa) {
            if (setObj.totp_enabled) {
                badge2fa.innerText = t("settings_2fa_enabled", "Включена");
                badge2fa.className = "badge success-badge";
                badge2fa.style.background = "rgba(46, 213, 115, 0.15)";
                badge2fa.style.color = "#2ed573";
                
                if (btnSetup2fa) btnSetup2fa.style.display = "none";
                if (btnDisable2fa) btnDisable2fa.style.display = "block";
            } else {
                badge2fa.innerText = t("settings_2fa_disabled", "Выключена");
                badge2fa.className = "badge warning-badge";
                badge2fa.style.background = "rgba(255, 165, 2, 0.15)";
                badge2fa.style.color = "#ffa502";
                
                if (btnSetup2fa) btnSetup2fa.style.display = "block";
                if (btnDisable2fa) btnDisable2fa.style.display = "none";
            }
            if (setupPanel2fa) setupPanel2fa.style.display = "none";
            if (disablePanel2fa) disablePanel2fa.style.display = "none";
        }
        
        const sessionTimeoutInput = document.getElementById("setting-session-timeout");
        if (sessionTimeoutInput) {
            sessionTimeoutInput.value = setObj.session_timeout_days !== undefined ? setObj.session_timeout_days : 7;
        }
        
        const loginMaxAttemptsInput = document.getElementById("setting-login-max-attempts");
        if (loginMaxAttemptsInput) {
            loginMaxAttemptsInput.value = setObj.login_max_attempts !== undefined ? setObj.login_max_attempts : 5;
        }
        
        const loginAttemptsPeriodInput = document.getElementById("setting-login-attempts-period");
        if (loginAttemptsPeriodInput) {
            loginAttemptsPeriodInput.value = setObj.login_attempts_period !== undefined ? setObj.login_attempts_period : 60;
        }
        
        const loginFailDelayInput = document.getElementById("setting-login-fail-delay");
        if (loginFailDelayInput) {
            loginFailDelayInput.value = setObj.login_fail_delay !== undefined ? setObj.login_fail_delay : 1.0;
        }
        
        const decoyType = setObj.decoy_type || "static";
        const decoyTypeSelect = document.getElementById("setting-decoy-type");
        if (decoyTypeSelect) {
            decoyTypeSelect.value = decoyType;
        }
        
        const decoyValueInput = document.getElementById("setting-decoy-value");
        if (decoyValueInput) {
            decoyValueInput.value = setObj.decoy_value || "";
        }
        
        // Load SSL fields
        const sslDomainInput = document.getElementById("setting-ssl-domain");
        if (sslDomainInput) {
            sslDomainInput.value = setObj.ssl_domain || "";
        }
        const sslEmailInput = document.getElementById("setting-ssl-email");
        if (sslEmailInput) {
            sslEmailInput.value = setObj.ssl_email || "";
        }
        const muxEnabledInput = document.getElementById("setting-mux-enabled");
        if (muxEnabledInput) {
            muxEnabledInput.checked = setObj.mux_enabled !== undefined ? setObj.mux_enabled : false;
        }
        const muxConcurrencyInput = document.getElementById("setting-mux-concurrency");
        if (muxConcurrencyInput) {
            muxConcurrencyInput.value = setObj.mux_concurrency !== undefined ? setObj.mux_concurrency : 8;
        }
        const muxXverInput = document.getElementById("setting-mux-xver");
        if (muxXverInput) {
            muxXverInput.checked = setObj.mux_xver !== undefined ? setObj.mux_xver : false;
        }
        // Load Telegram fields
        const telegramTokenInput = document.getElementById("setting-telegram-token");
        if (telegramTokenInput) {
            telegramTokenInput.value = setObj.telegram_bot_token || "";
        }
        const telegramAdminIdsInput = document.getElementById("setting-telegram-admin-ids");
        if (telegramAdminIdsInput) {
            telegramAdminIdsInput.value = setObj.telegram_admin_ids || "";
        }
        const telegram2faEnableInput = document.getElementById("setting-telegram-2fa-enable");
        if (telegram2faEnableInput) {
            telegram2faEnableInput.checked = setObj.telegram_2fa_enabled !== undefined ? setObj.telegram_2fa_enabled : false;
        }
        const telegramBotEnableInput = document.getElementById("setting-telegram-bot-enable");
        if (telegramBotEnableInput) {
            telegramBotEnableInput.checked = setObj.telegram_bot_enabled !== undefined ? setObj.telegram_bot_enabled : true;
        }
        const telegramClientEventsEnableInput = document.getElementById("setting-telegram-client-events-enable");
        if (telegramClientEventsEnableInput) {
            telegramClientEventsEnableInput.checked = setObj.telegram_client_events_enabled !== undefined ? setObj.telegram_client_events_enabled : true;
        }
        
        const backupEnableInput = document.getElementById("setting-backup-enable");
        if (backupEnableInput) {
            backupEnableInput.checked = setObj.backup_enable !== undefined ? setObj.backup_enable : false;
        }
        const backupRotationGroup = document.getElementById("setting-backup-rotation-group");
        if (backupRotationGroup) {
            backupRotationGroup.style.display = setObj.backup_enable ? "" : "none";
        }
        const backupTelegramInput = document.getElementById("setting-backup-telegram");
        if (backupTelegramInput) {
            backupTelegramInput.checked = setObj.backup_telegram !== undefined ? setObj.backup_telegram : false;
        }
        const backupIntervalSelect = document.getElementById("setting-backup-interval");
        if (backupIntervalSelect) {
            backupIntervalSelect.value = setObj.backup_interval || "daily";
        }
        const backupRotationInput = document.getElementById("setting-backup-rotation");
        if (backupRotationInput) {
            backupRotationInput.value = setObj.backup_rotation !== undefined ? setObj.backup_rotation : 7;
        }
        
        const backupEncryptInput = document.getElementById("setting-backup-encrypt");
        if (backupEncryptInput) {
            backupEncryptInput.checked = setObj.backup_encrypt !== undefined ? setObj.backup_encrypt : false;
            backupEncryptInput.dataset.initial = backupEncryptInput.checked;
        }
        const currPwd = document.getElementById("setting-backup-current-password");
        if (currPwd) currPwd.value = "";
        const newPwd = document.getElementById("setting-backup-new-password");
        if (newPwd) newPwd.value = "";
        const confirmPwd = document.getElementById("setting-backup-confirm-password");
        if (confirmPwd) confirmPwd.value = "";
        const backupPasswordGroup = document.getElementById("setting-backup-password-group");
        if (backupPasswordGroup) {
            backupPasswordGroup.style.display = setObj.backup_encrypt ? "block" : "none";
        }
        window.backupPasswordSet = setObj.backup_password_set || false;
        
        updateDecoyUI(decoyType);
        await loadWarpStatus();
        await loadAuditLogs();
        await loadOptimizationStatus();
        await loadActiveSessions();
    }
}

export function updateDecoyUI(decoyType) {
    const valGroup = document.getElementById("setting-decoy-value-group");
    const valLabel = document.getElementById("setting-decoy-value-label");
    const valDesc = document.getElementById("setting-decoy-value-desc");
    
    if (!valGroup) return;
    
    if (decoyType === "none") {
        valGroup.style.display = "none";
    } else {
        valGroup.style.display = "block";
        if (decoyType === "proxy") {
            if (valLabel) valLabel.innerText = "Адрес внешнего сайта (URL)";
            if (valDesc) valDesc.innerText = "Укажите полный адрес сайта для проксирования, включая протокол (например: https://github.com).";
        } else if (decoyType === "redirect") {
            if (valLabel) valLabel.innerText = "Адрес перенаправления (URL)";
            if (valDesc) valDesc.innerText = "Укажите полный URL-адрес внешнего сайта, на который будут перенаправляться все публичные запросы (например: https://google.com).";
        } else {
            if (valLabel) valLabel.innerText = "Имя шаблона заглушки";
            if (valDesc) valDesc.innerText = "Название HTML-файла шаблона в папке frontend/decoy/ (по умолчанию: company_landing).";
        }
    }
}

export function setupGeneralListeners() {
    const decoyTypeSelect = document.getElementById("setting-decoy-type");
    if (decoyTypeSelect) {
        decoyTypeSelect.addEventListener("change", (e) => {
            updateDecoyUI(e.target.value);
        });
    }

    // Card 1: Access Credentials Save
    const btnSaveAccess = document.getElementById("btn-save-access");
    if (btnSaveAccess) {
        btnSaveAccess.addEventListener("click", async () => {
            const secretPath = document.getElementById("setting-secret-path-input").value.trim();
            const sessionTimeoutInput = document.getElementById("setting-session-timeout");
            const sessionTimeout = sessionTimeoutInput ? parseInt(sessionTimeoutInput.value) : 7;
            const loginMaxAttemptsInput = document.getElementById("setting-login-max-attempts");
            const loginMaxAttempts = loginMaxAttemptsInput ? parseInt(loginMaxAttemptsInput.value) : 5;
            const loginAttemptsPeriodInput = document.getElementById("setting-login-attempts-period");
            const loginAttemptsPeriod = loginAttemptsPeriodInput ? parseInt(loginAttemptsPeriodInput.value) : 60;
            const loginFailDelayInput = document.getElementById("setting-login-fail-delay");
            const loginFailDelay = loginFailDelayInput ? parseFloat(loginFailDelayInput.value) : 1.0;

            if (!secretPath) {
                showToast(t("secret_path_empty", "Секретный путь не может быть пустым"), "error");
                return;
            }
            if (isNaN(sessionTimeout) || sessionTimeout <= 0) {
                showToast(t("settings_session_timeout_invalid", "Срок действия сессии должен быть целым положительным числом"), "error");
                return;
            }
            if (isNaN(loginMaxAttempts) || loginMaxAttempts <= 0) {
                showToast(t("settings_login_max_attempts_invalid", "Максимум попыток входа должен быть целым положительным числом"), "error");
                return;
            }
            if (isNaN(loginAttemptsPeriod) || loginAttemptsPeriod <= 0) {
                showToast(t("settings_login_attempts_period_invalid", "Период блокировки должен быть целым положительным числом секунд"), "error");
                return;
            }
            if (isNaN(loginFailDelay) || loginFailDelay < 0) {
                showToast(t("settings_login_fail_delay_invalid", "Задержка после неверного ввода должна быть неотрицательным числом секунд"), "error");
                return;
            }

            btnSaveAccess.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    secret_path: secretPath,
                    session_timeout_days: sessionTimeout,
                    login_max_attempts: loginMaxAttempts,
                    login_attempts_period: loginAttemptsPeriod,
                    login_fail_delay: loginFailDelay
                })
            });
            btnSaveAccess.disabled = false;

            if (res && res.success) {
                if (secretPath !== originalSecretPath) {
                    showToast(t("settings_saved_redirect", "Настройки сохранены! Перенаправление через 3 секунды..."), "info");
                    setTimeout(() => {
                        window.location.href = `/${secretPath}/`;
                    }, 3000);
                } else {
                    showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
                    loadSettings();
                }
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
            }
        });
    }

    // Card 3: Decoy Site Save
    const btnSaveDecoy = document.getElementById("btn-save-decoy");
    if (btnSaveDecoy) {
        btnSaveDecoy.addEventListener("click", async () => {
            const decoyType = document.getElementById("setting-decoy-type").value;
            const decoyValue = document.getElementById("setting-decoy-value").value.trim();

            btnSaveDecoy.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    decoy_type: decoyType,
                    decoy_value: decoyValue
                })
            });
            btnSaveDecoy.disabled = false;

            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
                loadSettings();
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
            }
        });
    }

    // Card 3: Decoy Site Preview
    const btnPreviewDecoy = document.getElementById("btn-preview-decoy");
    if (btnPreviewDecoy) {
        btnPreviewDecoy.addEventListener("click", () => {
            window.open(window.location.origin + "/", "_blank");
        });
    }

    // Card 4: SSL Settings Save
    const btnSaveSsl = document.getElementById("btn-save-ssl");
    if (btnSaveSsl) {
        btnSaveSsl.addEventListener("click", async () => {
            const sslDomain = document.getElementById("setting-ssl-domain").value.trim();
            const sslEmail = document.getElementById("setting-ssl-email").value.trim();

            btnSaveSsl.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ssl_domain: sslDomain,
                    ssl_email: sslEmail
                })
            });
            btnSaveSsl.disabled = false;

            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
                loadSettings();
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
            }
        });
    }

    // Card 4.5: Mux Settings Save
    const btnSaveMux = document.getElementById("btn-save-mux");
    if (btnSaveMux) {
        btnSaveMux.addEventListener("click", async () => {
            const muxEnabled = document.getElementById("setting-mux-enabled").checked;
            const muxConcurrencyInput = document.getElementById("setting-mux-concurrency");
            const muxConcurrency = muxConcurrencyInput ? parseInt(muxConcurrencyInput.value) : 8;
            const muxXver = document.getElementById("setting-mux-xver").checked;

            if (isNaN(muxConcurrency) || muxConcurrency <= 0) {
                showToast(t("invalid_mux_concurrency", "Неверный лимит соединений (должно быть целое положительное число)"), "error");
                return;
            }

            btnSaveMux.disabled = true;
            const res = await apiFetch("/api/settings/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    mux_enabled: muxEnabled,
                    mux_concurrency: muxConcurrency,
                    mux_xver: muxXver
                })
            });
            btnSaveMux.disabled = false;

            if (res && res.success) {
                showToast(t("settings_saved_toast", "Настройки успешно сохранены!"));
                loadSettings();
            } else {
                showToast(res ? res.msg : t("settings_save_error", "Не удалось сохранить настройки"), "error");
            }
        });
    }

    // Bind sub-modules listeners
    setupWarpListeners();
    setupAuditLogsListeners();

    // Инициализация переключения суб-вкладок настроек
    const navItems = document.querySelectorAll(".settings-nav-item");
    const sections = document.querySelectorAll(".settings-section-panel");
    navItems.forEach(item => {
        item.addEventListener("click", () => {
            const targetSection = item.getAttribute("data-settings-section");
            navItems.forEach(ni => ni.classList.remove("active"));
            sections.forEach(sec => sec.classList.remove("active"));
            item.classList.add("active");
            const targetEl = document.getElementById(`sec-${targetSection}`);
            if (targetEl) targetEl.classList.add("active");
        });
    });
}
