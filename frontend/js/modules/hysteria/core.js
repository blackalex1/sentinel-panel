import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadHysteriaConfig } from "./config.js";

export async function loadHysteriaCoreInfo() {
    const currEl = document.getElementById("hysteria-curr-version");
    const latestEl = document.getElementById("hysteria-latest-version");

    // Instantly display cached versions if available to eliminate loading lag
    const cachedCurr = localStorage.getItem("hysteria_cached_curr_ver");
    const cachedLatest = localStorage.getItem("hysteria_cached_latest_ver");
    if (currEl && cachedCurr && currEl.innerText === "...") currEl.innerText = cachedCurr;
    if (latestEl && cachedLatest && latestEl.innerText === "...") latestEl.innerText = cachedLatest;

    const prereleaseToggle = document.getElementById("hysteria-prerelease-toggle");
    let includePrerelease = false;
    if (prereleaseToggle) {
        const savedState = localStorage.getItem("hysteria_include_prerelease");
        if (savedState !== null) {
            prereleaseToggle.checked = savedState === "true";
        }
        includePrerelease = prereleaseToggle.checked;
    }

    const versionUrl = includePrerelease ? "/api/hysteria/version?include_prerelease=true" : "/api/hysteria/version";
    const res = await apiFetch(versionUrl);
    if (!res || !res.success) return;
    
    if (currEl && res.current) {
        currEl.innerText = res.current;
        localStorage.setItem("hysteria_cached_curr_ver", res.current);
    }
    if (latestEl && res.latest) {
        latestEl.innerText = res.latest;
        localStorage.setItem("hysteria_cached_latest_ver", res.latest);
    }

    const prereleaseBadge = document.getElementById("hysteria-prerelease-badge");
    const versionSelect = document.getElementById("hysteria-version-select");
    const updateBtn = document.getElementById("hysteria-update-btn");

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

        const customContainer = versionSelect.closest(".custom-select-container");
        if (customContainer) {
            customContainer.style.display = "block";
        } else {
            versionSelect.style.display = "none";
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
                updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>${t("hysteria_installed", "Установлено")}</span>`;
            } else {
                updateBtn.disabled = false;
                updateBtn.setAttribute("data-url", selUrl);
                updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span>${t("core_btn_install_version", "Установить")} ${selVer}</span>`;
            }
        };

        versionSelect.onchange = updateSelectedState;
        updateSelectedState();
    } else {
        if (prereleaseBadge) {
            prereleaseBadge.style.display = res.is_prerelease ? "inline-block" : "none";
        }
        if (normVer(res.current) !== normVer(res.latest) && res.latest !== "Unknown" && res.download_url) {
            updateBtn.disabled = false;
            updateBtn.setAttribute("data-url", res.download_url);
            updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span>${t("hysteria_btn_update", "Обновить ядро")}</span>`;
        } else {
            updateBtn.disabled = true;
            updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>${t("hysteria_updated", "Обновлено")}</span>`;
        }
    }
    
    const statusRes = await apiFetch("/api/hysteria/status");
    if (statusRes) {
        const stopBtn = document.getElementById("hysteria-stop-btn");
        if (stopBtn) {
            if (statusRes.running) {
                stopBtn.className = "btn danger-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-stop"></i> <span>${t("hysteria_btn_stop", "Остановить")}</span>`;
                stopBtn.setAttribute("data-action", "stop");
            } else {
                stopBtn.className = "btn success-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-play"></i> <span>${t("hysteria_btn_start", "Запустить")}</span>`;
                stopBtn.setAttribute("data-action", "start");
            }
        }
        
        // Update top-bar badge
        const hBadge = document.getElementById("hysteria-status-badge");
        const hStatusText = hBadge ? hBadge.querySelector(".status-text") : null;
        if (hBadge && hStatusText) {
            if (statusRes.running) {
                hBadge.className = "status-badge running";
                hStatusText.innerText = t("hysteria_status_active", "Hysteria: Активен");
            } else {
                hBadge.className = "status-badge stopped";
                hStatusText.innerText = t("hysteria_status_stopped", "Hysteria: Остановлен");
            }
        }
    }
    
    await loadHysteriaConfig();
}

let _hysteriaSocket = null;
let _hysteriaES = null;
let _hysteriaReconnectTimer = null;
let _hysteriaReconnectDelay = 1000;
let lastHysteriaLogsStr = "";

function appendHysteriaLines(terminal, lines) {
    const atBottom = terminal.scrollTop + terminal.clientHeight >= terminal.scrollHeight - 50;
    const frag = document.createDocumentFragment();
    lines.forEach(line => {
        const div = document.createElement("div");
        const cleanLine = (line || "").replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
        div.innerText = cleanLine;

        if (cleanLine.toLowerCase().includes("warn") || cleanLine.includes("[Warning]")) {
            div.style.color = "var(--accent-orange)";
        } else if (cleanLine.toLowerCase().includes("err") || cleanLine.includes("[Error]")) {
            div.style.color = "var(--accent-rose)";
        } else if (cleanLine.includes("connected") || cleanLine.includes("authenticate")) {
            div.style.color = "var(--accent-blue)";
        }

        frag.appendChild(div);
    });
    terminal.appendChild(frag);
    while (terminal.childElementCount > 300) {
        terminal.removeChild(terminal.firstChild);
    }
    if (atBottom) terminal.scrollTop = terminal.scrollHeight;
}

export async function loadHysteriaLogs() {
    const terminal = document.getElementById("hysteria-logs-terminal");
    if (!terminal) return;
    try {
        const res = await apiFetch("/api/hysteria/logs");
        if (res && res.success && Array.isArray(res.logs) && res.logs.length > 0) {
            terminal.innerHTML = "";
            appendHysteriaLines(terminal, res.logs);
        }
    } catch (_) {}
}

export function startHysteriaLogsStream() {
    stopHysteriaLogsStream();
    const terminal = document.getElementById("hysteria-logs-terminal");
    if (!terminal) return;

    loadHysteriaLogs();

    function connect() {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${proto}//${window.location.host}/api/hysteria/logs/ws`;

        try {
            const ws = new WebSocket(wsUrl);
            _hysteriaSocket = ws;

            ws.onopen = () => {
                _hysteriaReconnectDelay = 1000;
            };

            ws.onmessage = (e) => {
                try {
                    const msg = JSON.parse(e.data);
                    if (msg.event === "history" && Array.isArray(msg.data)) {
                        terminal.innerHTML = "";
                        appendHysteriaLines(terminal, msg.data);
                    } else if (msg.event === "line" && msg.data) {
                        appendHysteriaLines(terminal, [msg.data]);
                    }
                } catch (_) {}
            };

            ws.onerror = () => {
                ws.close();
            };

            ws.onclose = (e) => {
                _hysteriaSocket = null;
                if (e.code === 4401 || e.code === 1008) return;
                if (!_hysteriaES) {
                    connectSSE();
                }
            };
        } catch (_) {
            connectSSE();
        }
    }

    function connectSSE() {
        if (_hysteriaES) return;
        const es = new EventSource("/api/hysteria/logs/stream");
        _hysteriaES = es;

        es.addEventListener("history", (e) => {
            try {
                const lines = JSON.parse(e.data);
                if (Array.isArray(lines) && lines.length > 0) {
                    terminal.innerHTML = "";
                    appendHysteriaLines(terminal, lines);
                }
                _hysteriaReconnectDelay = 1000;
            } catch (_) {}
        });

        es.addEventListener("line", (e) => {
            try {
                appendHysteriaLines(terminal, [JSON.parse(e.data)]);
            } catch (_) {}
        });

        es.onerror = () => {
            es.close();
            _hysteriaES = null;
            _hysteriaReconnectDelay = Math.min(_hysteriaReconnectDelay * 2, 30000);
            _hysteriaReconnectTimer = setTimeout(connect, _hysteriaReconnectDelay);
        };
    }

    connect();
}

export function stopHysteriaLogsStream() {
    if (_hysteriaReconnectTimer) { clearTimeout(_hysteriaReconnectTimer); _hysteriaReconnectTimer = null; }
    if (_hysteriaSocket) { _hysteriaSocket.close(); _hysteriaSocket = null; }
    if (_hysteriaES) { _hysteriaES.close(); _hysteriaES = null; }
    _hysteriaReconnectDelay = 1000;
}

export function setupHysteriaCoreListeners() {
    const prereleaseToggle = document.getElementById("hysteria-prerelease-toggle");
    if (prereleaseToggle) {
        prereleaseToggle.addEventListener("change", () => {
            localStorage.setItem("hysteria_include_prerelease", prereleaseToggle.checked);
            loadHysteriaCoreInfo();
        });
    }

    const clearLogsBtn = document.getElementById("hysteria-clear-logs-btn");
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener("click", async () => {
            const res = await apiFetch("/api/hysteria/logs/clear", { method: "POST" });
            if (res && res.success) {
                lastHysteriaLogsStr = "[]";
                const terminal = document.getElementById("hysteria-logs-terminal");
                if (terminal) terminal.innerText = "";
                showToast(t("logs_cleared", "Логи очищены"));
            } else {
                showToast(t("logs_clear_error", "Ошибка при очистке логов"), "error");
            }
        });
    }

    const copyLogsBtn = document.getElementById("hysteria-copy-logs-btn");
    if (copyLogsBtn) {
        copyLogsBtn.addEventListener("click", () => {
            const terminal = document.getElementById("hysteria-logs-terminal");
            if (terminal) {
                const text = terminal.innerText;
                navigator.clipboard.writeText(text).then(() => {
                    showToast(t("logs_copied", "Логи скопированы в буфер обмена"));
                }).catch(err => {
                    showToast(t("logs_copy_error", "Не удалось скопировать логи"), "error");
                });
            }
        });
    }
    
    const restartBtn = document.getElementById("hysteria-restart-btn");
    if (restartBtn) {
        restartBtn.addEventListener("click", async () => {
            const res = await apiFetch("/api/hysteria/action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "restart" })
            });
            if (res && res.success) {
                showToast(t("hysteria_restarted", "Ядро Hysteria перезапущено"));
                loadHysteriaCoreInfo();
            }
        });
    }
    
    const stopBtn = document.getElementById("hysteria-stop-btn");
    if (stopBtn) {
        stopBtn.addEventListener("click", async () => {
            const action = stopBtn.getAttribute("data-action") || "stop";
            const res = await apiFetch("/api/hysteria/action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: action })
            });
            if (res && res.success) {
                if (action === "stop") {
                    showToast(t("hysteria_stopped_toast", "Ядро Hysteria остановлено"), "info");
                } else {
                    showToast(t("hysteria_started_toast", "Ядро Hysteria запущено"));
                }
                loadHysteriaCoreInfo();
            }
        });
    }
    
    const updateBtn = document.getElementById("hysteria-update-btn");
    if (updateBtn) {
        updateBtn.addEventListener("click", async () => {
            const url = updateBtn.getAttribute("data-url");
            if (!url) return;
            
            updateBtn.disabled = true;
            updateBtn.innerText = t("hysteria_updating", "Обновление...");
            showToast(t("hysteria_update_started", "Начался процесс обновления ядра Hysteria. Пожалуйста, подождите"), "info");
            
            const res = await apiFetch("/api/hysteria/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ download_url: url })
            });
            
            if (res && res.success) {
                showToast(t("hysteria_update_success", "Ядро успешно обновлено до версии {version}!").replace("{version}", res.version));
                loadHysteriaCoreInfo();
            } else {
                showToast(res ? res.msg : t("hysteria_update_error", "Ошибка обновления ядра"), "error");
                loadHysteriaCoreInfo();
            }
        });
    }
}
