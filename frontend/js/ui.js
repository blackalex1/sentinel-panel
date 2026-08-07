// Shared UI Utility functions
import { translatePage, t } from "./i18n.js";

window.addEventListener("show-toast", (e) => {
    if (e.detail && e.detail.text) {
        showToast(e.detail.text, e.detail.type || "success");
    }
});

export function showToast(text, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    
    let icon = "fa-circle-check";
    if (type === "error") icon = "fa-circle-xmark";
    else if (type === "info") icon = "fa-circle-info";
    
    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${text}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = "toastIn 0.3s reverse forwards";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

export function formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0 || isNaN(bytes)) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const val = (bytes / Math.pow(k, i)).toFixed(dm);
    return parseFloat(val) + ' ' + sizes[i];
}

export function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

import { enhanceAllSelects } from "./components/customSelect.js";

const loadedComponents = new Set();

export async function loadComponent(id, filePath, targetSelector) {
    if (loadedComponents.has(id)) return true;
    
    try {
        const response = await fetch(filePath);
        if (!response.ok) throw new Error(`Failed to load component ${id}`);
        const html = await response.text();
        const target = document.querySelector(targetSelector);
        if (target) {
            target.insertAdjacentHTML('beforeend', html);
            loadedComponents.add(id);
            try {
                translatePage();
            } catch (e) {}
            try {
                enhanceAllSelects(target);
            } catch (e) {}
            return true;
        }
    } catch (err) {
        console.error(`Error loading component ${id}:`, err);
    }
    return false;
}

export function showConfirmDialog(message) {
    return new Promise((resolve) => {
        // Create modal element
        const modal = document.createElement("div");
        modal.id = "custom-confirm-modal";
        modal.className = "modal active";
        modal.style.zIndex = "2000";
        modal.style.opacity = "1";
        modal.style.pointerEvents = "auto";
        modal.style.display = "flex";
        modal.style.justifyContent = "center";
        modal.style.alignItems = "center";
        modal.style.position = "fixed";
        modal.style.top = "0";
        modal.style.left = "0";
        modal.style.width = "100%";
        modal.style.height = "100%";
        modal.style.background = "rgba(2, 6, 23, 0.88)";
        modal.style.transition = "opacity 0.2s ease";

        // Modal Card
        const card = document.createElement("div");
        card.className = "glass-card modal-card";
        card.style.maxWidth = "420px";
        card.style.width = "90%";
        card.style.padding = "25px";
        card.style.borderRadius = "24px";
        card.style.border = "1px solid var(--border-color)";
        card.style.background = "var(--bg-card)";
        card.style.backdropFilter = "blur(28px) saturate(130%)";
        card.style.boxShadow = "var(--shadow-card)";
        card.style.transform = "translateY(0)";
        card.style.transition = "transform 0.2s ease";

        // Header
        const header = document.createElement("div");
        header.style.display = "flex";
        header.style.justifyContent = "space-between";
        header.style.alignItems = "center";
        header.style.marginBottom = "15px";

        const title = document.createElement("h3");
        title.style.margin = "0";
        title.style.fontSize = "18px";
        title.style.fontWeight = "700";
        title.style.color = "var(--accent-rose)";
        title.style.display = "flex";
        title.style.alignItems = "center";
        title.style.gap = "8px";
        title.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <span>${t("confirm_warning_title", "Внимание")}</span>`;

        const closeBtn = document.createElement("button");
        closeBtn.className = "btn icon-btn";
        closeBtn.style.background = "transparent";
        closeBtn.style.color = "var(--text-secondary)";
        closeBtn.style.padding = "0";
        closeBtn.style.border = "none";
        closeBtn.style.cursor = "pointer";
        closeBtn.style.fontSize = "18px";
        closeBtn.innerHTML = `<i class="fa-solid fa-xmark"></i>`;

        header.appendChild(title);
        header.appendChild(closeBtn);

        // Body
        const body = document.createElement("div");
        body.style.marginBottom = "20px";

        const text = document.createElement("p");
        text.style.margin = "0";
        text.style.fontSize = "14px";
        text.style.color = "var(--text-primary)";
        text.style.lineHeight = "1.5";
        text.innerText = message;

        body.appendChild(text);

        // Footer Buttons
        const footer = document.createElement("div");
        footer.style.display = "flex";
        footer.style.justifyContent = "flex-end";
        footer.style.gap = "10px";

        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "btn secondary-btn";
        cancelBtn.style.padding = "8px 16px";
        cancelBtn.style.fontSize = "13px";
        cancelBtn.style.borderRadius = "8px";
        cancelBtn.innerText = t("confirm_cancel_btn", "Отмена");

        const okBtn = document.createElement("button");
        okBtn.type = "button";
        okBtn.className = "btn danger-btn";
        okBtn.style.padding = "8px 16px";
        okBtn.style.fontSize = "13px";
        okBtn.style.borderRadius = "8px";
        okBtn.style.fontWeight = "600";
        okBtn.innerText = t("confirm_ok_btn", "Подтвердить");

        footer.appendChild(cancelBtn);
        footer.appendChild(okBtn);

        card.appendChild(header);
        card.appendChild(body);
        card.appendChild(footer);
        modal.appendChild(card);
        document.body.appendChild(modal);

        // Close functions
        const cleanup = () => {
            modal.style.opacity = "0";
            card.style.transform = "translateY(15px)";
            setTimeout(() => {
                modal.remove();
            }, 200);
        };

        const onConfirm = () => {
            cleanup();
            resolve(true);
        };

        const onCancel = () => {
            cleanup();
            resolve(false);
        };

        okBtn.addEventListener("click", onConfirm);
        cancelBtn.addEventListener("click", onCancel);
        closeBtn.addEventListener("click", onCancel);
        
        // Close on clicking overlay
        modal.addEventListener("click", (e) => {
            if (e.target === modal) {
                onCancel();
            }
        });
    });
}

