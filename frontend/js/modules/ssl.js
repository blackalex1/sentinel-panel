import { apiFetch } from "../api.js";
import { showToast } from "../ui.js";
import { t } from "../i18n.js";

export function setupSslListeners() {
    const btnGenerateSsl = document.getElementById("btn-generate-ssl");
    if (btnGenerateSsl) {
        btnGenerateSsl.addEventListener("click", async () => {
            const domain = document.getElementById("setting-ssl-domain").value.trim();
            const email = document.getElementById("setting-ssl-email").value.trim();
            
            if (!domain) {
                showToast(t("ssl_fill_fields", "Пожалуйста, укажите домен для выпуска сертификата"), "warning");
                return;
            }
            
            btnGenerateSsl.disabled = true;
            btnGenerateSsl.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Выпускается...';
            showToast(t("ssl_issue_started", "Запущен процесс автоматического выпуска SSL. Это может занять до 1 минуты."), "info");
            
            const res = await apiFetch("/api/ssl/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ domain, email })
            });
            
            btnGenerateSsl.disabled = false;
            btnGenerateSsl.innerHTML = '<i class="fa-solid fa-shield-halved"></i> Выпустить сертификат';
            
            if (res && res.success) {
                showToast(t("ssl_issue_success", "SSL-сертификат успешно выпущен и установлен!"));
            } else {
                showToast(res ? res.msg : t("ssl_issue_error", "Не удалось выпустить сертификат"), "error");
            }
        });
    }
}
