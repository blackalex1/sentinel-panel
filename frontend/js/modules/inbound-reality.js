import { apiFetch } from "../api.js";
import { showToast } from "../ui.js";
import { t } from "../i18n.js";

export function setupRealityListeners() {
    const genRealityBtn = document.getElementById("gen-x25519-keys-btn");
    if (genRealityBtn) {
        genRealityBtn.addEventListener("click", async () => {
            const res = await apiFetch("/api/xray/x25519");
            if (res && res.success) {
                document.getElementById("ib-reality-pbk").value = res.publicKey;
                document.getElementById("ib-reality-priv").value = res.privateKey;
                showToast(t("reality_keys_generated", "Ключи Reality успешно сгенерированы!"));
            } else {
                showToast(t("reality_keys_error", "Не удалось сгенерировать ключи"), "error");
            }
        });
    }

    const genShortIdsBtn = document.getElementById("gen-short-ids-btn");
    if (genShortIdsBtn) {
        genShortIdsBtn.addEventListener("click", () => {
            const chars = "0123456789abcdef";
            let result = "";
            for (let i = 0; i < 8; i++) {
                result += chars[Math.floor(Math.random() * 16)];
            }
            document.getElementById("ib-reality-shortids").value = result;
            showToast(t("short_id_generated", "Случайный Short ID сгенерирован!"));
        });
    }
}
