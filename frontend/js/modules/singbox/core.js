import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadSingboxConfig, setupSingboxConfigListeners } from "./config.js";

export { loadSingboxConfig };

export async function loadSingboxCoreInfo() {
    const currElem = document.getElementById("singbox-curr-version");
    const latestElem = document.getElementById("singbox-latest-version");

    // Instantly display cached versions if available to eliminate loading lag
    const cachedCurr = localStorage.getItem("singbox_cached_curr_ver");
    const cachedLatest = localStorage.getItem("singbox_cached_latest_ver");
    if (currElem && cachedCurr && currElem.innerText === "...") currElem.innerText = cachedCurr;
    if (latestElem && cachedLatest && latestElem.innerText === "...") latestElem.innerText = cachedLatest;

    const prereleaseToggle = document.getElementById("singbox-prerelease-toggle");
    let includePrerelease = false;
    if (prereleaseToggle) {
        const savedState = localStorage.getItem("singbox_include_prerelease");
        if (savedState !== null) {
            prereleaseToggle.checked = savedState === "true";
        }
        includePrerelease = prereleaseToggle.checked;
    }

    const versionUrl = includePrerelease ? "/api/singbox/version?include_prerelease=true" : "/api/singbox/version";
    const res = await apiFetch(versionUrl);
    if (!res || !res.success) return;

    if (currElem && res.current) {
        currElem.innerText = res.current;
        localStorage.setItem("singbox_cached_curr_ver", res.current);
    }

    if (latestElem && res.latest) {
        latestElem.innerText = res.latest;
        localStorage.setItem("singbox_cached_latest_ver", res.latest);
    }

    const prereleaseBadge = document.getElementById("singbox-prerelease-badge");
    const versionSelect = document.getElementById("singbox-version-select");
    const updateBtn = document.getElementById("singbox-update-btn");

    const normVer = (v) => (v || "").toString().trim().replace(/^v/i, "");

    if (res.versions && res.versions.length > 0 && versionSelect) {
        versionSelect.innerHTML = "";
        res.versions.forEach(item => {
            const opt = document.createElement("option");
            opt.value = item.download_url;
            opt.setAttribute("data-version", item.version);
            opt.setAttribute("data-prerelease", item.is_prerelease ? "true" : "false");
            const tag = item.is_prerelease ? t("tag_prerelease") : t("tag_stable");
            opt.innerText = `${item.version} (${tag})`;
            if (normVer(item.version) === normVer(res.current)) {
                opt.innerText += ` — [${t("core_installed_tag")}]`;
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
                    prereleaseBadge.innerText = t("tag_prerelease");
                    prereleaseBadge.style.background = "rgba(255, 171, 0, 0.15)";
                    prereleaseBadge.style.color = "#ffab00";
                    prereleaseBadge.style.borderColor = "rgba(255, 171, 0, 0.3)";
                } else {
                    prereleaseBadge.innerText = t("tag_stable");
                    prereleaseBadge.style.background = "rgba(0, 230, 118, 0.15)";
                    prereleaseBadge.style.color = "#00e676";
                    prereleaseBadge.style.borderColor = "rgba(0, 230, 118, 0.3)";
                }
            }

            if (normVer(selVer) === normVer(res.current)) {
                updateBtn.disabled = true;
                updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span data-i18n="singbox_installed">${t("singbox_installed")}</span>`;
            } else {
                updateBtn.disabled = false;
                updateBtn.setAttribute("data-url", selUrl);
                updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span>${t("core_btn_install_version").replace("{version}", selVer)}</span>`;
            }
        };

        versionSelect.onchange = updateSelectedState;
        updateSelectedState();
    } else {
        if (prereleaseBadge) {
            prereleaseBadge.style.display = res.is_prerelease ? "inline-block" : "none";
        }
        if (updateBtn) {
            if (normVer(res.current) !== normVer(res.latest) && res.latest !== "Unknown" && res.download_url) {
                updateBtn.disabled = false;
                updateBtn.setAttribute("data-url", res.download_url);
                updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span data-i18n="singbox_btn_update">${t("singbox_btn_update")}</span>`;
            } else {
                updateBtn.disabled = true;
                updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span data-i18n="singbox_updated">${t("singbox_updated")}</span>`;
            }
        }
    }

    const statusRes = await apiFetch("/api/singbox/status");
    if (statusRes) {
        const stopBtn = document.getElementById("singbox-stop-btn");
        if (stopBtn) {
            if (statusRes.running) {
                stopBtn.className = "btn danger-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-stop"></i> <span data-i18n="singbox_btn_stop">${t("singbox_btn_stop")}</span>`;
                stopBtn.setAttribute("data-action", "stop");
            } else {
                stopBtn.className = "btn success-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-play"></i> <span data-i18n="singbox_btn_start">${t("singbox_btn_start")}</span>`;
                stopBtn.setAttribute("data-action", "start");
            }
        }

        const badge = document.getElementById("singbox-status-badge");
        const statusText = badge ? badge.querySelector(".status-text") : null;
        if (badge && statusText) {
            if (statusRes.running) {
                badge.className = "status-badge running";
                statusText.innerHTML = `<span data-i18n="singbox_status_active">${t("singbox_status_active")}</span>`;
            } else {
                badge.className = "status-badge stopped";
                statusText.innerHTML = `<span data-i18n="singbox_status_stopped">${t("singbox_status_stopped")}</span>`;
            }
        }
    }

    await loadSingboxConfig();
}

let _singboxSocket = null;
let _singboxES = null;
let _singboxReconnectTimer = null;
let _singboxReconnectDelay = 1000;
let lastSingboxLogsStr = "";

function appendSingboxLines(terminal, lines) {
    const atBottom = terminal.scrollTop + terminal.clientHeight >= terminal.scrollHeight - 50;
    const frag = document.createDocumentFragment();
    lines.forEach(line => {
        const div = document.createElement("div");
        const cleanLine = (line || "").replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
        div.innerText = cleanLine;

        if (cleanLine.includes("[WARN]") || cleanLine.includes("warning")) div.style.color = "var(--accent-orange)";
        else if (cleanLine.includes("[ERROR]") || cleanLine.includes("error")) div.style.color = "var(--accent-rose)";
        else if (cleanLine.includes("[INFO]") || cleanLine.includes("info")) div.style.color = "var(--accent-blue)";

        frag.appendChild(div);
    });
    terminal.appendChild(frag);
    while (terminal.childElementCount > 300) {
        terminal.removeChild(terminal.firstChild);
    }
    if (atBottom) terminal.scrollTop = terminal.scrollHeight;
}

export async function loadSingboxLogs() {
    const terminal = document.getElementById("singbox-logs-terminal");
    if (!terminal) return;
    try {
        const res = await apiFetch("/api/singbox/logs");
        if (res && res.success && Array.isArray(res.logs) && res.logs.length > 0) {
            terminal.innerHTML = "";
            appendSingboxLines(terminal, res.logs);
        }
    } catch (_) {}
}

export function startSingboxLogsStream() {
    stopSingboxLogsStream();
    const terminal = document.getElementById("singbox-logs-terminal");
    if (!terminal) return;

    loadSingboxLogs();

    function connect() {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${proto}//${window.location.host}/api/singbox/logs/ws`;

        try {
            const ws = new WebSocket(wsUrl);
            _singboxSocket = ws;

            ws.onopen = () => {
                _singboxReconnectDelay = 1000;
            };

            ws.onmessage = (e) => {
                try {
                    const msg = JSON.parse(e.data);
                    if (msg.event === "history" && Array.isArray(msg.data)) {
                        terminal.innerHTML = "";
                        appendSingboxLines(terminal, msg.data);
                    } else if (msg.event === "line" && msg.data) {
                        appendSingboxLines(terminal, [msg.data]);
                    }
                } catch (_) {}
            };

            ws.onerror = () => {
                ws.close();
            };

            ws.onclose = (e) => {
                _singboxSocket = null;
                if (e.code === 4401 || e.code === 1008) return;
                if (!_singboxES) {
                    connectSSE();
                }
            };
        } catch (_) {
            connectSSE();
        }
    }

    function connectSSE() {
        if (_singboxES) return;
        const es = new EventSource("/api/singbox/logs/stream");
        _singboxES = es;

        es.addEventListener("history", (e) => {
            try {
                const lines = JSON.parse(e.data);
                if (Array.isArray(lines) && lines.length > 0) {
                    terminal.innerHTML = "";
                    appendSingboxLines(terminal, lines);
                }
                _singboxReconnectDelay = 1000;
            } catch (_) {}
        });

        es.addEventListener("line", (e) => {
            try {
                appendSingboxLines(terminal, [JSON.parse(e.data)]);
            } catch (_) {}
        });

        es.onerror = () => {
            es.close();
            _singboxES = null;
            _singboxReconnectDelay = Math.min(_singboxReconnectDelay * 2, 30000);
            _singboxReconnectTimer = setTimeout(connect, _singboxReconnectDelay);
        };
    }

    connect();
}

export function stopSingboxLogsStream() {
    if (_singboxReconnectTimer) { clearTimeout(_singboxReconnectTimer); _singboxReconnectTimer = null; }
    if (_singboxSocket) { _singboxSocket.close(); _singboxSocket = null; }
    if (_singboxES) { _singboxES.close(); _singboxES = null; }
    _singboxReconnectDelay = 1000;
}

export function setupSingboxCoreListeners() {
    const prereleaseToggle = document.getElementById("singbox-prerelease-toggle");
    if (prereleaseToggle) {
        prereleaseToggle.addEventListener("change", () => {
            localStorage.setItem("singbox_include_prerelease", prereleaseToggle.checked);
            loadSingboxCoreInfo();
        });
    }

    const restartBtn = document.getElementById("singbox-restart-btn");
    if (restartBtn) {
        restartBtn.addEventListener("click", async () => {
            const res = await apiFetch("/api/singbox/action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "restart" })
            });
            if (res && res.success) showToast(t("singbox_restarted"));
        });
    }

    const stopBtn = document.getElementById("singbox-stop-btn");
    if (stopBtn) {
        stopBtn.addEventListener("click", async () => {
            const action = stopBtn.getAttribute("data-action") || "stop";
            const res = await apiFetch("/api/singbox/action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: action })
            });
            if (res && res.success) {
                if (action === "stop") {
                    showToast(t("singbox_stopped_toast"), "info");
                } else {
                    showToast(t("singbox_started_toast"));
                }
                loadSingboxCoreInfo();
            }
        });
    }

    const updateBtn = document.getElementById("singbox-update-btn");
    if (updateBtn) {
        updateBtn.addEventListener("click", async () => {
            const url = updateBtn.getAttribute("data-url");
            if (!url) return;

            updateBtn.disabled = true;
            updateBtn.innerText = t("core_btn_updating");
            showToast(t("singbox_update_started"), "info");

            const res = await apiFetch("/api/singbox/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ download_url: url })
            });

            if (res && res.success) {
                showToast(t("singbox_update_success").replace("{version}", res.version));
                loadSingboxCoreInfo();
            } else {
                showToast(res ? res.msg : t("singbox_update_error"), "error");
                loadSingboxCoreInfo();
            }
        });
    }

    const copyLogsBtn = document.getElementById("singbox-copy-logs-btn");
    if (copyLogsBtn) {
        copyLogsBtn.addEventListener("click", () => {
            const terminal = document.getElementById("singbox-logs-terminal");
            if (terminal) {
                navigator.clipboard.writeText(terminal.innerText);
                showToast(t("logs_copied"));
            }
        });
    }

    const clearLogsBtn = document.getElementById("singbox-clear-logs-btn");
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener("click", async () => {
            const res = await apiFetch("/api/singbox/logs/clear", { method: "POST" });
            if (res && res.success) {
                lastSingboxLogsStr = "[]";
                const terminal = document.getElementById("singbox-logs-terminal");
                if (terminal) terminal.innerText = "";
                showToast(t("logs_cleared"));
            } else {
                showToast(t("logs_clear_error"), "error");
            }
        });
    }

    setupSingboxConfigListeners();
}
