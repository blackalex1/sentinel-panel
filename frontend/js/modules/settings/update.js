import { apiFetch } from "../../api.js";
import { showToast, showConfirmDialog } from "../../ui.js";
import { t } from "../../i18n.js";

let latestUpdateData = null;

export async function checkPanelUpdates(force = false) {
    try {
        const icon = document.getElementById("icon-check-update");
        if (icon) icon.classList.add("fa-spin");

        const res = await apiFetch(`/api/system/settings/update/check?force=${force}`);
        if (icon) icon.classList.remove("fa-spin");

        if (res) {
            latestUpdateData = res;
            renderUpdateUI(res);
            return res;
        }
    } catch (e) {
        console.error("Failed to check panel updates:", e);
    }
    return null;
}

function renderUpdateUI(data) {
    const sidebarBadge = document.getElementById("sidebar-settings-update-badge");
    const navBadge = document.getElementById("settings-nav-update-badge");
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
        // Show exclamation marks
        if (sidebarBadge) sidebarBadge.style.display = "inline-flex";
        if (navBadge) navBadge.style.display = "inline-flex";

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
        if (sidebarBadge) sidebarBadge.style.display = "none";
        if (navBadge) navBadge.style.display = "none";

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

export function setupUpdateListeners() {
    const btnCheck = document.getElementById("btn-check-panel-update");
    if (btnCheck) {
        btnCheck.addEventListener("click", async () => {
            showToast("Проверка обновлений на GitHub...", "info");
            const res = await checkPanelUpdates(true);
            if (res && res.has_update) {
                showToast(`Доступна новая версия v${res.latest_version}!`, "success");
            } else if (res && res.success) {
                showToast("У вас установлена последняя версия панели.", "success");
            } else {
                showToast("Не удалось получить информацию с GitHub.", "error");
            }
        });
    }

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
}
