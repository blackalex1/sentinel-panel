import { apiFetch } from "./api.js";
import { showToast } from "./ui.js";
import { t } from "./i18n.js";
import {
    outboundsCache,
    loadOutbounds,
    openOutboundModal,
    toggleOutbound,
    deleteOutbound,
    updateOutboundFormFields,
    populateOutboundDropdowns,
    validateOutboundForm,
    parseProxyLink
} from "./modules/routing-outbounds.js";
import {
    loadRoutingRules,
    openRoutingRuleModal,
    toggleRoutingRule,
    deleteRoutingRule,
    setupRoutingRulesListeners
} from "./modules/routing-rules.js";
import "./modules/drag-drop.js";
import { setupOutboundFormListeners } from "./modules/routing/outbound-form.js";

// Re-export outbounds and rules for outside use
export { loadOutbounds, loadRoutingRules };

window.addEventListener("routing-rules-updated", () => {
    loadRoutingRules();
});

// Global functions exposed to window scope for HTML onclick bindings
window.openOutboundModal = openOutboundModal;
window.toggleOutbound = toggleOutbound;
window.deleteOutbound = deleteOutbound;
window.openRoutingRuleModal = openRoutingRuleModal;
window.toggleRoutingRule = toggleRoutingRule;
window.deleteRoutingRule = deleteRoutingRule;

window.testOutbound = async function(id, testType, btnElement) {
    const icon = btnElement.querySelector("i");
    const originalClass = icon.className;
    icon.className = "fa-solid fa-spinner fa-spin";
    btnElement.disabled = true;
    
    try {
        const res = await apiFetch(`/api/routing/outbounds/test/${id}?test_type=${testType}`, { method: "POST" });
        if (res && res.success) {
            showToast(t("routing_test_success", "Соединение успешно!") + ` (${res.ping} ms)`);
            const settingsCell = btnElement.closest("tr").querySelector("td:nth-child(4)");
            if (settingsCell) {
                const originalText = settingsCell.innerText.split(" (")[0];
                const typeLabel = testType.toUpperCase();
                settingsCell.innerHTML = `${originalText} <span style="color: var(--accent-green); font-size: 12px; font-weight: 600;">(${typeLabel}: ${res.ping} ms)</span>`;
            }
        } else {
            showToast(res ? res.msg : t("routing_toast_test_error", "Ошибка проверки"), "error");
            const settingsCell = btnElement.closest("tr").querySelector("td:nth-child(4)");
            if (settingsCell) {
                const originalText = settingsCell.innerText.split(" (")[0];
                const typeLabel = testType.toUpperCase();
                const errMsg = res && res.msg ? res.msg : "Error";
                settingsCell.innerHTML = `${originalText} <span style="color: var(--accent-rose); font-size: 11px; font-weight: 600;" title="${errMsg}">(${typeLabel}: Error)</span>`;
            }
        }
    } catch(e) {
        showToast("Error testing outbound", "error");
    } finally {
        icon.className = originalClass;
        btnElement.disabled = false;
    }
};

export function setupRoutingListeners() {
    setupRoutingRulesListeners();
    setupOutboundFormListeners();
}
