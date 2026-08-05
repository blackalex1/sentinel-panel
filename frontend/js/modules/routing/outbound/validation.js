import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";

export function validateOutboundForm() {
    let isValid = true;
    const errors = [];
    
    // Clear previous validation styling
    const inputs = document.querySelectorAll("#outbound-form input, #outbound-form select, #outbound-form textarea");
    inputs.forEach(el => el.classList.remove("input-invalid"));
    
    const remark = document.getElementById("ob-remark");
    if (remark && (!remark.value || !remark.value.trim())) {
        remark.classList.add("input-invalid");
        errors.push(t("validation_outbound_remark_required", "Описание исходящего подключения обязательно"));
        isValid = false;
    }
    
    const tag = document.getElementById("ob-tag");
    if (tag && (!tag.value || !tag.value.trim())) {
        tag.classList.add("input-invalid");
        errors.push(t("validation_outbound_tag_required", "Тег исходящего подключения обязателен"));
        isValid = false;
    }
    
    const protocol = document.getElementById("ob-protocol").value;
    if (protocol === "socks" || protocol === "http" || protocol === "shadowsocks" || protocol === "vless" || protocol === "hysteria" || protocol === "hysteria2") {
        const address = document.getElementById("ob-address");
        if (address && (!address.value || !address.value.trim())) {
            address.classList.add("input-invalid");
            errors.push(t("validation_outbound_address_required", "Адрес сервера обязателен"));
            isValid = false;
        }
        
        const port = document.getElementById("ob-port");
        if (port) {
            const portVal = parseInt(port.value);
            if (isNaN(portVal) || portVal < 1 || portVal > 65535) {
                port.classList.add("input-invalid");
                errors.push(t("validation_outbound_port_invalid", "Порт должен быть числом от 1 до 65535"));
                isValid = false;
            }
        }
        
        if (protocol === "shadowsocks" || protocol === "vless" || protocol === "hysteria" || protocol === "hysteria2") {
            const password = document.getElementById("ob-password");
            if (password && (!password.value || !password.value.trim())) {
                password.classList.add("input-invalid");
                if (protocol === "vless") {
                    errors.push(t("validation_outbound_uuid_required", "UUID обязателен"));
                } else if (protocol === "hysteria" || protocol === "hysteria2") {
                    errors.push(t("validation_outbound_auth_required", "Пароль (Auth) обязателен"));
                } else {
                    errors.push(t("validation_outbound_password_required", "Пароль / Ключ обязателен"));
                }
                isValid = false;
            }
        }
        
        if (protocol === "vless") {
            const security = document.getElementById("ob-security").value;
            if (security === "reality" || security === "tls") {
                const sni = document.getElementById("ob-sni");
                if (sni && (!sni.value || !sni.value.trim())) {
                    sni.classList.add("input-invalid");
                    errors.push(t("validation_outbound_sni_required", "SNI / ServerName обязателен"));
                    isValid = false;
                }
            }
            if (security === "reality") {
                const pbk = document.getElementById("ob-pbk");
                const shortid = document.getElementById("ob-shortid");
                
                if (pbk && (!pbk.value || !pbk.value.trim())) {
                    pbk.classList.add("input-invalid");
                    errors.push(t("validation_outbound_pbk_required", "Публичный ключ Reality обязателен"));
                    isValid = false;
                }
                if (shortid && (!shortid.value || !shortid.value.trim())) {
                    shortid.classList.add("input-invalid");
                    errors.push(t("validation_outbound_shortid_required", "Short ID Reality обязателен"));
                    isValid = false;
                }
            }
        } else if (protocol === "hysteria" || protocol === "hysteria2") {
            const sni = document.getElementById("ob-sni");
            if (sni && (!sni.value || !sni.value.trim())) {
                sni.classList.add("input-invalid");
                errors.push(t("validation_outbound_sni_required", "SNI / ServerName обязателен"));
                isValid = false;
            }
        }
    } else if (protocol === "wireguard") {
        const privKey = document.getElementById("ob-wg-private-key");
        if (privKey && (!privKey.value || !privKey.value.trim())) {
            privKey.classList.add("input-invalid");
            errors.push(t("validation_outbound_wg_privkey_required", "Приватный ключ WireGuard обязателен"));
            isValid = false;
        }
        const addresses = document.getElementById("ob-wg-addresses");
        if (addresses && (!addresses.value || !addresses.value.trim())) {
            addresses.classList.add("input-invalid");
            errors.push(t("validation_outbound_wg_addresses_required", "Адреса интерфейса WireGuard обязательны"));
            isValid = false;
        }
        const peerPub = document.getElementById("ob-wg-peer-public-key");
        if (peerPub && (!peerPub.value || !peerPub.value.trim())) {
            peerPub.classList.add("input-invalid");
            errors.push(t("validation_outbound_wg_peer_pubkey_required", "Публичный ключ пира WireGuard обязателен"));
            isValid = false;
        }
        const endpoint = document.getElementById("ob-wg-endpoint");
        if (endpoint && (!endpoint.value || !endpoint.value.trim())) {
            endpoint.classList.add("input-invalid");
            errors.push(t("validation_outbound_wg_endpoint_required", "Эндпоинт пира WireGuard обязателен"));
            isValid = false;
        }
    }
    
    if (!isValid && errors.length > 0) {
        showToast(errors[0], "error");
    }
    return isValid;
}
