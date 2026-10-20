import { apiFetch } from "../../api.js";
import { showToast, showConfirmDialog } from "../../ui.js";
import { t } from "../../i18n.js";

let latestUpdateData = null;
let latestCoreData = null;

function updateUnifiedBadges() {
    const sidebarBadge = document.getElementById("sidebar-settings-update-badge");
    const navBadge = document.getElementById("settings-nav-update-badge");
    const hasAnyUpdate = Boolean(latestUpdateData?.has_update || latestCoreData?.has_update);

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
    const statusBadge = document.getElementById("panel-update-status-badge");
    const currentVerEl = document.getElementById("panel-current-version-display");
    const latestVerEl = document.getElementById("panel-latest-version-display");
    const alertBox = document.getElementById("panel-update-alert-box");
    const alertTitle = document.getElementById("panel-update-alert-title");
    const releaseNotesBox = document.getElementById("panel-release-notes-container");
    const releaseNotesContent = document.getElementById("panel-release-notes-content");
    const btnApply = document.getElementById("btn-apply-panel-update");
    const btnApplyText = document.getElementById("btn-apply-update-text");
    const githubLink = document.getElementById("btn-open-github-release");

    if (currentVerEl && data.current_version) {
        currentVerEl.innerText = `v${data.current_version}`;
    }
    if (latestVerEl && data.latest_version) {
        latestVerEl.innerText = `v${data.latest_version}`;
    }

    if (githubLink && data.release_url) {
        githubLink.href = data.release_url;
    }

    if (data.has_update) {
        if (statusBadge) {
            statusBadge.innerText = `Доступно обновление v${data.latest_version}`;
            statusBadge.style.background = "rgba(239, 68, 68, 0.15)";
            statusBadge.style.color = "#f87171";
            statusBadge.style.border = "1px solid rgba(239, 68, 68, 0.35)";
        }

        if (alertBox) alertBox.style.display = "block";
        if (alertTitle) alertTitle.innerText = `Доступна новая версия панели: v${data.latest_version}!`;

        if (data.release_notes && releaseNotesBox && releaseNotesContent) {
            releaseNotesContent.innerText = data.release_notes;
            releaseNotesBox.style.display = "block";
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
            return res;
        }
    } catch (e) {
        console.error("Failed to check Sentinel core updates:", e);
    }
    return null;
}

function renderCoreUI(data) {
    const statusBadge = document.getElementById("core-update-status-badge");
    const currentVerEl = document.getElementById("core-current-version-display");
    const latestVerEl = document.getElementById("core-latest-version-display");
    const alertBox = document.getElementById("core-update-alert-box");
    const alertTitle = document.getElementById("core-update-alert-title");
    const selectEl = document.getElementById("core-version-select");
    const notesBox = document.getElementById("core-release-notes-container");
    const notesContent = document.getElementById("core-release-notes-content");
    const btnApply = document.getElementById("btn-apply-core-update");
    const btnApplyText = document.getElementById("btn-apply-core-text");
    const githubLink = document.getElementById("btn-open-core-github");

    if (currentVerEl && data.current_version) {
        currentVerEl.innerText = data.current_version.startsWith("v") || data.current_version.includes("dev")
            ? data.current_version
            : `v${data.current_version}`;
    }
    if (latestVerEl && data.latest_version) {
        latestVerEl.innerText = data.latest_version.startsWith("v")
            ? data.latest_version
            : `v${data.latest_version}`;
    }

    if (githubLink && data.release_url) {
        githubLink.href = data.release_url;
    }

    // Populate dropdown with available releases
    if (selectEl && Array.isArray(data.releases) && data.releases.length > 0) {
        const currentSelected = selectEl.value;
        selectEl.innerHTML = "";

        const optDefault = document.createElement("option");
        optDefault.value = "";
        optDefault.text = `Последняя стабильная (${data.stable_version || data.latest_version})`;
        selectEl.appendChild(optDefault);

        data.releases.forEach(r => {
            const opt = document.createElement("option");
            opt.value = r.tag;
            const preLabel = r.prerelease ? " [Pre-release]" : "";
            opt.text = `${r.tag}${preLabel} — ${r.name || r.tag}`;
            selectEl.appendChild(opt);
        });

        if (currentSelected) {
            selectEl.value = currentSelected;
        }
    }

    if (data.has_update) {
        if (statusBadge) {
            statusBadge.innerText = `Доступно ядро ${data.latest_version}`;
            statusBadge.style.background = "rgba(239, 68, 68, 0.15)";
            statusBadge.style.color = "#f87171";
            statusBadge.style.border = "1px solid rgba(239, 68, 68, 0.35)";
        }

        if (alertBox) alertBox.style.display = "block";
        if (alertTitle) alertTitle.innerText = `Доступно обновление Sentinel-Core: ${data.latest_version}!`;

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
    const selectEl = document.getElementById("core-version-select");
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

async function executeCoreInstallation(targetVersion, force = false) {
    const feedbackEl = document.getElementById("core-install-feedback");
    const btnApply = document.getElementById("btn-apply-core-update");
    const btnReinstall = document.getElementById("btn-reinstall-core");

    if (btnApply) btnApply.disabled = true;
    if (btnReinstall) btnReinstall.disabled = true;

    if (feedbackEl) {
        feedbackEl.style.display = "block";
        feedbackEl.style.background = "rgba(14, 165, 233, 0.12)";
        feedbackEl.style.border = "1px solid rgba(14, 165, 233, 0.35)";
        feedbackEl.style.color = "#38bdf8";
        feedbackEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin" style="margin-right: 8px;"></i> ${
            force ? "Переустановка Sentinel-Core: загрузка бинарников и библиотеки C-FFI с GitHub..." : "Обновление Sentinel-Core: загрузка и установка..."
        }`;
    }

    try {
        const res = await apiFetch("/api/system/settings/update/core/apply", {
            method: "POST",
            body: JSON.stringify({
                version: targetVersion,
                force: force
            })
        });

        if (res && res.success) {
            showToast(res.msg || `Sentinel-Core успешно ${force ? "переустановлен" : "обновлен"}!`, "success");
            if (feedbackEl) {
                feedbackEl.style.background = "rgba(34, 197, 94, 0.12)";
                feedbackEl.style.border = "1px solid rgba(34, 197, 94, 0.35)";
                feedbackEl.style.color = "#4ade80";
                feedbackEl.innerHTML = `<i class="fa-solid fa-check" style="margin-right: 8px;"></i> ${res.msg || "Ядро успешно установлено!"}`;
            }
            await checkCoreUpdates(true);
        } else {
            showToast(res?.msg || "Ошибка установки Sentinel-Core.", "error");
            if (feedbackEl) {
                feedbackEl.style.background = "rgba(239, 68, 68, 0.12)";
                feedbackEl.style.border = "1px solid rgba(239, 68, 68, 0.35)";
                feedbackEl.style.color = "#f87171";
                feedbackEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="margin-right: 8px;"></i> ${res?.msg || "Не удалось установить ядро."}`;
            }
        }
    } catch (err) {
        console.error("Execute core installation error:", err);
        showToast("Ошибка сети при установке Sentinel-Core.", "error");
        if (feedbackEl) {
            feedbackEl.style.background = "rgba(239, 68, 68, 0.12)";
            feedbackEl.style.border = "1px solid rgba(239, 68, 68, 0.35)";
            feedbackEl.style.color = "#f87171";
            feedbackEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation" style="margin-right: 8px;"></i> Ошибка: ${err.message || err}`;
        }
    } finally {
        if (btnApply) btnApply.disabled = false;
        if (btnReinstall) btnReinstall.disabled = false;
    }
}

// ============================================================================
// LISTENERS SETUP
// ============================================================================

export function setupUpdateListeners() {
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
                                    clearInterval(pollInterval);
                                    showToast("Панель успешно обновлена! Перезагрузка страницы...", "success");
                                    setTimeout(() => window.location.reload(), 1500);
                                }
                            } catch (e) {
                                if (attempts > 15) {
                                    clearInterval(pollInterval);
                                    window.location.reload();
                                }
                            }
                        }, 2000);
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
    const selectCoreVer = document.getElementById("core-version-select");
    if (selectCoreVer) {
        selectCoreVer.addEventListener("change", () => {
            updateSelectedReleaseNotes();
        });
    }

    // 5. Core Apply (Update)
    const btnApplyCore = document.getElementById("btn-apply-core-update");
    if (btnApplyCore) {
        btnApplyCore.addEventListener("click", async () => {
            const selectEl = document.getElementById("core-version-select");
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
            const selectEl = document.getElementById("core-version-select");
            const selectedVer = selectEl?.value || latestCoreData?.current_version || latestCoreData?.latest_version || "";
            const displayVer = selectedVer || "текущей";

            const confirmed = await showConfirmDialog({
                title: "Переустановка Sentinel-Core",
                message: `Вы действительно хотите ПЕРЕУСТАНОВИТЬ Sentinel-Core (${displayVer})?\n\nТекущие бинарные файлы и библиотеки C-FFI будут принудительно перезагружены с GitHub и перезаписаны.`,
                type: "warning",
                icon: "fa-solid fa-rotate-right",
                okText: `Переустановить ${displayVer}`,
                cancelText: "Отмена"
            });

            if (!confirmed) return;
            await executeCoreInstallation(selectedVer, true);
        });
    }
}
