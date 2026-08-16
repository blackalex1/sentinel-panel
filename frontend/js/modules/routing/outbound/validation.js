import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";
import { getCurrentOutboundValues } from "./modal_manager.js";

export function validateOutboundForm() {
    let isValid = true;
    const errors = [];
    
    // Clear previous validation styling
    const inputs = document.querySelectorAll("#outbound-form input, #outbound-form select, #outbound-form textarea");
    inputs.forEach(el => el.classList.remove("input-invalid"));
    
    const vals = getCurrentOutboundValues() || {};
    const protocol = document.getElementById("ob-protocol") ? document.getElementById("ob-protocol").value : (vals.protocol || "vless");

    const remark = document.getElementById("ob-remark");
    const remarkVal = remark ? remark.value.trim() : vals.remark;
    if (!remarkVal) {
        if (remark) remark.classList.add("input-invalid");
        errors.push(t("validation_outbound_remark_required", "Описание исходящего подключения обязательно"));
        isValid = false;
    }
    
    const tag = document.getElementById("ob-tag");
    const tagVal = tag ? tag.value.trim() : vals.tag;
    if (!tagVal) {
        if (tag) tag.classList.add("input-invalid");
        errors.push(t("validation_outbound_tag_required", "Тег исходящего подключения обязателен"));
        isValid = false;
    }

    if (protocol !== "freedom" && protocol !== "direct" && protocol !== "blackhole" && protocol !== "block") {
        const host = document.getElementById("ob-host");
        const hostVal = host ? host.value.trim() : vals.host;
        if (!hostVal && protocol !== "warp") {
            if (host) host.classList.add("input-invalid");
            errors.push(t("validation_outbound_address_required", "Адрес сервера обязателен"));
            isValid = false;
        }

        const port = document.getElementById("ob-port");
        const portVal = port ? parseInt(port.value) : parseInt(vals.port);
        if (isNaN(portVal) || portVal < 1 || portVal > 65535) {
            if (port) port.classList.add("input-invalid");
            errors.push(t("validation_outbound_port_invalid", "Порт должен быть числом от 1 до 65535"));
            isValid = false;
        }

        if (protocol === "vless") {
            const uuid = document.getElementById("ob-uuid") || document.getElementById("ob-password");
            const uuidVal = uuid ? uuid.value.trim() : (vals.uuid || vals.password);
            if (!uuidVal) {
                if (uuid) uuid.classList.add("input-invalid");
                errors.push(t("validation_outbound_uuid_required", "UUID обязателен"));
                isValid = false;
            }

            const sec = document.getElementById("ob-security") ? document.getElementById("ob-security").value : (vals.security || "reality");
            if (sec === "reality") {
                const pbk = document.getElementById("ob-pbk");
                const pbkVal = pbk ? pbk.value.trim() : (vals.publicKey || vals.pbk);
                if (!pbkVal) {
                    if (pbk) pbk.classList.add("input-invalid");
                    errors.push(t("validation_outbound_pbk_required", "Публичный ключ Reality обязателен"));
                    isValid = false;
                }
            }
        } else if (protocol === "hysteria2" || protocol === "hysteria") {
            const pass = document.getElementById("ob-password");
            const passVal = pass ? pass.value.trim() : (vals.password || vals.auth);
            if (!passVal) {
                if (pass) pass.classList.add("input-invalid");
                errors.push(t("validation_outbound_auth_required", "Пароль (Auth) обязателен"));
                isValid = false;
            }
        } else if (protocol === "shadowsocks" || protocol === "trojan") {
            const pass = document.getElementById("ob-password");
            const passVal = pass ? pass.value.trim() : vals.password;
            if (!passVal) {
                if (pass) pass.classList.add("input-invalid");
                errors.push(t("validation_outbound_password_required", "Пароль обязателен"));
                isValid = false;
            }
        }
    }

    if (!isValid && errors.length > 0) {
        showToast(errors[0], "warning");
    }

    return isValid;
}
