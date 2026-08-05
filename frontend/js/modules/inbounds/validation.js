import { showToast } from "../../ui.js";
import { t } from "../../i18n.js";
import { switchInboundModalTab } from "./core.js";

export function validateInboundForm() {
    let isValid = true;
    const errors = [];
    
    // Clear previous validation styling
    const inputs = document.querySelectorAll("#inbound-form input, #inbound-form select, #inbound-form textarea");
    inputs.forEach(el => el.classList.remove("input-invalid"));
    
    const remark = document.getElementById("ib-remark");
    if (remark && (!remark.value || !remark.value.trim())) {
        remark.classList.add("input-invalid");
        errors.push(t("validation_inbound_remark_required", "Название подключения обязательно"));
        isValid = false;
    }
    
    const port = document.getElementById("ib-port");
    if (port) {
        const portVal = parseInt(port.value);
        if (isNaN(portVal) || portVal < 1 || portVal > 65535) {
            port.classList.add("input-invalid");
            errors.push(t("validation_inbound_port_invalid", "Порт должен быть числом от 1 до 65535"));
            isValid = false;
        }
    }
    
    const proto = document.getElementById("ib-protocol").value;
    if (proto === "vless" || proto === "vmess" || proto === "trojan") {
        const security = document.getElementById("ib-security").value;
        if (security === "reality") {
            const priv = document.getElementById("ib-reality-priv");
            const pbk = document.getElementById("ib-reality-pbk");
            const dest = document.getElementById("ib-reality-dest");
            
            if (priv && (!priv.value || !priv.value.trim())) {
                priv.classList.add("input-invalid");
                errors.push(t("validation_inbound_reality_priv_required", "Приватный ключ Reality обязателен"));
                isValid = false;
            }
            if (pbk && (!pbk.value || !pbk.value.trim())) {
                pbk.classList.add("input-invalid");
                errors.push(t("validation_inbound_reality_pbk_required", "Публичный ключ Reality обязателен"));
                isValid = false;
            }
            if (dest && (!dest.value || !dest.value.trim())) {
                dest.classList.add("input-invalid");
                errors.push(t("validation_inbound_reality_dest_required", "Направление маскировки Reality обязательно"));
                isValid = false;
            }
        }
    } else if (proto === "hysteria2") {
        const hystMode = document.getElementById("ib-hysteria-mode").value || "masq";
        if (hystMode === "obfs") {
            const obfs = document.getElementById("ib-hysteria-obfs-password");
            if (obfs && (!obfs.value || !obfs.value.trim())) {
                obfs.classList.add("input-invalid");
                errors.push(t("validation_inbound_hysteria_obfs_required", "Пароль обфускации Hysteria 2 обязателен"));
                isValid = false;
            }
        }
        
        const certMode = document.getElementById("ib-hysteria-cert-mode").value;
        if (certMode === "custom") {
            const certPath = document.getElementById("ib-hysteria-cert-path");
            const keyPath = document.getElementById("ib-hysteria-key-path");
            
            if (certPath && (!certPath.value || !certPath.value.trim())) {
                certPath.classList.add("input-invalid");
                errors.push(t("validation_inbound_hysteria_cert_required", "Путь к файлу сертификата обязателен"));
                isValid = false;
            }
            if (keyPath && (!keyPath.value || !keyPath.value.trim())) {
                keyPath.classList.add("input-invalid");
                errors.push(t("validation_inbound_hysteria_key_required", "Путь к приватному ключу обязателен"));
                isValid = false;
            }
        }
    }
    
    if (!isValid && errors.length > 0) {
        showToast(errors[0], "error"); // Show first error
        
        // Find the first invalid element and switch to its containing tab panel
        const firstInvalid = document.querySelector("#inbound-form .input-invalid");
        if (firstInvalid) {
            const panel = firstInvalid.closest(".tab-panel");
            if (panel) {
                const tabName = panel.id.replace("tab-panel-", "");
                switchInboundModalTab(tabName);
            }
        }
    }
    return isValid;
}
