import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";

export async function loadGeoInfo() {
    const res = await apiFetch("/api/xray/geo");
    if (!res || !res.success) return;

    const info = res.obj;

    _applyGeoInfoToUI(info);

    // Заполняем поля URL (показываем только если не дефолтный)
    const geoipUrlInput   = document.getElementById("geo-geoip-url");
    const geositeUrlInput = document.getElementById("geo-geosite-url");

    if (geoipUrlInput) {
        // Храним дефолт в data-атрибуте для placeholder/сброса
        geoipUrlInput.setAttribute("data-default", info.geoip_url || "");
        geoipUrlInput.placeholder = info.geoip_url || "https://github.com/.../geoip.dat";
        // Показываем кастомный URL только если он отличается от дефолтного
        const savedGeoipUrl = geoipUrlInput.getAttribute("data-saved") || "";
        if (savedGeoipUrl && savedGeoipUrl !== info.geoip_url) {
            geoipUrlInput.value = savedGeoipUrl;
        }
    }
    if (geositeUrlInput) {
        geositeUrlInput.setAttribute("data-default", info.geosite_url || "");
        geositeUrlInput.placeholder = info.geosite_url || "https://github.com/.../geosite.dat";
        const savedGeositeUrl = geositeUrlInput.getAttribute("data-saved") || "";
        if (savedGeositeUrl && savedGeositeUrl !== info.geosite_url) {
            geositeUrlInput.value = savedGeositeUrl;
        }
    }
}

export function setupGeoListeners() {
    // --- Кнопка "Сохранить URL" ---
    const saveBtn = document.getElementById("geo-save-btn");
    if (saveBtn) {
        saveBtn.addEventListener("click", async () => {
            const geoipUrlEl = document.getElementById("geo-geoip-url");
            const geositeUrlEl = document.getElementById("geo-geosite-url");
            const geoipUrl   = (geoipUrlEl ? geoipUrlEl.value : "").trim();
            const geositeUrl = (geositeUrlEl ? geositeUrlEl.value : "").trim();

            // Базовая валидация
            for (const [label, url] of [["geoip_url", geoipUrl], ["geosite_url", geositeUrl]]) {
                if (url && !url.toLowerCase().endsWith(".dat")) {
                    showToast(t("geo_err_dat", `${label}: URL должен заканчиваться на .dat`), "warning");
                    return;
                }
            }

            const res = await apiFetch("/api/xray/geo/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ geoip_url: geoipUrl, geosite_url: geositeUrl })
            });

            if (res && res.success) {
                // Сохраняем как data-saved для последующей загрузки
                const geoipUrlInput = document.getElementById("geo-geoip-url");
                const geositeUrlInput = document.getElementById("geo-geosite-url");
                if (geoipUrlInput) geoipUrlInput.setAttribute("data-saved", geoipUrl);
                if (geositeUrlInput) geositeUrlInput.setAttribute("data-saved", geositeUrl);
                showToast(t("geo_saved", "URL источников geo-файлов сохранены"));
                await loadGeoInfo();
            } else {
                showToast(res ? res.msg : t("geo_save_error", "Ошибка сохранения URL"), "error");
            }
        });
    }

    // --- Кнопка "Сбросить URL к дефолтным" ---
    const resetBtn = document.getElementById("geo-reset-btn");
    if (resetBtn) {
        resetBtn.addEventListener("click", async () => {
            const geoipInput   = document.getElementById("geo-geoip-url");
            const geositeInput = document.getElementById("geo-geosite-url");
            if (geoipInput)   geoipInput.value = "";
            if (geositeInput) geositeInput.value = "";

            const res = await apiFetch("/api/xray/geo/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ geoip_url: "", geosite_url: "" })
            });

            if (res && res.success) {
                showToast(t("geo_reset", "URLs reset to default (Loyalsoldier)"));
                await loadGeoInfo();
            } else {
                showToast(res ? res.msg : t("geo_err_reset", "Failed to reset URLs"), "error");
            }
        });
    }

    // --- Кнопка "Обновить geo-файлы" ---
    const updateBtn   = document.getElementById("geo-update-btn");
    const statusSpan  = document.getElementById("geo-update-status");

    if (updateBtn) {
        updateBtn.addEventListener("click", async () => {
            updateBtn.disabled = true;
            const origHtml = updateBtn.innerHTML;
            updateBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin" style="margin-right:6px;"></i><span>${t("geo_updating", "Downloading...")}</span>`;

            if (statusSpan) {
                statusSpan.textContent = t("geo_updating_status", "⏳ Downloading files...");
                statusSpan.style.display = "inline";
                statusSpan.style.color = "var(--text-secondary)";
            }

            showToast(t("geo_update_started", "Начато скачивание geo-файлов, пожалуйста подождите..."), "info");

            const res = await apiFetch("/api/xray/geo/update", { method: "POST" });

            updateBtn.disabled = false;
            updateBtn.innerHTML = origHtml;

            if (res && (res.success || res.partial)) {
                if (statusSpan) {
                    statusSpan.textContent = `✓ ${res.msg}`;
                    statusSpan.style.color = "var(--accent-teal, #2ed573)";
                    statusSpan.style.display = "inline";
                }
                showToast(
                    res.success
                        ? t("geo_update_success", "Geo-файлы успешно обновлены! Xray перезапущен.")
                        : t("geo_update_partial", `Частично обновлено: ${res.msg}`),
                    res.success ? "success" : "warning"
                );
                // Обновляем статус-карточки с новыми данными
                if (res.info) {
                    _applyGeoInfoToUI(res.info);
                } else {
                    await loadGeoInfo();
                }
            } else {
                if (statusSpan) {
                    statusSpan.textContent = `✗ ${(res && res.msg) || t("geo_err_generic", "Error")}`;
                    statusSpan.style.color = "var(--accent-rose, #ff4757)";
                    statusSpan.style.display = "inline";
                }
                showToast(res ? res.msg : t("geo_update_error", "Ошибка обновления geo-файлов"), "error");
            }
        });
    }
}

/** Вспомогательная функция: применяет данные geo-файлов к UI без доп. запроса */
function _applyGeoInfoToUI(info) {
    const files = [
        { key: "geoip.dat",   badgeId: "geo-geoip-badge",   metaId: "geo-geoip-meta"   },
        { key: "geosite.dat", badgeId: "geo-geosite-badge",  metaId: "geo-geosite-meta" },
    ];
    for (const { key, badgeId, metaId } of files) {
        const badge = document.getElementById(badgeId);
        const meta  = document.getElementById(metaId);
        if (!badge || !meta) continue;
        const f = info[key];
        if (f && f.exists) {
            badge.textContent = t("geo_installed", "✓ Installed");
            badge.className = "tag-badge tag-badge-direct";
            meta.textContent = t("geo_meta_info", "{size} KB · Updated: {date}")
                .replace("{size}", f.size_kb)
                .replace("{date}", f.updated_at);
        } else {
            badge.textContent = t("geo_missing", "✗ Missing");
            badge.className = "tag-badge tag-badge-blocked";
            meta.textContent = t("geo_not_found", "File not found in bin/ directory");
        }
    }
}
