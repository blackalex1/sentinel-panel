import { apiFetch } from "../../api.js";
import { showToast, showConfirmDialog } from "../../ui.js";
import { t } from "../../i18n.js";

let latestUpdateData = null;
let latestCoreData = null;
let currentUpdateChannel = "stable";
let coreProgressPollInterval = null;

function formatVersionDisplay(ver) {
    if (!ver) return "";
    const trimmed = String(ver).trim();
    const isTextOnly = /^(не|not|установлен)/i.test(trimmed);
    if (isTextOnly || trimmed.startsWith("v") || trimmed.includes("dev")) {
        return trimmed;
    }
    return `v${trimmed}`;
}

function setAlertBannerContent(alertEl, iconClass, text) {
    if (!alertEl) return;
    alertEl.textContent = "";
    const icon = document.createElement("i");
    icon.className = iconClass;
    icon.style.fontSize = "16px";
    icon.style.marginRight = "8px";
    const span = document.createElement("span");
    span.textContent = text;
    alertEl.appendChild(icon);
    alertEl.appendChild(span);
}

function applyChannelUI(channel) {
    const norm = String(channel || "").trim().toLowerCase() === "beta" ? "beta" : "stable";
    currentUpdateChannel = norm;

    const radioStable = document.getElementById("update-channel-stable");
    const radioBeta = document.getElementById("update-channel-beta");
    const cardStable = document.getElementById("channel-card-stable");
    const cardBeta = document.getElementById("channel-card-beta");
    const badge = document.getElementById("update-channel-badge");

    if (radioStable) radioStable.checked = norm === "stable";
    if (radioBeta) radioBeta.checked = norm === "beta";

    if (cardStable) {
        cardStable.style.background = norm === "stable" ? "rgba(34, 197, 94, 0.08)" : "rgba(255, 255, 255, 0.03)";
        cardStable.style.border = norm === "stable" ? "1px solid rgba(34, 197, 94, 0.45)" : "1px solid rgba(255, 255, 255, 0.1)";
    }
    if (cardBeta) {
        cardBeta.style.background = norm === "beta" ? "rgba(245, 158, 11, 0.09)" : "rgba(255, 255, 255, 0.03)";
        cardBeta.style.border = norm === "beta" ? "1px solid rgba(245, 158, 11, 0.45)" : "1px solid rgba(255, 255, 255, 0.1)";
    }
    if (badge) {
        if (norm === "beta") {
            badge.innerText = "Stable + Beta (Pre-release)";
            badge.style.background = "rgba(245, 158, 11, 0.15)";
            badge.style.color = "#fbbf24";
            badge.style.border = "1px solid rgba(245, 158, 11, 0.35)";
        } else {
            badge.innerText = "Только стабильные (Stable)";
            badge.style.background = "rgba(34, 197, 94, 0.15)";
            badge.style.color = "#4ade80";
            badge.style.border = "1px solid rgba(34, 197, 94, 0.3)";
        }
    }
}

export async function loadUpdateChannel() {
    try {
        const res = await apiFetch("/api/system/settings/update/channel");
        if (res && res.success && res.channel) {
            applyChannelUI(res.channel);
            return res.channel;
        }
    } catch (e) {
        console.debug("Failed to load update channel:", e);
    }
    return currentUpdateChannel;
}

function renderCoreProgress(prog) {
    if (!prog) return;

    const fillEl = document.getElementById("core-progress-bar-fill");
    const pctEl = document.getElementById("core-progress-pct");
    const stageEl = document.getElementById("core-progress-stage-text");
    const bytesEl = document.getElementById("core-progress-bytes-val");
    const speedEl = document.getElementById("core-progress-speed-val");
    const etaEl = document.getElementById("core-progress-eta-val");

    const pct = Math.max(0, Math.min(100, Math.round(prog.percent || 0)));
    if (fillEl) fillEl.style.width = `${pct}%`;
    if (pctEl) pctEl.innerText = `${pct}%`;
    if (stageEl && prog.stage) stageEl.innerText = prog.stage;

    if (bytesEl) {
        if (prog.total_bytes && prog.total_bytes > 0) {
            const dlMb = ((prog.downloaded_bytes || 0) / (1024 * 1024)).toFixed(1);
            const totMb = (prog.total_bytes / (1024 * 1024)).toFixed(1);
            bytesEl.innerText = `${dlMb} / ${totMb} MB`;
        } else if (prog.downloaded_bytes > 0) {
            const dlMb = (prog.downloaded_bytes / (1024 * 1024)).toFixed(1);
            bytesEl.innerText = `${dlMb} MB`;
        }
    }

    if (speedEl && prog.speed) speedEl.innerText = prog.speed;
    if (etaEl && prog.eta) etaEl.innerText = prog.eta;
}

function startCoreProgressPolling() {
    if (coreProgressPollInterval) clearInterval(coreProgressPollInterval);
    coreProgressPollInterval = setInterval(async () => {
        try {
            const prog = await apiFetch("/api/system/settings/update/core/progress");
            if (prog && prog.active) {
                renderCoreProgress(prog);
            }
        } catch (e) {
            // ignore
        }
    }, 250);
}

function stopCoreProgressPolling() {
    if (coreProgressPollInterval) {
        clearInterval(coreProgressPollInterval);
        coreProgressPollInterval = null;
    }
}

async function checkActiveCoreProgress() {
    try {
        const prog = await apiFetch("/api/system/settings/update/core/progress");
        if (prog && prog.active) {
            const feedbackEl = document.getElementById("core-install-feedback");
            const alertEl = document.getElementById("core-install-alert");
            const progressBox = document.getElementById("core-install-progress-container");
            const btnApply = document.getElementById("btn-apply-core-update");
            const btnReinstall = document.getElementById("btn-reinstall-core");

            if (btnApply) btnApply.disabled = true;
            if (btnReinstall) btnReinstall.disabled = true;
            if (feedbackEl) feedbackEl.style.display = "block";
            if (alertEl) alertEl.style.display = "none";
            if (progressBox) progressBox.style.display = "block";
            renderCoreProgress(prog);
            startCoreProgressPolling();
        }
    } catch (e) {
        // ignore
    }
}

function updateUnifiedBadges() {
    const sidebarBadge = document.getElementById("sidebar-settings-update-badge");
    const navBadge = document.getElementById("settings-nav-update-badge");
    const hasAnyUpdate = Boolean(
        latestUpdateData?.has_update || latestCoreData?.has_update || latestCoreData?.restart_required
    );

    if (sidebarBadge) {
        sidebarBadge.style.display = hasAnyUpdate ? "inline-flex" : "none";
    }
    if (navBadge) {
        navBadge.style.display = hasAnyUpdate ? "inline-flex" : "none";
    }
}

// ============================================================================
// PANEL UPDATE
// ============================================================================

export async function checkPanelUpdates(force = false) {
    try {
        const icon = document.getElementById("icon-check-update");
        if (icon) icon.classList.add("fa-spin");

        const res = await apiFetch(`/api/system/settings/update/check?force=${force}`);
        if (icon) icon.classList.remove("fa-spin");

        if (res) {
            latestUpdateData = res;
            renderUpdateUI(res);
            updateUnifiedBadges();
            return res;
        }
    } catch (e) {
        console.error("Failed to check panel updates:", e);
    }
    return null;
}

function renderUpdateUI(data) {
    if (data.channel) {
        applyChannelUI(data.channel);
    }

    const statusBadge = document.getElementById("panel-update-status-badge");
    const currentVerEl = document.getElementById("panel-current-version-display");
    const latestVerEl = document.getElementById("panel-latest-version-display");
    const alertBox = document.getElementById("panel-update-alert-box");
    const alertTitle = document.getElementById("panel-update-alert-title");
    const alertDesc = document.getElementById("panel-update-alert-desc");
    const releaseNotesBox = document.getElementById("panel-release-notes-container");
    const releaseNotesContent = document.getElementById("panel-release-notes-content");
    const btnApply = document.getElementById("btn-apply-panel-update");
    const btnApplyText = document.getElementById("btn-apply-update-text");
    const githubLink = document.getElementById("btn-open-github-release");

    if (currentVerEl && data.current_version) {
        currentVerEl.innerText = formatVersionDisplay(data.current_version);
    }
    if (latestVerEl && data.latest_version) {
        latestVerEl.innerText = formatVersionDisplay(data.latest_version);
    }

    if (githubLink && data.release_url) {
        githubLink.href = data.release_url;
    }

    if (data.has_update) {
        const isPre = Boolean(data.is_prerelease);
        if (statusBadge) {
            statusBadge.innerText = isPre
                ? `Доступна Beta v${data.latest_version}`
                : `Доступно обновление v${data.latest_version}`;
            statusBadge.style.background = isPre ? "rgba(245, 158, 11, 0.15)" : "rgba(239, 68, 68, 0.15)";
            statusBadge.style.color = isPre ? "#fbbf24" : "#f87171";
            statusBadge.style.border = isPre ? "1px solid rgba(245, 158, 11, 0.35)" : "1px solid rgba(239, 68, 68, 0.35)";
        }

        if (alertBox) {
            alertBox.style.display = "block";
            alertBox.style.background = isPre ? "rgba(245, 158, 11, 0.12)" : "rgba(239, 68, 68, 0.12)";
            alertBox.style.border = isPre ? "1px solid rgba(245, 158, 11, 0.35)" : "1px solid rgba(239, 68, 68, 0.35)";
        }
        if (alertTitle) {
            alertTitle.style.color = isPre ? "#fbbf24" : "#f87171";
            alertTitle.innerText = isPre
                ? `Доступна бета-версия панели (Pre-release): v${data.latest_version}`
                : `Доступна новая версия панели: v${data.latest_version}!`;
        }
        if (alertDesc) {
            alertDesc.innerText = isPre
                ? "Тестовая сборка может работать с ограничениями. Вы видите её, так как включён бета-канал обновлений."
                : "Рекомендуется обновить панель до актуальной версии для применения новых возможностей и обновлений безопасности.";
        }

        if (data.release_notes && releaseNotesBox && releaseNotesContent) {
            releaseNotesContent.innerText = data.release_notes;
            releaseNotesBox.style.display = "block";
        } else if (releaseNotesBox) {
            releaseNotesBox.style.display = "none";
        }

        if (btnApply) {
            btnApply.style.display = "inline-flex";
            if (btnApplyText) btnApplyText.innerText = `Обновить до v${data.latest_version}`;
        }
    } else {
        if (statusBadge) {
            statusBadge.innerText = "Установлена актуальная версия";
            statusBadge.style.background = "rgba(34, 197, 94, 0.15)";
            statusBadge.style.color = "#4ade80";
            statusBadge.style.border = "1px solid rgba(34, 197, 94, 0.3)";
        }

        if (alertBox) alertBox.style.display = "none";
        if (releaseNotesBox) releaseNotesBox.style.display = "none";
        if (btnApply) btnApply.style.display = "none";
    }
}

// ============================================================================
// SENTINEL-CORE ENGINE UPDATE & REINSTALL
// ============================================================================

export async function checkCoreUpdates(force = false) {
    try {
        const icon = document.getElementById("icon-check-core-update");
        if (icon) icon.classList.add("fa-spin");

        const res = await apiFetch(`/api/system/settings/update/core/check?force=${force}`);
        if (icon) icon.classList.remove("fa-spin");

        if (res) {
            latestCoreData = res;
            renderCoreUI(res);
            updateUnifiedBadges();
            await checkActiveCoreProgress();
            return res;
        }
    } catch (e) {
        console.error("Failed to check Sentinel core updates:", e);
    }
    return null;
}

function renderCoreUI(data) {
    if (data.channel) {
        applyChannelUI(data.channel);
    }

    const statusBadge = document.getElementById("core-update-status-badge");
    const currentVerEl = document.getElementById("core-current-version-display");
    const loadedNoteEl = document.getElementById("core-loaded-version-note");
    const restartBox = document.getElementById("core-restart-required-box");
    const restartDesc = document.getElementById("core-restart-required-desc");
    const latestVerEl = document.getElementById("core-latest-version-display");
    const alertBox = document.getElementById("core-update-alert-box");
    const alertTitle = document.getElementById("core-update-alert-title");
    const alertDesc = document.getElementById("core-update-alert-desc");
    const selectEl = document.getElementById("sentinel-core-version-select");
    const btnApply = document.getElementById("btn-apply-core-update");
    const btnApplyText = document.getElementById("btn-apply-core-text");
    const githubLink = document.getElementById("btn-open-core-github");

    if (currentVerEl && data.current_version) {
        currentVerEl.innerText = formatVersionDisplay(data.current_version);
    }
    if (loadedNoteEl) {
        if (data.loaded_version) {
            loadedNoteEl.style.display = "block";
            loadedNoteEl.style.color = data.restart_required ? "#fbbf24" : "#94a3b8";
            loadedNoteEl.innerText = `В памяти (RAM): ${formatVersionDisplay(data.loaded_version)}`;
        } else if (data.is_installed) {
            loadedNoteEl.style.display = "block";
            loadedNoteEl.style.color = "#94a3b8";
            loadedNoteEl.innerText = "В памяти (RAM): не загружена (загрузится при старте движка)";
        } else {
            loadedNoteEl.style.display = "none";
        }
    }

    if (restartBox) {
        if (data.restart_required) {
            restartBox.style.display = "block";
            if (restartDesc) {
                restartDesc.innerText =
                    `На диске установлена ${formatVersionDisplay(data.current_version)}, ` +
                    `но в памяти процесса всё ещё загружена ${formatVersionDisplay(data.loaded_version || "предыдущая версия")}. ` +
                    `Перезапустите панель для применения новой библиотеки C-FFI.`;
            }
        } else {
            restartBox.style.display = "none";
        }
    }

    if (latestVerEl && data.latest_version) {
        latestVerEl.innerText = formatVersionDisplay(data.latest_version);
    }

    if (githubLink && data.release_url) {
        githubLink.href = data.release_url;
    }

    // Populate dropdown with releases filtered by active channel
    if (selectEl) {
        const currentSelected = selectEl.value;
        const rels = Array.isArray(data.releases) ? data.releases : [];
        selectEl.innerHTML = "";

        if (rels.length > 0) {
            const optDefault = document.createElement("option");
            optDefault.value = "";
            if (data.channel === "beta" && data.latest_is_prerelease) {
                optDefault.text = `Последняя доступная (Beta: ${data.latest_version})`;
            } else {
                optDefault.text = `Последняя стабильная (${data.stable_version || data.latest_version})`;
            }
            selectEl.appendChild(optDefault);

            rels.forEach(r => {
                const opt = document.createElement("option");
                opt.value = r.tag;
                const preLabel = r.prerelease ? " [Beta / Pre-release]" : "";
                opt.text = `${r.tag}${preLabel} — ${r.name || r.tag}`;
                selectEl.appendChild(opt);
            });

            const stillAvailable = rels.some(r => r.tag === currentSelected);
            selectEl.value = stillAvailable ? currentSelected : "";
        } else {
            const optEmpty = document.createElement("option");
            optEmpty.value = "";
            optEmpty.text = data.channel === "beta"
                ? "Релизы ядра не найдены"
                : "Нет доступных стабильных релизов";
            selectEl.appendChild(optEmpty);
        }
    }

    if (data.has_update) {
        const isPre = Boolean(data.latest_is_prerelease);
        if (statusBadge) {
            statusBadge.innerText = isPre
                ? `Доступна Beta ${data.latest_version}`
                : `Доступно ядро ${data.latest_version}`;
            statusBadge.style.background = isPre ? "rgba(245, 158, 11, 0.15)" : "rgba(239, 68, 68, 0.15)";
            statusBadge.style.color = isPre ? "#fbbf24" : "#f87171";
            statusBadge.style.border = isPre ? "1px solid rgba(245, 158, 11, 0.35)" : "1px solid rgba(239, 68, 68, 0.35)";
        }

        if (alertBox) {
            alertBox.style.display = "block";
            alertBox.style.background = isPre ? "rgba(245, 158, 11, 0.12)" : "rgba(239, 68, 68, 0.12)";
            alertBox.style.border = isPre ? "1px solid rgba(245, 158, 11, 0.35)" : "1px solid rgba(239, 68, 68, 0.35)";
        }
        if (alertTitle) {
            alertTitle.style.color = isPre ? "#fbbf24" : "#f87171";
            alertTitle.innerText = isPre
                ? `Доступна бета-версия Sentinel-Core (Pre-release): ${data.latest_version}`
                : `Доступно обновление Sentinel-Core: ${data.latest_version}!`;
        }
        if (alertDesc) {
            alertDesc.innerText = isPre
                ? "Тестовая сборка ядра отображается, так как включён бета-канал. После установки панель автоматически перезапустится."
                : "Обновите ядро для получения улучшенных алгоритмов маршрутизации и оптимизаций производительности. После установки панель перезапустится.";
        }

        if (btnApply) {
            btnApply.style.display = "inline-flex";
            if (btnApplyText) btnApplyText.innerText = `Обновить ядро до ${data.latest_version}`;
        }
    } else {
        if (statusBadge) {
            statusBadge.innerText = "Ядро актуально";
            statusBadge.style.background = "rgba(34, 197, 94, 0.15)";
            statusBadge.style.color = "#4ade80";
            statusBadge.style.border = "1px solid rgba(34, 197, 94, 0.3)";
        }

        if (alertBox) alertBox.style.display = "none";
        if (btnApply) btnApply.style.display = "none";
    }

    updateSelectedReleaseNotes();
}

function updateSelectedReleaseNotes() {
    const selectEl = document.getElementById("sentinel-core-version-select");
    const notesBox = document.getElementById("core-release-notes-container");
    const notesContent = document.getElementById("core-release-notes-content");
    const tagInfo = document.getElementById("core-selected-tag-info");

    if (!selectEl || !notesBox || !notesContent || !latestCoreData) return;

    const selectedTag = selectEl.value;
    const release = latestCoreData.releases?.find(r => r.tag === selectedTag)
        || latestCoreData.releases?.[0];

    if (release && release.body) {
        notesContent.innerText = release.body;
        notesBox.style.display = "block";
    } else {
        notesBox.style.display = "none";
    }

    if (tagInfo) {
        tagInfo.innerText = release ? `Опубликован: ${new Date(release.published_at).toLocaleDateString()}` : "";
    }
}

async function waitForPanelRestartAndReloadCore() {
    const feedbackEl = document.getElementById("core-install-feedback");
    const alertEl = document.getElementById("core-install-alert");
    const progressBox = document.getElementById("core-install-progress-container");
    const btnRestart = document.getElementById("btn-restart-panel-after-core");
    const btnApply = document.getElementById("btn-apply-core-update");
    const btnReinstall = document.getElementById("btn-reinstall-core");

    if (btnRestart) btnRestart.disabled = true;
    if (btnApply) btnApply.disabled = true;
    if (btnReinstall) btnReinstall.disabled = true;

    if (feedbackEl) feedbackEl.style.display = "block";
    if (progressBox) progressBox.style.display = "none";
    if (alertEl) {
        alertEl.style.display = "flex";
        alertEl.style.background = "rgba(56, 189, 248, 0.12)";
        alertEl.style.border = "1px solid rgba(56, 189, 248, 0.35)";
        alertEl.style.color = "#38bdf8";
        setAlertBannerContent(
            alertEl,
            "fa-solid fa-spinner fa-spin",
            "Панель перезапускается для загрузки новой библиотеки C-FFI в память..."
        );
    }

    await new Promise(r => setTimeout(r, 2200));

    let recovered = false;
    for (let attempt = 0; attempt < 30; attempt++) {
        try {
            const resp = await fetch(`/api/system/settings/update/core/check?force=true&t=${Date.now()}`, {
                credentials: "same-origin",
                cache: "no-store",
            });
            if (resp.ok) {
                const checkData = await resp.json();
                if (checkData && checkData.success) {
                    recovered = true;
                    latestCoreData = checkData;
                    renderCoreUI(checkData);
                    updateUnifiedBadges();

                    const loadedTxt = checkData.loaded_version || checkData.current_version || "";
                    if (alertEl) {
                        if (checkData.restart_required) {
                            alertEl.style.background = "rgba(245, 158, 11, 0.12)";
                            alertEl.style.border = "1px solid rgba(245, 158, 11, 0.35)";
                            alertEl.style.color = "#fbbf24";
                            setAlertBannerContent(
                                alertEl,
                                "fa-solid fa-triangle-exclamation",
                                "Панель ответила, но в памяти всё ещё загружена предыдущая версия ядра. Попробуйте перезапустить ещё раз."
                            );
                        } else {
                            alertEl.style.background = "rgba(34, 197, 94, 0.12)";
                            alertEl.style.border = "1px solid rgba(34, 197, 94, 0.35)";
                            alertEl.style.color = "#4ade80";
                            setAlertBannerContent(
                                alertEl,
                                "fa-solid fa-circle-check",
                                `Панель успешно перезапущена! Активная версия ядра: ${loadedTxt}.`
                            );
                            showToast(`Ядро Sentinel-Core (${loadedTxt}) активно!`, "success");
                        }
                    }
                    await checkPanelUpdates(true);
                    break;
                }
            }
        } catch (e) {
            // Panel process is restarting; continue polling
        }
        await new Promise(r => setTimeout(r, 1500));
    }

    if (!recovered) {
        if (alertEl) {
            alertEl.style.background = "rgba(245, 158, 11, 0.12)";
            alertEl.style.border = "1px solid rgba(245, 158, 11, 0.35)";
            alertEl.style.color = "#fbbf24";
            setAlertBannerContent(
                alertEl,
                "fa-solid fa-rotate",
                "Перезапуск занимает больше времени, чем ожидалось. Обновляем страницу..."
            );
        }
        setTimeout(() => window.location.reload(), 1500);
    }

    if (btnRestart) btnRestart.disabled = false;
    if (btnApply) btnApply.disabled = false;
    if (btnReinstall) btnReinstall.disabled = false;
}

async function executeCoreInstallation(targetVersion, force = false) {
    const feedbackEl = document.getElementById("core-install-feedback");
    const alertEl = document.getElementById("core-install-alert");
    const progressBox = document.getElementById("core-install-progress-container");
    const titleEl = document.getElementById("core-progress-title");
    const btnApply = document.getElementById("btn-apply-core-update");
    const btnReinstall = document.getElementById("btn-reinstall-core");

    if (btnApply) btnApply.disabled = true;
    if (btnReinstall) btnReinstall.disabled = true;

    if (feedbackEl) feedbackEl.style.display = "block";
    if (alertEl) alertEl.style.display = "none";
    if (progressBox) {
        progressBox.style.display = "block";
        if (titleEl) {
            titleEl.innerText = force
                ? "Переустановка Sentinel-Core: загрузка бинарников и библиотеки C-FFI с GitHub..."
                : "Обновление Sentinel-Core: загрузка и установка...";
        }
        renderCoreProgress({
            percent: 0,
            stage: "Подготовка к загрузке...",
            downloaded_bytes: 0,
            total_bytes: 0,
            speed: "0.0 KB/s",
            eta: "--",
        });
    }

    startCoreProgressPolling();

    let waitForRestart = false;
    try {
        const res = await apiFetch("/api/system/settings/update/core/apply", {
            method: "POST",
            body: JSON.stringify({
                version: targetVersion,
                force: force,
                channel: currentUpdateChannel
            })
        });

        stopCoreProgressPolling();

        if (res && res.success) {
            renderCoreProgress({
                percent: 100,
                stage: "Установка успешно завершена!",
            });
            await new Promise(r => setTimeout(r, 600));

            showToast(res.msg || `Sentinel-Core успешно ${force ? "переустановлен" : "обновлен"}!`, "success");
            if (res.restarting) {
                waitForRestart = true;
                await waitForPanelRestartAndReloadCore();
            } else {
                if (progressBox) progressBox.style.display = "none";
                if (alertEl) {
                    alertEl.style.display = "flex";
                    alertEl.style.background = "rgba(34, 197, 94, 0.12)";
                    alertEl.style.border = "1px solid rgba(34, 197, 94, 0.35)";
                    alertEl.style.color = "#4ade80";
                    setAlertBannerContent(
                        alertEl,
                        "fa-solid fa-circle-check",
                        res.msg || "Ядро успешно установлено!"
                    );
                }
                await checkCoreUpdates(true);
            }
        } else {
            showToast(res?.msg || "Ошибка установки Sentinel-Core.", "error");
            if (progressBox) progressBox.style.display = "none";
            if (alertEl) {
                alertEl.style.display = "flex";
                alertEl.style.background = "rgba(239, 68, 68, 0.12)";
                alertEl.style.border = "1px solid rgba(239, 68, 68, 0.35)";
                alertEl.style.color = "#f87171";
                setAlertBannerContent(
                    alertEl,
                    "fa-solid fa-triangle-exclamation",
                    res?.msg || "Не удалось установить ядро."
                );
            }
        }
    } catch (err) {
        stopCoreProgressPolling();
        console.error("Execute core installation error:", err);
        showToast("Ошибка сети при установке Sentinel-Core.", "error");
        if (progressBox) progressBox.style.display = "none";
        if (alertEl) {
            alertEl.style.display = "flex";
            alertEl.style.background = "rgba(239, 68, 68, 0.12)";
            alertEl.style.border = "1px solid rgba(239, 68, 68, 0.35)";
            alertEl.style.color = "#f87171";
            setAlertBannerContent(
                alertEl,
                "fa-solid fa-triangle-exclamation",
                `Ошибка: ${err.message || err}`
            );
        }
    } finally {
        if (!waitForRestart) {
            if (btnApply) btnApply.disabled = false;
            if (btnReinstall) btnReinstall.disabled = false;
        }
    }
}

// ============================================================================
// LISTENERS SETUP
// ============================================================================

export function setupUpdateListeners() {
    // 0. Update Channel Switcher
    loadUpdateChannel();
    document.querySelectorAll('input[name="update-channel"]').forEach(radio => {
        radio.addEventListener("change", async (ev) => {
            const newChannel = ev.target.value === "beta" ? "beta" : "stable";
            const prevChannel = currentUpdateChannel;
            applyChannelUI(newChannel);

            try {
                const res = await apiFetch("/api/system/settings/update/channel", {
                    method: "POST",
                    body: JSON.stringify({ channel: newChannel })
                });
                if (res && res.success) {
                    const selectEl = document.getElementById("sentinel-core-version-select");
                    if (selectEl) selectEl.value = "";
                    showToast(res.msg || "Канал обновлений обновлён.", "success");
                    await Promise.all([checkPanelUpdates(true), checkCoreUpdates(true)]);
                } else {
                    applyChannelUI(prevChannel);
                    showToast(res?.msg || "Не удалось изменить канал обновлений.", "error");
                }
            } catch (e) {
                applyChannelUI(prevChannel);
                showToast("Ошибка сохранения канала обновлений.", "error");
            }
        });
    });

    // Manual Panel Restart button when new core sits on disk
    const btnRestartAfterCore = document.getElementById("btn-restart-panel-after-core");
    if (btnRestartAfterCore) {
        btnRestartAfterCore.addEventListener("click", async () => {
            const confirmed = await showConfirmDialog({
                title: "Перезапуск панели управления",
                message: "Панель будет перезапущена для загрузки новой версии библиотеки Sentinel-Core (C-FFI) из файла на диске.\n\nЭто займёт несколько секунд.",
                type: "warning",
                icon: "fa-solid fa-power-off",
                okText: "Перезапустить панель",
                cancelText: "Отмена"
            });
            if (!confirmed) return;

            btnRestartAfterCore.disabled = true;
            try {
                const res = await apiFetch("/api/system/settings/panel/restart", { method: "POST" });
                if (res && res.success) {
                    showToast(res.msg || "Перезапуск панели...", "info");
                    if (res.restarting) {
                        await waitForPanelRestartAndReloadCore();
                    } else {
                        await checkCoreUpdates(true);
                    }
                } else {
                    showToast(res?.msg || "Не удалось инициировать перезапуск.", "error");
                }
            } catch (e) {
                showToast("Ошибка отправки команды перезапуска.", "error");
            } finally {
                btnRestartAfterCore.disabled = false;
            }
        });
    }

    // 1. Panel Check
    const btnCheck = document.getElementById("btn-check-panel-update");
    if (btnCheck) {
        btnCheck.addEventListener("click", async () => {
            showToast("Проверка обновлений панели на GitHub...", "info");
            const res = await checkPanelUpdates(true);
            if (res && res.has_update) {
                showToast(`Доступна новая версия панели v${res.latest_version}!`, "success");
            } else if (res && res.success) {
                showToast("У вас установлена актуальная версия панели.", "success");
            } else {
                showToast("Не удалось получить информацию с GitHub.", "error");
            }
        });
    }

    // 2. Panel Apply
    const btnApply = document.getElementById("btn-apply-panel-update");
    if (btnApply) {
        btnApply.addEventListener("click", async () => {
            const targetVer = latestUpdateData?.latest_version || "N";
            const confirmed = await showConfirmDialog({
                title: "Обновление Sentinel Control Panel",
                message: `Вы действительно хотите обновить панель до версии v${targetVer}?\n\nВ процессе обновления будут загружены новые файлы и панель автоматически перезапустится в течение нескольких секунд.`,
                type: "warning",
                icon: "fa-solid fa-cloud-arrow-down",
                okText: `Обновить до v${targetVer}`,
                cancelText: "Отмена"
            });

            if (!confirmed) return;

            btnApply.disabled = true;
            btnApply.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Обновление...</span>';
            showToast("Запущено обновление панели. Ожидайте перезагрузки...", "info");

            try {
                const res = await apiFetch("/api/system/settings/update/apply", {
                    method: "POST"
                });

                if (res && res.success) {
                    showToast(res.msg || "Обновление успешно инициировано!", "success");
                    setTimeout(() => {
                        let attempts = 0;
                        const pollInterval = setInterval(async () => {
                            attempts++;
                            try {
                                const check = await fetch(`/api/system/settings/update/check?force=true&t=${Date.now()}`);
                                if (check.ok) {
                                    const checkData = await check.json();
                                    if (checkData && (checkData.current_version === targetVer || !checkData.has_update)) {
                                        clearInterval(pollInterval);
                                        showToast(`Панель успешно обновлена до v${checkData.current_version}! Перезагрузка страницы...`, "success");
                                        setTimeout(() => window.location.reload(), 1500);
                                        return;
                                    }
                                }
                            } catch (e) {
                                // Container may be restarting
                            }
                            if (attempts > 30) {
                                clearInterval(pollInterval);
                                showToast("Ожидание завершения обновления. Перезагрузка страницы...", "info");
                                setTimeout(() => window.location.reload(), 1500);
                            }
                        }, 2500);
                    }, 4000);
                } else {
                    showToast(res?.msg || "Не удалось запустить обновление.", "error");
                    btnApply.disabled = false;
                    btnApply.innerHTML = `<i class="fa-solid fa-bolt"></i> <span>Обновить до v${targetVer}</span>`;
                }
            } catch (err) {
                console.error("Apply update error:", err);
                showToast("Ошибка при отправке команды обновления.", "error");
                btnApply.disabled = false;
                btnApply.innerHTML = `<i class="fa-solid fa-bolt"></i> <span>Обновить до v${targetVer}</span>`;
            }
        });
    }

    // 3. Core Check
    const btnCheckCore = document.getElementById("btn-check-core-update");
    if (btnCheckCore) {
        btnCheckCore.addEventListener("click", async () => {
            showToast("Проверка релизов Sentinel-Core на GitHub...", "info");
            const res = await checkCoreUpdates(true);
            if (res && res.has_update) {
                showToast(`Доступна новая версия ядра ${res.latest_version}!`, "success");
            } else if (res && res.success) {
                showToast("У вас установлено актуальное ядро Sentinel-Core.", "success");
            } else {
                showToast("Не удалось проверить ядро на GitHub.", "error");
            }
        });
    }

    // 4. Core Version Selector
    const selectCoreVer = document.getElementById("sentinel-core-version-select");
    if (selectCoreVer) {
        selectCoreVer.addEventListener("change", () => {
            updateSelectedReleaseNotes();
        });
    }

    // 5. Core Apply (Update)
    const btnApplyCore = document.getElementById("btn-apply-core-update");
    if (btnApplyCore) {
        btnApplyCore.addEventListener("click", async () => {
            const selectEl = document.getElementById("sentinel-core-version-select");
            const selectedVer = selectEl?.value || latestCoreData?.latest_version || "";
            const displayVer = selectedVer || latestCoreData?.latest_version || "latest";

            const confirmed = await showConfirmDialog({
                title: "Обновление Sentinel-Core",
                message: `Вы действительно хотите обновить ядро Sentinel до версии ${displayVer}?\n\nБудут загружены и установлены динамическая библиотека C-FFI и бинарный файл ядра.`,
                type: "info",
                icon: "fa-solid fa-microchip",
                okText: `Обновить ядро до ${displayVer}`,
                cancelText: "Отмена"
            });

            if (!confirmed) return;
            await executeCoreInstallation(selectedVer, false);
        });
    }

    // 6. Core Reinstall
    const btnReinstallCore = document.getElementById("btn-reinstall-core");
    if (btnReinstallCore) {
        btnReinstallCore.addEventListener("click", async () => {
            const selectEl = document.getElementById("sentinel-core-version-select");
            const currVer = latestCoreData?.current_version || "";
            const isValidCurrSemver = /^v?\d+\.\d+/.test(currVer.trim());
            const selectedVer = selectEl?.value || (isValidCurrSemver ? currVer : "") || latestCoreData?.latest_version || "";
            const cleanTarget = /^v?\d+\.\d+/.test(selectedVer.trim()) ? selectedVer.trim() : "";
            const displayVer = cleanTarget || "актуальной версии";

            const confirmed = await showConfirmDialog({
                title: "Переустановка Sentinel-Core",
                message: `Вы действительно хотите ПЕРЕУСТАНОВИТЬ Sentinel-Core (${displayVer})?\n\nТекущие бинарные файлы и библиотеки C-FFI будут принудительно перезагружены с GitHub и перезаписаны, после чего панель перезапустится.`,
                type: "warning",
                icon: "fa-solid fa-rotate-right",
                okText: `Переустановить ${displayVer}`,
                cancelText: "Отмена"
            });

            if (!confirmed) return;
            await executeCoreInstallation(cleanTarget, true);
        });
    }
}
