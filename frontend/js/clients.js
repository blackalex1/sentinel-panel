import {
    activeInboundId,
    activeInboundProtocol,
    editModeClientEmail,
    setEditModeEmail as coreSetEditModeEmail,
    openClientsModal as coreOpenClientsModal,
    toggleClientActiveStatus as coreToggleClientActiveStatus,
    setLoadInboundsCallback as coreSetLoadInboundsCallback,
    deleteClient as coreDeleteClient,
    openLinksModal as coreOpenLinksModal,
    resetClientTraffic as coreResetClientTraffic,
    resetAllClientsTrafficForInbound as coreResetAllClientsTrafficForInbound
} from "./modules/clients-core.js";

import {
    openEditClientModal as formOpenEditClientModal,
    handleClientFormSubmit as formHandleClientFormSubmit
} from "./modules/clients-form.js";

import { generateUUID } from "./ui.js";
import { t } from "./i18n.js";

export { activeInboundId, activeInboundProtocol, editModeClientEmail };

export function setEditModeEmail(email) {
    return coreSetEditModeEmail(email);
}

export async function openClientsModal(inboundId) {
    return await coreOpenClientsModal(inboundId);
}

export async function toggleClientActiveStatus(inboundId, clientData, enabled) {
    return await coreToggleClientActiveStatus(inboundId, clientData, enabled);
}

export function openEditClientModal(inboundId, clientData) {
    return formOpenEditClientModal(inboundId, clientData);
}

export function setLoadInboundsCallback(cb) {
    return coreSetLoadInboundsCallback(cb);
}

export async function deleteClient(inboundId, clientId, loadInboundsCallback) {
    return await coreDeleteClient(inboundId, clientId, loadInboundsCallback);
}

export async function openLinksModal(inboundId, email) {
    return await coreOpenLinksModal(inboundId, email);
}

export async function resetClientTraffic(inboundId, email) {
    return await coreResetClientTraffic(inboundId, email);
}

export async function resetAllClientsTrafficForInbound(inboundId) {
    return await coreResetAllClientsTrafficForInbound(inboundId);
}

export async function handleClientFormSubmit(e, loadInboundsCallback) {
    return await formHandleClientFormSubmit(e, loadInboundsCallback);
}

function generateClientPassword(length = 16) {
    const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let pwd = "";
    for (let i = 0; i < length; i++) {
        pwd += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return pwd;
}

function generateRandomUsername() {
    const prefixes = [
        // Standard & Network
        "user", "client", "guest", "member", "peer", "agent", "runner", "scout", "voyager", "pioneer", "relay", "proxy", "node",
        // Cyber & Stealth
        "shadow", "ghost", "cyber", "spectre", "sentinel", "phantom", "stealth", "cipher", "shroud", "viper", "cobra", "raven",
        "falcon", "phoenix", "ninja", "samurai", "ronin", "anonym", "mask", "blade", "razor", "tracer", "hacker", "veiled", "shade",
        // Tech & Science
        "nexus", "vector", "matrix", "vertex", "quantum", "pulse", "orbit", "prism", "proton", "electron", "neutron", "cortex",
        "binary", "synapse", "kernel", "packet", "buffer", "circuit", "stream", "cluster", "grid", "data", "core", "signal", "beacon",
        // Cosmic & Space
        "alpha", "beta", "omega", "titan", "orion", "sirius", "hyperion", "aurora", "eclipse", "nova", "pulsar", "nebula", "zenith",
        "apex", "astral", "cosmos", "astro", "comet", "meteor", "galaxy", "quasar", "starlight", "solar", "lunar",
        // Animals & Beasts
        "wolf", "jaguar", "panther", "tiger", "lion", "hawk", "eagle", "condor", "lynx", "leopard", "puma", "fox", "grizzly",
        "bear", "kraken", "dragon", "hydra", "griffin", "sphinx", "chimera", "mantis",
        // Elements & Forces
        "blaze", "frost", "storm", "spark", "flame", "thunder", "vortex", "drift", "gale", "inferno", "magma", "glacier",
        "tsunami", "sonic", "plasma", "static", "zero", "frostbyte", "thunderbolt",
        // Mythic & Guardians
        "atlas", "chronos", "zeus", "ares", "hermes", "valkyrie", "odin", "thor", "loki", "kratos", "spartan", "legion",
        "vanguard", "guardian", "warden", "paladin", "ranger", "knight", "chief", "officer", "captain",
        // Crypto & Abstract
        "entropy", "enigma", "hash", "vault", "bunker", "shield", "armor", "aether", "aura", "flux", "echo", "horizon", "infinity"
    ];
    const randomPrefix = prefixes[Math.floor(Math.random() * prefixes.length)];
    const randomNum = Math.floor(Math.random() * 9000) + 1000;
    return `${randomPrefix}_${randomNum}`;
}

export function setupClientListeners(loadInboundsCallback) {
    const addClientBtn = document.getElementById("add-client-btn");
    if (addClientBtn) {
        addClientBtn.addEventListener("click", () => {
            const clientForm = document.getElementById("client-form");
            if (clientForm) clientForm.reset();
            setEditModeEmail(null);
            const emailInput = document.getElementById("c-email");
            if (emailInput) {
                emailInput.disabled = false;
                emailInput.value = generateRandomUsername();
            }
            const modalTitle = document.getElementById("client-modal-title");
            if (modalTitle) modalTitle.innerText = t("client_add_title", "Добавление клиента");
            
            const ibIdInput = document.getElementById("client-ib-id");
            if (ibIdInput) ibIdInput.value = activeInboundId || "";
            
            const flowGroup = document.getElementById("client-flow-group");
            const vmessGroup = document.getElementById("client-vmess-group");
            
            if (flowGroup) flowGroup.style.display = (activeInboundProtocol === "vless") ? "block" : "none";
            if (vmessGroup) vmessGroup.style.display = (activeInboundProtocol === "vmess") ? "block" : "none";
            
            const uuidInput = document.getElementById("c-uuid");
            if (uuidInput) {
                if (activeInboundProtocol === "vless" || activeInboundProtocol === "vmess") {
                    uuidInput.value = generateUUID();
                } else {
                    uuidInput.value = generateClientPassword(16);
                }
            }
            
            const limitIpInput = document.getElementById("c-limit-ip");
            if (limitIpInput) limitIpInput.value = 0;
            const allowedIpsInput = document.getElementById("c-allowed-ips");
            if (allowedIpsInput) allowedIpsInput.value = "";
            const enableInput = document.getElementById("c-enable");
            if (enableInput) enableInput.checked = true;
            
            const clientModal = document.getElementById("client-modal");
            if (clientModal) clientModal.classList.add("active");
        });
    }
    
    const genEmailBtn = document.getElementById("c-gen-email-btn");
    if (genEmailBtn) {
        genEmailBtn.addEventListener("click", () => {
            const emailInput = document.getElementById("c-email");
            if (emailInput) emailInput.value = generateRandomUsername();
        });
    }
    
    const genUuidBtn = document.getElementById("c-gen-uuid-btn");
    if (genUuidBtn) {
        genUuidBtn.addEventListener("click", () => {
            const uuidInput = document.getElementById("c-uuid");
            if (uuidInput) {
                if (activeInboundProtocol === "vless" || activeInboundProtocol === "vmess") {
                    uuidInput.value = generateUUID();
                } else {
                    uuidInput.value = generateClientPassword(16);
                }
            }
        });
    }
    
    const clientForm = document.getElementById("client-form");
    if (clientForm) {
        clientForm.addEventListener("submit", (e) => {
            handleClientFormSubmit(e, loadInboundsCallback);
        });
    }
}
