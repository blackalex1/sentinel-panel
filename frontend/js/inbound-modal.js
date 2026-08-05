import { loadInbounds as coreLoadInbounds, toggleInbound as coreToggleInbound, deleteInbound as coreDeleteInbound, renderInboundsList } from "./modules/inbound-core.js";
import {
    editInboundId,
    setEditInboundId as formSetEditInboundId,
    updateFormToggles as formUpdateFormToggles,
    handleProtocolChange as formHandleProtocolChange,
    handleInboundFormSubmit as formHandleInboundFormSubmit,
    openEditInboundModal as formOpenEditInboundModal,
    generateRandomPassword,
    switchInboundModalTab,
    updateTabVisibility,
    originalClients
} from "./modules/inbound-form.js";
import { setupRealityListeners } from "./modules/inbound-reality.js";
import { t } from "./i18n.js";
import { apiFetch } from "./api.js";
import { showToast } from "./ui.js";

export { editInboundId };
export function setEditInboundId(val) { return formSetEditInboundId(val); }
export function updateFormToggles() { return formUpdateFormToggles(); }
export function handleProtocolChange(proto) { return formHandleProtocolChange(proto); }
export async function handleInboundFormSubmit(e, loadInboundsCallback) { return await formHandleInboundFormSubmit(e, loadInboundsCallback); }
export async function openEditInboundModal(id) { return await formOpenEditInboundModal(id); }
export async function loadInbounds() { return await coreLoadInbounds(); }
export async function toggleInbound(id, state) { return await coreToggleInbound(id, state); }
export async function deleteInbound(id) { return await coreDeleteInbound(id); }

// Expose to window scope for HTML compatibility
window.deleteInbound = deleteInbound;
window.toggleInbound = toggleInbound;
window.openEditInboundModal = openEditInboundModal;

export function setupInboundListeners(loadInboundsCallback) {
    setupRealityListeners();

    const btnGenObfs = document.getElementById("btn-gen-obfs");
    if (btnGenObfs) {
        btnGenObfs.addEventListener("click", () => {
            const obfsInput = document.getElementById("ib-hysteria-obfs-password");
            if (obfsInput) {
                obfsInput.value = generateRandomPassword(16);
            }
        });
    }

    const ibGenPortBtn = document.getElementById("ib-gen-port-btn");
    if (ibGenPortBtn) {
        ibGenPortBtn.addEventListener("click", async () => {
            ibGenPortBtn.disabled = true;
            const res = await apiFetch("/api/system/free-port");
            ibGenPortBtn.disabled = false;
            if (res && res.success) {
                document.getElementById("ib-port").value = res.port;
            } else {
                showToast(res ? res.msg : "Не удалось подобрать свободный порт", "error");
            }
        });
    }

    // Modal Tabs switcher listeners
    document.querySelectorAll(".modal-tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const tabName = btn.getAttribute("data-tab");
            switchInboundModalTab(tabName);
        });
    });

    document.getElementById("add-inbound-btn").addEventListener("click", async () => {
        setEditInboundId(null);
        originalClients.length = 0; // Reset clients cache
        
        const protoSelect = document.getElementById("ib-protocol");
        if (protoSelect) {
            protoSelect.disabled = false;
        }
        
        document.getElementById("inbound-form").reset();
        document.getElementById("inbound-modal-title").innerText = t("inbounds_add_btn", "Создание подключения");
        document.querySelector("#inbound-form button[type='submit']").innerText = t("inbounds_add_btn", "Создать");
        
        const jsonEditor = document.getElementById("ib-json-editor");
        if (jsonEditor) {
            jsonEditor.value = "";
        }
        
        handleProtocolChange("vless");
        switchInboundModalTab("basic");
        
        const res = await apiFetch("/api/xray/x25519");
        if (res && res.success) {
            document.getElementById("ib-reality-pbk").value = res.publicKey;
            document.getElementById("ib-reality-priv").value = res.privateKey;
        }
        
        document.getElementById("inbound-modal").classList.add("active");
    });
    
    document.getElementById("ib-protocol").addEventListener("change", (e) => {
        handleProtocolChange(e.target.value);
    });
    
    document.getElementById("ib-network").addEventListener("change", () => {
        updateFormToggles();
    });
    
    document.getElementById("ib-security").addEventListener("change", () => {
        updateFormToggles();
    });

    document.getElementById("ib-tcp-type").addEventListener("change", () => {
        updateFormToggles();
    });

    document.getElementById("ib-hysteria-cert-mode").addEventListener("change", () => {
        updateFormToggles();
    });

    const ibHystMode = document.getElementById("ib-hysteria-mode");
    if (ibHystMode) {
        ibHystMode.addEventListener("change", () => {
            updateFormToggles();
        });
    }

    // VLESS Encryption Key Generation listeners
    const genVlessX25519Btn = document.getElementById("gen-vless-x25519-btn");
    const genVlessMlkemBtn = document.getElementById("gen-vless-mlkem-btn");
    const clearVlessEncBtn = document.getElementById("clear-vless-enc-btn");

    const generateVlessenc = async (type) => {
        const res = await apiFetch("/api/xray/vlessenc");
        if (res && res.success) {
            const keys = res[type];
            if (keys) {
                document.getElementById("ib-vless-decryption").value = keys.decryption || "none";
                document.getElementById("ib-vless-encryption").value = keys.encryption || "none";
                showToast(t("vless_enc_generated_success", "Ключи VLESS Encryption успешно сгенерированы!"));
                updateFormToggles();
            }
        } else {
            showToast(res ? res.msg : "Не удалось сгенерировать ключи", "error");
        }
    };

    if (genVlessX25519Btn) {
        genVlessX25519Btn.addEventListener("click", () => generateVlessenc("x25519"));
    }
    if (genVlessMlkemBtn) {
        genVlessMlkemBtn.addEventListener("click", () => generateVlessenc("mlkem768"));
    }
    if (clearVlessEncBtn) {
        clearVlessEncBtn.addEventListener("click", () => {
            document.getElementById("ib-vless-decryption").value = "none";
            document.getElementById("ib-vless-encryption").value = "none";
            updateFormToggles();
        });
    }

    // Exclusivity dynamic listeners
    const ibDecryptionInput = document.getElementById("ib-vless-decryption");
    if (ibDecryptionInput) {
        ibDecryptionInput.addEventListener("input", () => updateFormToggles());
    }
    const ibFallbackDestInput = document.getElementById("ib-fallback-dest");
    if (ibFallbackDestInput) {
        ibFallbackDestInput.addEventListener("input", () => updateFormToggles());
    }

    document.getElementById("ib-sniffing").addEventListener("change", () => {
        updateFormToggles();
    });
    
    const inboundForm = document.getElementById("inbound-form");
    if (inboundForm) {
        inboundForm.addEventListener("submit", (e) => {
            handleInboundFormSubmit(e, loadInboundsCallback);
        });
        inboundForm.querySelectorAll("input, select, textarea").forEach(el => {
            el.addEventListener("input", () => {
                el.classList.remove("input-invalid");
            });
            el.addEventListener("change", () => {
                el.classList.remove("input-invalid");
            });
        });
    }
    
    const sortSelect = document.getElementById("inbounds-sort");
    if (sortSelect) {
        sortSelect.addEventListener("change", () => {
            renderInboundsList();
        });
    }

    const searchInput = document.getElementById("inbounds-search");
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            const term = e.target.value.toLowerCase();
            document.querySelectorAll(".inbound-card").forEach(card => {
                const text = card.innerText.toLowerCase();
                card.style.display = text.includes(term) ? "flex" : "none";
            });
        });
    }
}
