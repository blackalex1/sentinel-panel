import { getCsrfToken, setCsrfToken, apiFetch } from "./api.js";
import { showToast, loadComponent } from "./ui.js";
import { initI18n, t } from "./i18n.js";

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) {
    tg.ready();
    tg.expand();
}

// Запуск инициализации приложения сразу (так как type="module" выполняется после парсинга DOM)
(async () => {
    try {
        await initI18n();
        setupLoginListener();
        await initApp();
    } catch (e) {
        console.error("Critical app initialization error:", e);
        if (window.onerror) {
            window.onerror(e.message || String(e), "app.js", 0, 0, e);
        }
    }
})();

async function initApp() {
    document.getElementById("loading-overlay").classList.add("active");
    
    // 1. Telegram WebApp Authorization
    if (tg && tg.initData) {
        document.getElementById("loading-text").innerText = "Авторизация в Telegram...";
        const res = await apiFetch("/api/auth/telegram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ initData: tg.initData })
        });
        
        if (res && res.success) {
            setCsrfToken(res.token);
            showToast(t("tg_auth_success", "Авторизация Telegram успешна!"));
            await startPanel();
        } else {
            document.getElementById("loading-overlay").classList.remove("active");
            showToast(res ? res.msg : t("tg_auth_error", "Ошибка проверки подписи"), "error");
            document.getElementById("login-overlay").classList.add("active");
        }
        return;
    }
    
    // 2. Regular Browser Cookie Session Authorization
    const csrfRes = await apiFetch("/csrf-token");
    if (csrfRes && csrfRes.success) {
        setCsrfToken(csrfRes.obj);
        await startPanel();
    } else {
        document.getElementById("loading-overlay").classList.remove("active");
        document.getElementById("login-overlay").classList.add("active");
    }
}

async function loadAuthorizedComponents() {
    const loadingOverlay = document.getElementById("loading-overlay");
    const loadingText = document.getElementById("loading-text");
    if (loadingOverlay) loadingOverlay.classList.add("active");
    if (loadingText) loadingText.innerText = t("loading_components", "Загрузка компонентов...");
    
    // Загружаем все компоненты интерфейса параллельно только после успешной авторизации
    await Promise.all([
        loadComponent("tab-dashboard", "components/dashboard.html", ".content-area"),
        loadComponent("tab-inbounds", "components/inbounds.html", ".content-area"),
        loadComponent("tab-xray", "components/xray.html", ".content-area"),
        loadComponent("tab-hysteria", "components/hysteria.html", ".content-area"),
        loadComponent("tab-singbox", "components/singbox.html", ".content-area"),
        loadComponent("tab-routing", "components/routing.html", ".content-area"),
        loadComponent("tab-settings", "components/settings.html", ".content-area"),
        loadComponent("inbound-modal", "components/inbound-modal.html", "body"),
        loadComponent("clients-modal", "components/clients-modal.html", "body"),
        loadComponent("client-modal", "components/client-modal.html", "body"),
        loadComponent("links-modal", "components/links-modal.html", "body"),
        loadComponent("json-modal", "components/json-modal.html", "body"),
        loadComponent("global-traffic-modal", "components/global-traffic-modal.html", "body")
    ]);

    // Загружаем секции настроек
    await Promise.all([
        loadComponent("sec-security", "components/settings/security.html", ".settings-sections-content"),
        loadComponent("sec-network", "components/settings/network.html", ".settings-sections-content"),
        loadComponent("sec-telegram", "components/settings/telegram.html", ".settings-sections-content"),
        loadComponent("sec-system", "components/settings/system.html", ".settings-sections-content"),
        loadComponent("sec-backups", "components/settings/backups.html", ".settings-sections-content"),
        loadComponent("sec-logs", "components/settings/logs.html", ".settings-sections-content")
    ]);

    // Загружаем вкладки модального окна инбаундов
    await Promise.all([
        loadComponent("ib-tab-panel-basic", "components/inbound_modal/tab-basic.html", "#inbound-form-tabs-container"),
        loadComponent("ib-tab-panel-protocol", "components/inbound_modal/tab-protocol.html", "#inbound-form-tabs-container"),
        loadComponent("ib-tab-panel-stream", "components/inbound_modal/tab-stream.html", "#inbound-form-tabs-container"),
        loadComponent("ib-tab-panel-security", "components/inbound_modal/tab-security.html", "#inbound-form-tabs-container"),
        loadComponent("ib-tab-panel-sniffing", "components/inbound_modal/tab-sniffing.html", "#inbound-form-tabs-container"),
        loadComponent("ib-tab-panel-advanced", "components/inbound_modal/tab-advanced.html", "#inbound-form-tabs-container")
    ]);

    // Загружаем компоненты и модальные окна маршрутизации
    await Promise.all([
        loadComponent("routing-quick-security", "components/routing/quick-security-rules.html", "#routing-quick-security-container"),
        loadComponent("routing-rules-table", "components/routing/routing-rules-table.html", "#routing-rules-table-container"),
        loadComponent("routing-outbounds-table", "components/routing/outbounds-table.html", "#routing-outbounds-table-container"),
        loadComponent("routing-preset-import-modal-wrapper", "components/routing/preset-import-modal.html", "#routing-modals-container"),
        loadComponent("routing-outbound-modal-wrapper", "components/routing/outbound-modal.html", "#routing-modals-container"),
        loadComponent("routing-rule-modal-wrapper", "components/routing/routing-rule-modal.html", "#routing-modals-container")
    ]);
}

async function loadPanelStylesheets() {
    const sheets = [
        "css/pages/dashboard.css",
        "css/pages/inbounds.css",
        "css/pages/settings.css",
        "css/pages/routing.css"
    ];
    await Promise.all(sheets.map(href => {
        return new Promise((resolve) => {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = href + "?v=upgrade_7";
            link.onload = resolve;
            link.onerror = resolve; // Продолжить даже при ошибке
            document.head.appendChild(link);
        });
    }));
}

import { enhanceAllSelects } from "./components/customSelect.js";

async function startPanel() {
    try {
        await Promise.all([
            loadAuthorizedComponents(),
            loadPanelStylesheets()
        ]);
        
        // Dynamically import admin logic only after successful authorization
        const { initPanel } = await import("./panel-main.js");
        await initPanel();
        enhanceAllSelects();
    } catch (err) {
        console.error("Error starting panel:", err);
    } finally {
        const loadingOverlay = document.getElementById("loading-overlay");
        const loginOverlay = document.getElementById("login-overlay");
        const appContainer = document.getElementById("app-container");
        if (loadingOverlay) loadingOverlay.classList.remove("active");
        if (loginOverlay) loginOverlay.classList.remove("active");
        if (appContainer) appContainer.classList.add("active");
    }
}

let tg2faPollInterval = null;

function startTg2faPolling(token) {
    if (tg2faPollInterval) {
        clearInterval(tg2faPollInterval);
    }
    const errorDiv = document.getElementById("login-error");
    const tgMsgDiv = document.getElementById("login-tg-2fa-message");
    const btnBack = document.getElementById("btn-login-2fa-back");

    tg2faPollInterval = setInterval(async () => {
        try {
            const res = await apiFetch(`/api/auth/tg-2fa/poll?token=${token}`);
            if (res) {
                if (res.status === "approved") {
                    clearInterval(tg2faPollInterval);
                    tg2faPollInterval = null;
                    const csrfRes = await apiFetch("/csrf-token");
                    if (csrfRes && csrfRes.success) {
                        setCsrfToken(csrfRes.obj);
                    }
                    await startPanel();
                } else if (res.status === "blocked") {
                    clearInterval(tg2faPollInterval);
                    tg2faPollInterval = null;
                    if (errorDiv) errorDiv.innerText = "Этот IP-адрес был заблокирован.";
                    if (btnBack) btnBack.click();
                } else if (res.status === "expired") {
                    clearInterval(tg2faPollInterval);
                    tg2faPollInterval = null;
                    if (errorDiv) errorDiv.innerText = "Время подтверждения входа истекло.";
                    if (btnBack) btnBack.click();
                }
            }
        } catch (e) {
            console.error("Polling error:", e);
        }
    }, 2000);
}

function setupLoginListener() {
    const loginForm = document.getElementById("login-form");
    const credentialsGroup = document.getElementById("login-credentials-group");
    const faGroup = document.getElementById("login-2fa-group");
    const btnBack = document.getElementById("btn-login-2fa-back");
    const totpInput = document.getElementById("login-totp-code");
    const totpGroup = document.getElementById("login-totp-group");
    const tgMsgDiv = document.getElementById("login-tg-2fa-message");
    
    let is2faState = false;
    let cachedUsername = "";
    let cachedPassword = "";
    let currentTgToken = "";

    if (btnBack) {
        btnBack.addEventListener("click", () => {
            is2faState = false;
            if (tg2faPollInterval) {
                clearInterval(tg2faPollInterval);
                tg2faPollInterval = null;
            }
            if (credentialsGroup) credentialsGroup.style.display = "block";
            if (faGroup) faGroup.style.display = "none";
            if (btnBack) btnBack.style.display = "none";
            if (totpInput) totpInput.value = "";
            if (tgMsgDiv) tgMsgDiv.style.display = "none";
            if (totpGroup) totpGroup.style.display = "block";
            const errorDiv = document.getElementById("login-error");
            if (errorDiv) errorDiv.innerText = "";
        });
    }

    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const errorDiv = document.getElementById("login-error");
            if (errorDiv) errorDiv.innerText = "";
            
            let payload = {};
            
            if (!is2faState) {
                const usernameInput = document.getElementById("username");
                const passwordInput = document.getElementById("password");
                const username = usernameInput ? usernameInput.value.trim() : "";
                const password = passwordInput ? passwordInput.value : "";
                
                if (!username || !password) {
                    if (errorDiv) errorDiv.innerText = t("login_empty_fields", "Введите логин и пароль");
                    return;
                }
                
                cachedUsername = username;
                cachedPassword = password;
                payload = { username, password };
            } else {
                const code = totpInput ? totpInput.value.trim() : "";
                if (!code || code.length !== 6 || isNaN(code)) {
                    if (errorDiv) errorDiv.innerText = t("login_empty_2fa_code", "Введите 6-значный код");
                    return;
                }
                payload = { username: cachedUsername, password: cachedPassword, code };
                if (currentTgToken) {
                    payload.token = currentTgToken;
                }
            }
            
            const res = await apiFetch("/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            if (res && res.success) {
                if (res.requires_2fa) {
                    is2faState = true;
                    if (credentialsGroup) credentialsGroup.style.display = "none";
                    if (faGroup) faGroup.style.display = "block";
                    if (btnBack) btnBack.style.display = "block";
                    
                    if (res.type === "tg_2fa") {
                        if (totpGroup) totpGroup.style.display = "none";
                        if (tgMsgDiv) tgMsgDiv.style.display = "block";
                        currentTgToken = res.token;
                        startTg2faPolling(res.token);
                    } else if (res.type === "both") {
                        if (totpGroup) totpGroup.style.display = "block";
                        if (tgMsgDiv) tgMsgDiv.style.display = "block";
                        if (totpInput) totpInput.focus();
                        currentTgToken = res.token;
                        startTg2faPolling(res.token);
                    } else {
                        if (totpGroup) totpGroup.style.display = "block";
                        if (tgMsgDiv) tgMsgDiv.style.display = "none";
                        if (totpInput) totpInput.focus();
                        currentTgToken = "";
                    }
                } else {
                    if (tg2faPollInterval) {
                        clearInterval(tg2faPollInterval);
                        tg2faPollInterval = null;
                    }
                    const csrfRes = await apiFetch("/csrf-token");
                    if (csrfRes && csrfRes.success) {
                        setCsrfToken(csrfRes.obj);
                    }
                    await startPanel();
                }
            } else {
                if (errorDiv) {
                    errorDiv.innerText = res ? res.msg : t("login_failed", "Не удалось авторизоваться");
                }
            }
        });
    }
}
