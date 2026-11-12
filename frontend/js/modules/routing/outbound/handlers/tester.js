import { apiFetch } from "../../../../api.js";
import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { validateOutboundForm } from "../validation.js";
import { getCurrentOutboundValues } from "../modal_manager.js";
import { buildOutboundPayload } from "../payload_builder.js";

export function bindTesterListener() {
    const testObBtn = document.getElementById("ob-test-btn");
    if (!testObBtn) return;

    testObBtn.addEventListener("click", async () => {
        if (!validateOutboundForm()) return;
        
        const icon = testObBtn.querySelector("i");
        const btnText = testObBtn.querySelector("span");
        const originalClass = icon ? icon.className : "";
        const originalText = btnText ? btnText.innerText : "";
        
        if (icon) icon.className = "fa-solid fa-spinner fa-spin";
        if (btnText) btnText.innerText = t("routing_testing", "Проверка...");
        testObBtn.disabled = true;
        
        try {
            const vals = getCurrentOutboundValues() || {};
            const testTypeEl = document.getElementById("ob-test-type");
            const test_type = testTypeEl ? testTypeEl.value : "http";

            const { protocol, host, rawPort, settings, streamSettings } = buildOutboundPayload(vals);

            if (protocol !== "freedom" && protocol !== "direct" && protocol !== "blackhole" && protocol !== "block" && protocol !== "warp") {
                if (!host || (!String(rawPort).includes("-") && !String(rawPort).includes(",") && isNaN(parseInt(rawPort, 10)))) {
                    showToast(t("routing_err_host_port", "Укажите адрес и порт сервера прокси"), "warning");
                    return;
                }
            }

            const res = await apiFetch("/api/routing/outbounds/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ protocol, settings, streamSettings, test_type })
            });
            
            if (res && res.success) {
                showToast(t("routing_test_success", "Соединение успешно!") + ` (${res.ping} ms)`);
            } else {
                showToast(res ? res.msg : t("routing_toast_connection_error", "Ошибка соединения"), "error");
            }
        } catch (err) {
            showToast("Error: " + err.message, "error");
        } finally {
            if (icon) icon.className = originalClass;
            if (btnText) btnText.innerText = originalText;
            testObBtn.disabled = false;
        }
    });
}
