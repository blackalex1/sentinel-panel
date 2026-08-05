import { apiFetch } from "../../../api.js";
import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";

export async function saveHysteriaConfigToServer(inboundId, config, selectedIdx, reloadCallback) {
    const res = await apiFetch("/api/hysteria/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inbound_id: inboundId, config: config })
    });
    if (res && res.success) {
        showToast(t("config_saved_success", "Конфигурация успешно сохранена и ядро перезапущено!"));
        if (typeof reloadCallback === "function") {
            await reloadCallback(selectedIdx);
        }
    } else {
        throw new Error(res ? res.msg : t("config_save_error", "Ошибка при сохранении конфигурации"));
    }
}
