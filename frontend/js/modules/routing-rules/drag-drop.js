import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { loadRoutingRules } from "./core.js";

window.moveRule = async function(id, direction) {
    const listRes = await apiFetch("/api/routing/rules");
    if (!listRes || !listRes.success) return;
    
    const rules = listRes.obj;
    const idx = rules.findIndex(x => x.id === id);
    if (idx === -1) return;
    
    let swapIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= rules.length) return;
    
    // Swap elements in list
    const temp = rules[idx];
    rules[idx] = rules[swapIdx];
    rules[swapIdx] = temp;
    
    // Send new IDs list to sort API
    const ruleIds = rules.map(r => r.id);
    const sortRes = await apiFetch("/api/routing/rules/sort", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rule_ids: ruleIds })
    });
    
    if (sortRes && sortRes.success) {
        showToast(t("routing_priority_updated", "Приоритеты правил успешно обновлены!"));
        loadRoutingRules();
    }
};
