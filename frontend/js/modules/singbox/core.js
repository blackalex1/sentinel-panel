import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadSingboxConfig, setupSingboxConfigListeners } from "./config.js";

export { loadSingboxConfig };

export async function loadSingboxCoreInfo() {
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

    const currElem = document.getElementById("singbox-curr-version");
    if (currElem) currElem.innerText = res.current;

    const latestElem = document.getElementById("singbox-latest-version");
    if (latestElem) latestElem.innerText = res.latest;

    const prereleaseBadge = document.getElementById("singbox-prerelease-badge");
    const versionSelect = document.getElementById("singbox-version-select");
    const updateBtn = document.getElementById("singbox-update-btn");

    const normVer = (v) => (v || "").toString().trim().replace(/^v/i, "");

    if (res.versions && res.versions.length > 0 && versionSelect) {
        versionSelect.style.display = "inline-block";
        versionSelect.innerHTML = "";
        res.versions.forEach(item => {
            const opt = document.createElement("option");
            opt.value = item.download_url;
            opt.setAttribute("data-version", item.version);
            opt.setAttribute("data-prerelease", item.is_prerelease ? "true" : "false");
            const tag = item.is_prerelease ? "Pre-release" : "Stable";
            opt.innerText = `${item.version} (${tag})`;
            if (normVer(item.version) === normVer(res.current)) {
                opt.innerText += " — [Установлено]";
            }
            versionSelect.appendChild(opt);
        });

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
                updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>${t("singbox_installed", "Установлено")}</span>`;
            } else {
                updateBtn.disabled = false;
                updateBtn.setAttribute("data-url", selUrl);
                updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span>Установить ${selVer}</span>`;
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
                updateBtn.innerHTML = `<i class="fa-solid fa-download"></i> <span>${t("singbox_btn_update", "Обновить ядро")}</span>`;
            } else {
                updateBtn.disabled = true;
                updateBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>${t("singbox_updated", "Обновлено")}</span>`;
            }
        }
    }

    const statusRes = await apiFetch("/api/singbox/status");
    if (statusRes) {
        const stopBtn = document.getElementById("singbox-stop-btn");
        if (stopBtn) {
            if (statusRes.running) {
                stopBtn.className = "btn danger-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-stop"></i> <span>${t("singbox_btn_stop", "Остановить")}</span>`;
                stopBtn.setAttribute("data-action", "stop");
            } else {
                stopBtn.className = "btn success-btn";
                stopBtn.innerHTML = `<i class="fa-solid fa-play"></i> <span>${t("singbox_btn_start", "Запустить")}</span>`;
                stopBtn.setAttribute("data-action", "start");
            }
        }

        const badge = document.getElementById("singbox-status-badge");
        const statusText = badge ? badge.querySelector(".status-text") : null;
        if (badge && statusText) {
            if (statusRes.running) {
                badge.className = "status-badge running";
                statusText.innerText = t("singbox_status_active", "sing-box: Активен");
            } else {
                badge.className = "status-badge stopped";
                statusText.innerText = t("singbox_status_stopped", "sing-box: Остановлен");
            }
        }
    }

    await loadSingboxConfig();
}

let lastSingboxLogsStr = "";

export async function loadSingboxLogs() {
    const res = await apiFetch("/api/singbox/logs");
    if (!res || !res.success) return;

    const terminal = document.getElementById("singbox-logs-terminal");
    if (terminal) {
        const logsStr = JSON.stringify(res.logs);
        if (logsStr === lastSingboxLogsStr) {
            return;
        }
        lastSingboxLogsStr = logsStr;

        const currentScroll = terminal.scrollTop + terminal.clientHeight >= terminal.scrollHeight - 50;

        terminal.innerHTML = "";
        res.logs.forEach(line => {
            const div = document.createElement("div");
            const cleanLine = line.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
            div.innerText = cleanLine;

            if (cleanLine.includes("[WARN]") || cleanLine.includes("warning")) div.style.color = "var(--accent-orange)";
            else if (cleanLine.includes("[ERROR]") || cleanLine.includes("error")) div.style.color = "var(--accent-rose)";
            else if (cleanLine.includes("[INFO]") || cleanLine.includes("info")) div.style.color = "var(--accent-blue)";

            terminal.appendChild(div);
        });

        if (currentScroll) {
            terminal.scrollTop = terminal.scrollHeight;
        }
    }
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
            if (res && res.success) showToast(t("singbox_restarted", "Ядро sing-box перезапущено"));
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
                    showToast(t("singbox_stopped_toast", "Ядро sing-box остановлено"), "info");
                } else {
                    showToast(t("singbox_started_toast", "Ядро sing-box запущено"));
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
            updateBtn.innerText = "Обновление...";
            showToast(t("singbox_update_started", "Начался процесс обновления ядра sing-box. Пожалуйста, подождите"), "info");

            const res = await apiFetch("/api/singbox/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ download_url: url })
            });

            if (res && res.success) {
                showToast(t("singbox_update_success", "Ядро sing-box успешно обновлено до версии {version}!").replace("{version}", res.version));
                loadSingboxCoreInfo();
            } else {
                showToast(res ? res.msg : t("singbox_update_error", "Ошибка обновления ядра sing-box"), "error");
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
                showToast(t("logs_copied", "Логи скопированы в буфер обмена"));
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
                showToast(t("logs_cleared", "Логи очищены"));
            } else {
                showToast(t("logs_clear_error", "Ошибка при очистке логов"), "error");
            }
        });
    }

    setupSingboxConfigListeners();
}
