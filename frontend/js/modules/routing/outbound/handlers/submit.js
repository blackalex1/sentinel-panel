import { apiFetch } from "../../../../api.js";
import { showToast } from "../../../../ui.js";
import { t } from "../../../../i18n.js";
import { loadOutbounds } from "../../../routing-outbounds.js";
import { validateOutboundForm } from "../validation.js";
import { getCurrentOutboundValues } from "../modal_manager.js";
import { buildOutboundPayload } from "../payload_builder.js";

export function bindSubmitListener() {
    const outboundForm = document.getElementById("outbound-form");
    const submitBtn = document.getElementById("ob-submit-btn");

    async function handleSave(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        if (!validateOutboundForm()) {
            return;
        }

        const id = document.getElementById("ob-id").value;
        const vals = getCurrentOutboundValues() || {};
        const { protocol, settings, streamSettings } = buildOutboundPayload(vals);

        // Read top fields
        const remark = (document.getElementById("ob-remark") ? document.getElementById("ob-remark").value.trim() : vals.remark) || "Outbound";
        const tag = (document.getElementById("ob-tag") ? document.getElementById("ob-tag").value.trim() : vals.tag) || `${protocol}-${Math.floor(Math.random()*1000)}`;
        const enable = (document.getElementById("ob-enable") ? document.getElementById("ob-enable").checked : (vals.enable !== false)) ? 1 : 0;

        // Attach fallback route and failover strategy if set
        const fallbackRoute = (document.getElementById("fallback_outbound") ? document.getElementById("fallback_outbound").value : vals.fallback_outbound) || "";
        const fallbackStrategy = (document.getElementById("fallback_strategy") ? document.getElementById("fallback_strategy").value : vals.fallback_strategy) || "priority";
        const healthCheckInt = parseInt(document.getElementById("health_check_interval") ? document.getElementById("health_check_interval").value : vals.health_check_interval) || 30;

        if (fallbackRoute) {
            settings.backup_outbounds = [fallbackRoute];
            settings.fallback_outbound = fallbackRoute;
            settings.fallback_strategy = fallbackStrategy;
            settings.health_check_interval = healthCheckInt;
        } else {
            delete settings.backup_outbounds;
            delete settings.fallback_outbound;
            delete settings.fallback_strategy;
            delete settings.health_check_interval;
        }

        const url = id ? `/api/routing/outbounds/update/${id}` : "/api/routing/outbounds/create";
        const res = await apiFetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ remark, protocol, tag, settings, streamSettings, enable })
        });
        
        if (res && res.success) {
            showToast(id ? t("routing_outbound_updated", "Исходящее подключение обновлено") : t("routing_outbound_created", "Исходящее подключение создано"));
            document.getElementById("outbound-modal").classList.remove("active");
            loadOutbounds();
        } else {
            showToast(res ? res.msg : "Error", "error");
        }
    }

    if (outboundForm) {
        outboundForm.addEventListener("submit", handleSave);
    }
    if (submitBtn) {
        submitBtn.addEventListener("click", handleSave);
    }
}
