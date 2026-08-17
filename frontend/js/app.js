import { getCsrfToken, setCsrfToken, apiFetch } from "./api.js";
import { showToast, loadComponent } from "./ui.js";
import { initI18n, t } from "./i18n.js";

const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) {
    tg.ready();
    tg.expand();
}

// Запуск инициализации приложения сразу
(async () => {
    try {
        setupLoginListener();
        
        // Parallelize i18n initialization and auth check in one wave
        const [_, isAuth] = await Promise.all([
            initI18n(),
            checkSessionAuth()
        ]);
        
        if (isAuth) {
            await startPanel();
        } else {
            const loadingOverlay = document.getElementById("loading-overlay");
            const loginOverlay = document.getElementById("login-overlay");
            if (loadingOverlay) loadingOverlay.classList.remove("active");
            if (loginOverlay) loginOverlay.classList.add("active");
        }
    } catch (e) {
        console.error("Critical app initialization error:", e);
        if (window.onerror) {
            window.onerror(e.message || String(e), "app.js", 0, 0, e);
        }
    }
})();

async function checkSessionAuth() {
    // 1. Telegram WebApp Authorization
    if (tg && tg.initData) {
        const loadingText = document.getElementById("loading-text");
        if (loadingText) loadingText.innerText = t("loading_auth_telegram", "Авторизация в Telegram...");
        const res = await apiFetch("/api/auth/telegram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ initData: tg.initData })
        });
        
        if (res && res.success) {
            setCsrfToken(res.token);
            showToast(t("tg_auth_success", "Авторизация Telegram успешна!"));
            return true;
        }
        return false;
    }
    
    // 2. Regular Browser Cookie Session Authorization
    const csrfRes = await apiFetch("/csrf-token");
    if (csrfRes && csrfRes.success) {
        setCsrfToken(csrfRes.obj);
        return true;
    }
    return false;
}

import { loadedComponents } from "./ui.js";
import { translatePage } from "./i18n.js";

const COMPONENT_MANIFEST = [
    // Base tabs and main modals
    { id: "tab-dashboard", path: "components/dashboard.html", target: ".content-area" },
    { id: "tab-inbounds", path: "components/inbounds.html", target: ".content-area" },
    { id: "tab-xray", path: "components/xray.html", target: ".content-area" },
    { id: "tab-hysteria", path: "components/hysteria.html", target: ".content-area" },
    { id: "tab-singbox", path: "components/singbox.html", target: ".content-area" },
    { id: "tab-routing", path: "components/routing.html", target: ".content-area" },
    { id: "tab-settings", path: "components/settings.html", target: ".content-area" },
    { id: "inbound-modal", path: "components/inbound-modal.html", target: "body" },
    { id: "clients-modal", path: "components/clients-modal.html", target: "body" },
    { id: "client-modal", path: "components/client-modal.html", target: "body" },
    { id: "links-modal", path: "components/links-modal.html", target: "body" },
    { id: "json-modal", path: "components/json-modal.html", target: "body" },
    { id: "global-traffic-modal", path: "components/global-traffic-modal.html", target: "body" },

    // Settings sections
    { id: "sec-security", path: "components/settings/security.html", target: ".settings-sections-content" },
    { id: "sec-network", path: "components/settings/network.html", target: ".settings-sections-content" },
    { id: "sec-telegram", path: "components/settings/telegram.html", target: ".settings-sections-content" },
    { id: "sec-system", path: "components/settings/system.html", target: ".settings-sections-content" },
    { id: "sec-backups", path: "components/settings/backups.html", target: ".settings-sections-content" },
    { id: "sec-logs", path: "components/settings/logs.html", target: ".settings-sections-content" },

    // Routing components
    { id: "routing-quick-security", path: "components/routing/quick-security-rules.html", target: "#routing-quick-security-container" },
    { id: "routing-rules-table", path: "components/routing/routing-rules-table.html", target: "#routing-rules-table-container" },
    { id: "routing-outbounds-table", path: "components/routing/outbounds-table.html", target: "#routing-outbounds-table-container" },
    { id: "routing-preset-import-modal-wrapper", path: "components/routing/preset-import-modal.html", target: "#routing-modals-container" },
    { id: "routing-outbound-modal-wrapper", path: "components/routing/outbound-modal.html", target: "#routing-modals-container" },
    { id: "routing-rule-modal-wrapper", path: "components/routing/routing-rule-modal.html", target: "#routing-modals-container" }
];

async function loadAuthorizedComponents() {
    const loadingOverlay = document.getElementById("loading-overlay");
    const loadingText = document.getElementById("loading-text");
    if (loadingOverlay) loadingOverlay.classList.add("active");
    if (loadingText) loadingText.innerText = t("loading_components", "Загрузка компонентов...");
    
    const BUNDLE_STORAGE_KEY = "sentinel_comp_bundle_v60";
    let bundle = null;

    // Clear any obsolete bundle versions from session storage
    try {
        for (let i = sessionStorage.length - 1; i >= 0; i--) {
            const k = sessionStorage.key(i);
            if (k && k.startsWith("sentinel_comp_bundle") && k !== BUNDLE_STORAGE_KEY) {
                sessionStorage.removeItem(k);
            }
        }
        const cached = sessionStorage.getItem(BUNDLE_STORAGE_KEY);
        if (cached) {
            bundle = JSON.parse(cached);
        }
    } catch (e) {}

    if (!bundle) {
        try {
            const res = await apiFetch(`/api/components/bundle?t=${Date.now()}`);
            if (res && res.success && res.components) {
                bundle = res.components;
                try {
                    sessionStorage.setItem(BUNDLE_STORAGE_KEY, JSON.stringify(bundle));
                } catch (e) {}
            }
        } catch (e) {
            console.warn("Bundle fetch failed, falling back to parallel fetch:", e);
        }
    }

    if (bundle) {
        for (const item of COMPONENT_MANIFEST) {
            if (loadedComponents.has(item.id)) continue;
            const html = bundle[item.path];
            if (html) {
                const target = document.querySelector(item.target);
                if (target) {
                    target.insertAdjacentHTML("beforeend", html);
                    loadedComponents.add(item.id);
                }
            }
        }
    } else {
        const htmlMap = {};
        await Promise.all(COMPONENT_MANIFEST.map(async (item) => {
            try {
                const r = await fetch(item.path);
                if (r.ok) htmlMap[item.path] = await r.text();
            } catch (e) {}
        }));
        for (const item of COMPONENT_MANIFEST) {
            if (loadedComponents.has(item.id)) continue;
            const html = htmlMap[item.path];
            if (html) {
                const target = document.querySelector(item.target);
                if (target) {
                    target.insertAdjacentHTML("beforeend", html);
                    loadedComponents.add(item.id);
                }
            }
        }
    }

    try {
        translatePage();
    } catch (e) {}
}

async function loadPanelStylesheets() {
    return Promise.resolve();
}

import { enhanceAllSelects } from "./components/customSelect.js";

async function startPanel() {
    try {
        // Load HTML templates and main JS modules in parallel
        const [_, { initPanel }] = await Promise.all([
            loadAuthorizedComponents(),
            import("./panel-main.js")
        ]);
        
        // Populate initial dashboard data before revealing so nothing flashes empty (with 3.5s max wait)
        await Promise.race([
            initPanel(),
            new Promise(resolve => setTimeout(resolve, 3500))
        ]);
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
                    if (errorDiv) errorDiv.innerText = t("login_ip_blocked", "Этот IP-адрес был заблокирован.");
                    if (btnBack) btnBack.click();
                } else if (res.status === "expired") {
                    clearInterval(tg2faPollInterval);
                    tg2faPollInterval = null;
                    if (errorDiv) errorDiv.innerText = t("login_time_expired", "Время подтверждения входа истекло.");
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
