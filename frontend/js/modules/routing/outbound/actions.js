import { apiFetch } from "../../../api.js";
import { showToast, showConfirmDialog } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { loadOutbounds } from "./table_render.js";

export async function toggleOutbound(id, checked) {
    const listRes = await apiFetch("/api/routing/outbounds");
    if (!listRes || !listRes.success) return;
    const ob = listRes.obj.find(x => x.id === id);
    if (!ob) return;
    
    let settingsObj = {};
    try {
        settingsObj = JSON.parse(ob.settings || "{}");
    } catch(e) {}
    
    const res = await apiFetch(`/api/routing/outbounds/update/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            remark: ob.remark,
            protocol: ob.protocol,
            tag: ob.tag,
            settings: settingsObj,
            enable: checked ? 1 : 0
        })
    });
    
    if (res && res.success) {
        showToast(checked ? t("routing_outbound_enabled", "Исходящее подключение включено") : t("routing_outbound_disabled", "Исходящее подключение выключено"));
        loadOutbounds();
    }
}

export async function deleteOutbound(id) {
    const confirmed = await showConfirmDialog(t("routing_confirm_delete_outbound", "Вы уверены, что хотите удалить это исходящее подключение? Любые правила маршрутизации, ссылающиеся на него, больше не будут работать."));
    if (!confirmed) return;
    
    const res = await apiFetch(`/api/routing/outbounds/delete/${id}`, { method: "POST" });
    if (res && res.success) {
        showToast(t("routing_outbound_deleted", "Исходящее подключение успешно удалено"));
        loadOutbounds();
        // Trigger routing rules reload in routing.js via event to avoid circular dependencies and dynamic import
        window.dispatchEvent(new CustomEvent("routing-rules-updated"));
    } else {
        showToast(res ? res.msg : "Error", "error");
    }
}
