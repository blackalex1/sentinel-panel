import { apiFetch } from "../../../api.js";
import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { loadXrayConfig } from "./render.js";

export async function saveXrayConfigToServer() {
    const res = await apiFetch("/api/xray/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: window.xrayConfig })
    });
    if (res && res.success) {
        showToast(t("config_saved_success", "Конфигурация успешно сохранена и ядро перезапущено!"));
        await loadXrayConfig();
    } else {
        throw new Error(res ? res.msg : t("config_save_error", "Ошибка при сохранении конфигурации"));
    }
}
