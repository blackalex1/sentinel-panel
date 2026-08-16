import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadXrayConfig } from "./config.js";

import { initCustomSelect } from "../../components/customSelect.js";

export async function loadCoreInfo() {
    const currEl = document.getElementById("core-curr-version");
    const latestEl = document.getElementById("core-latest-version");

    // Instantly display cached versions if available to eliminate loading lag
    const cachedCurr = localStorage.getItem("xray_cached_curr_ver");
    const cachedLatest = localStorage.getItem("xray_cached_latest_ver");
    if (currEl && cachedCurr && currEl.innerText === "...") currEl.innerText = cachedCurr;
    if (latestEl && cachedLatest && latestEl.innerText === "...") latestEl.innerText = cachedLatest;

    const prereleaseToggle = document.getElementById("xray-prerelease-toggle");
    let includePrerelease = false;
    if (prereleaseToggle) {
        const savedState = localStorage.getItem("xray_include_prerelease");
        if (savedState !== null) {
            prereleaseToggle.checked = savedState === "true";
        }
        includePrerelease = prereleaseToggle.checked;
    }

    const versionUrl = includePrerelease ? "/api/xray/version?include_prerelease=true" : "/api/xray/version";
    const res = await apiFetch(versionUrl);
    if (!res || !res.success) return;
    
    if (currEl && res.current) {
        currEl.innerText = res.current;
        localStorage.setItem("xray_cached_curr_ver", res.current);
    }
    if (latestEl && res.latest) {
        latestEl.innerText = res.latest;
        localStorage.setItem("xray_cached_latest_ver", res.latest);
    }

    const prereleaseBadge = document.getElementById("core-prerelease-badge");
    const versionSelect = document.getElementById("core-version-select");
    const updateBtn = document.getElementById("core-update-btn");

    const normVer = (v) => (v || "").toString().trim().replace(/^v/i, "");

    if (res.versions && res.versions.length > 0 && versionSelect) {
        versionSelect.innerHTML = "";
        res.versions.forEach(item => {
            const opt = document.createElement("option");
            opt.value = item.download_url;
            opt.setAttribute("data-version", item.version);
            opt.setAttribute("data-prerelease", item.is_prerelease ? "true" : "false");
            const tag = item.is_prerelease ? "Pre-release" : "Stable";
            opt.innerText = `${item.version} (${tag})`;
            if (normVer(item.version) === normVer(res.current)) {
                opt.innerText += ` — [${t("core_installed_tag", "Установлено")}]`;
            }
            versionSelect.appendChild(opt);
        });

        if (!versionSelect.dataset.customSelectInit) {
            initCustomSelect(versionSelect);
        }

        const customContainer = versionSelect.closest(".custom-select-container");
        if (customContainer) {
            customContainer.style.display = "block";
        }

        const updateSelectedState = () => {
            const selectedOpt = versionSelect.options[versionSelect.selectedIndex];
            if (!selectedOpt) return;
            const selUrl = selectedOpt.value;
            const selVer = selectedOpt.getAttribute("data-version");
            const isPre = selectedOpt.getAttribute("data-prerelease") === "true";

            if (prereleaseBadge) {
                prereleaseBadge.style.display = "inline-block";
                if (isPre) {
                    prereleaseBadge.innerText = "Pre-release";
                    prereleaseBadge.style.background = "rgba(255, 171, 0, 0.15)";
                    prereleaseBadge.style.color = "#ffab00";
                    prereleaseBadge.style.borderColor = "rgba(255, 171, 0, 0.3)";
                } else {
                    prereleaseBadge.innerText = "Stable";
                    prereleaseBadge.style.background = "rgba(0, 230, 118, 0.15)";
                    prereleaseBadge.style.color = "#00e676";
                    prereleaseBadge.style.borderColor = "rgba(0, 230, 118, 0.3)";
                }
            }

            if (normVer(selVer) === normVer(res.current)) {
                updateBtn.disabled = true;
                updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>${t("xray_installed", "Установлено")}</span>`;
            } else {
                updateBtn.disabled = false;
                updateBtn.setAttribute("data-url", selUrl);
                updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span>${t("core_btn_install_version", "Установить")} ${selVer}</span>`;
            }
        };

        versionSelect.onchange = updateSelectedState;
        updateSelectedState();
    } else {
        const customContainer = versionSelect?.closest(".custom-select-container");
        if (customContainer) {
            customContainer.style.display = "none";
        }
        if (prereleaseBadge) {
            prereleaseBadge.style.display = res.is_prerelease ? "inline-block" : "none";
        }
        if (normVer(res.current) !== normVer(res.latest) && res.latest !== "Unknown" && res.download_url) {
            updateBtn.disabled = false;
            updateBtn.setAttribute("data-url", res.download_url);
            updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span>${t("xray_btn_update", "Обновить ядро")}</span>`;
        } else {
            updateBtn.disabled = true;
            updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>${t("xray_updated", "Обновлено")}</span>`;
        }
    }
    
    const statusRes = await apiFetch("/api/xray/status");
    if (statusRes) {
        const stopBtn = document.getElementById("core-stop-btn");
        if (stopBtn) {
            if (statusRes.running) {
                stopBtn.className = "btn danger-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-stop"></i> <span>${t("xray_btn_stop", "Остановить")}</span>`;
                stopBtn.setAttribute("data-action", "stop");
            } else {
                stopBtn.className = "btn success-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-play"></i> <span>${t("xray_btn_start", "Запустить")}</span>`;
                stopBtn.setAttribute("data-action", "start");
            }
        }
        
        const badge = document.getElementById("xray-status-badge");
        const statusText = badge ? badge.querySelector(".status-text") : null;
        if (badge && statusText) {
            if (statusRes.running) {
                badge.className = "status-badge running";
                statusText.innerText = t("xray_status_active", "Xray: Активен");
            } else {
                badge.className = "status-badge stopped";
                statusText.innerText = t("xray_status_stopped", "Xray: Остановлен");
            }
        }
    }
    
    await loadXrayConfig();
}

// ---------------------------------------------------------------------------
// SSE-based log streaming — replaces 2-second setInterval polling
// ---------------------------------------------------------------------------

const ANSI_RE = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;
const MAX_TERMINAL_LINES = 500;

function makeLogDiv(rawLine) {
    const div = document.createElement("div");
    const clean = rawLine.replace(ANSI_RE, "");
    div.innerText = clean;
    if (clean.includes("[Warning]"))    div.style.color = "var(--accent-orange)";
    else if (clean.includes("[Error]")) div.style.color = "var(--accent-rose)";
    else if (clean.includes("api:"))   div.style.color = "var(--accent-blue)";
    return div;
}

function appendToTerminal(terminal, lines) {
    const atBottom = terminal.scrollTop + terminal.clientHeight >= terminal.scrollHeight - 50;
    const frag = document.createDocumentFragment();
    lines.forEach(l => frag.appendChild(makeLogDiv(l)));
    terminal.appendChild(frag);
    while (terminal.childElementCount > MAX_TERMINAL_LINES) {
        terminal.removeChild(terminal.firstChild);
    }
    if (atBottom) terminal.scrollTop = terminal.scrollHeight;
}

let _xraySocket = null;
let _xrayES = null;
let _xrayReconnectTimer = null;
let _xrayReconnectDelay = 1000;

export async function loadLogs() {
    const terminal = document.getElementById("logs-terminal");
    if (!terminal) return;
    try {
        const res = await apiFetch("/api/xray/logs");
        if (res && res.success && Array.isArray(res.logs) && res.logs.length > 0) {
            terminal.innerHTML = "";
            appendToTerminal(terminal, res.logs);
        }
    } catch (_) {}
}

export function startLogsStream() {
    stopLogsStream();
    const terminal = document.getElementById("logs-terminal");
    if (!terminal) return;

    loadLogs();

    function connect() {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${proto}//${window.location.host}/api/xray/logs/ws`;

        try {
            const ws = new WebSocket(wsUrl);
            _xraySocket = ws;

            ws.onopen = () => {
                _xrayReconnectDelay = 1000;
            };

            ws.onmessage = (e) => {
                try {
                    const msg = JSON.parse(e.data);
                    if (msg.event === "history" && Array.isArray(msg.data)) {
                        terminal.innerHTML = "";
                        appendToTerminal(terminal, msg.data);
                    } else if (msg.event === "line" && msg.data) {
                        appendToTerminal(terminal, [msg.data]);
                    }
                } catch (_) {}
            };

            ws.onerror = () => {
                ws.close();
            };

            ws.onclose = (e) => {
                _xraySocket = null;
                if (e.code === 4401 || e.code === 1008) return;
                if (!_xrayES) {
                    connectSSE();
                }
            };
        } catch (_) {
            connectSSE();
        }
    }

    function connectSSE() {
        if (_xrayES) return;
        const es = new EventSource("/api/xray/logs/stream");
        _xrayES = es;

        es.addEventListener("history", (e) => {
            try {
                const lines = JSON.parse(e.data);
                if (Array.isArray(lines) && lines.length > 0) {
                    terminal.innerHTML = "";
                    appendToTerminal(terminal, lines);
                }
                _xrayReconnectDelay = 1000;
            } catch (_) {}
        });

        es.addEventListener("line", (e) => {
            try {
                appendToTerminal(terminal, [JSON.parse(e.data)]);
            } catch (_) {}
        });

        es.onerror = () => {
            es.close();
            _xrayES = null;
            _xrayReconnectDelay = Math.min(_xrayReconnectDelay * 2, 30000);
            _xrayReconnectTimer = setTimeout(connect, _xrayReconnectDelay);
        };
    }

    connect();
}

export function stopLogsStream() {
    if (_xrayReconnectTimer) { clearTimeout(_xrayReconnectTimer); _xrayReconnectTimer = null; }
    if (_xraySocket) { _xraySocket.close(); _xraySocket = null; }
    if (_xrayES) { _xrayES.close(); _xrayES = null; }
    _xrayReconnectDelay = 1000;
}

export function setupXrayCoreListeners() {
    const prereleaseToggle = document.getElementById("xray-prerelease-toggle");
    if (prereleaseToggle) {
        prereleaseToggle.addEventListener("change", () => {
            localStorage.setItem("xray_include_prerelease", prereleaseToggle.checked);
            loadCoreInfo();
        });
    }

    const restartBtn = document.getElementById("core-restart-btn");
    if (restartBtn) {
        restartBtn.addEventListener("click", async () => {
            const res = await apiFetch("/api/xray/action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "restart" })
            });
            if (res && res.success) showToast(t("xray_restarted", "Ядро Xray перезапущено"));
        });
    }
    
    const coreStopBtn = document.getElementById("core-stop-btn");
    if (coreStopBtn) {
        coreStopBtn.addEventListener("click", async () => {
            const action = coreStopBtn.getAttribute("data-action") || "stop";
            const res = await apiFetch("/api/xray/action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: action })
            });
            if (res && res.success) {
                if (action === "stop") {
                    showToast(t("xray_stopped_toast", "Ядро Xray остановлено"), "info");
                } else {
                    showToast(t("xray_started_toast", "Ядро Xray запущено"));
                }
                loadCoreInfo();
            }
        });
    }
    
    const updateBtn = document.getElementById("core-update-btn");
    if (updateBtn) {
        updateBtn.addEventListener("click", async () => {
            const url = updateBtn.getAttribute("data-url");
            if (!url) return;
            updateBtn.disabled = true;
            updateBtn.innerText = t("core_btn_updating", "Обновление...");
            showToast(t("xray_update_started", "Начался процесс обновления ядра Xray. Пожалуйста, подождите"), "info");
            const res = await apiFetch("/api/xray/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ download_url: url })
            });
            if (res && res.success) {
                showToast(t("xray_update_success", "Ядро успешно обновлено до версии {version}!").replace("{version}", res.version));
                loadCoreInfo();
            } else {
                showToast(res ? res.msg : t("xray_update_error", "Ошибка обновления ядра"), "error");
                loadCoreInfo();
            }
        });
    }

    const clearLogsBtn = document.getElementById("clear-logs-btn");
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener("click", async () => {
            const res = await apiFetch("/api/xray/logs/clear", { method: "POST" });
            if (res && res.success) {
                const terminal = document.getElementById("logs-terminal");
                if (terminal) terminal.innerHTML = "";
                showToast(t("logs_cleared", "Логи очищены"));
            } else {
                showToast(t("logs_clear_error", "Ошибка при очистке логов"), "error");
            }
        });
    }

    const copyLogsBtn = document.getElementById("copy-logs-btn");
    if (copyLogsBtn) {
        copyLogsBtn.addEventListener("click", () => {
            const terminal = document.getElementById("logs-terminal");
            if (terminal) {
                navigator.clipboard.writeText(terminal.innerText).then(() => {
                    showToast(t("logs_copied", "Логи скопированы в буфер обмена"));
                }).catch(() => {
                    showToast(t("logs_copy_error", "Не удалось скопировать логи"), "error");
                });
            }
        });
    }
}
