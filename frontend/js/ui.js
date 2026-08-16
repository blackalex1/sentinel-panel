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

export const loadedComponents = new Set();

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

export function showConfirmDialog(options) {
    return new Promise((resolve) => {
        const opts = typeof options === "string" ? { message: options } : (options || {});
        const titleText = opts.title || t("confirm_warning_title", "Внимание");
        const messageText = opts.message || "";
        const type = opts.type || "danger"; // 'danger' | 'warning' | 'info' | 'primary'
        const okText = opts.okText || t("confirm_ok_btn", "Подтвердить");
        const cancelText = opts.cancelText || t("confirm_cancel_btn", "Отмена");

        let iconClass = opts.icon;
        let accentColor = "var(--accent-rose)";
        let glowColor = "rgba(244, 63, 94, 0.25)";
        let badgeBg = "rgba(244, 63, 94, 0.15)";
        let btnBg = "linear-gradient(135deg, #f43f5e 0%, #e11d48 100%)";
        let btnColor = "#ffffff";
        let btnShadow = "0 4px 18px rgba(244, 63, 94, 0.4)";

        if (type === "warning") {
            iconClass = iconClass || "fa-solid fa-triangle-exclamation";
            accentColor = "var(--accent-orange, #f59e0b)";
            glowColor = "rgba(245, 158, 11, 0.25)";
            badgeBg = "rgba(245, 158, 11, 0.15)";
            btnBg = "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)";
            btnColor = "#0f172a";
            btnShadow = "0 4px 18px rgba(245, 158, 11, 0.35)";
        } else if (type === "info" || type === "cyan") {
            iconClass = iconClass || "fa-solid fa-circle-info";
            accentColor = "var(--accent-cyan, #06b6d4)";
            glowColor = "rgba(6, 182, 212, 0.25)";
            badgeBg = "rgba(6, 182, 212, 0.15)";
            btnBg = "linear-gradient(135deg, #06b6d4 0%, #0284c7 100%)";
            btnColor = "#ffffff";
            btnShadow = "0 4px 18px rgba(6, 182, 212, 0.35)";
        } else if (type === "primary" || type === "purple") {
            iconClass = iconClass || "fa-solid fa-shield-halved";
            accentColor = "var(--primary, #8b5cf6)";
            glowColor = "rgba(139, 92, 246, 0.25)";
            badgeBg = "rgba(139, 92, 246, 0.15)";
            btnBg = "var(--primary-gradient, linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%))";
            btnColor = "#ffffff";
            btnShadow = "0 4px 18px rgba(139, 92, 246, 0.35)";
        } else {
            iconClass = iconClass || "fa-solid fa-triangle-exclamation";
        }

        // Overlay Modal Container
        const modal = document.createElement("div");
        modal.id = "custom-confirm-modal";
        modal.className = "modal custom-confirm-overlay";
        modal.style.position = "fixed";
        modal.style.top = "0";
        modal.style.left = "0";
        modal.style.width = "100vw";
        modal.style.height = "100vh";
        modal.style.zIndex = "9999";
        modal.style.display = "flex";
        modal.style.justifyContent = "center";
        modal.style.alignItems = "center";
        modal.style.padding = "20px";
        modal.style.background = "rgba(4, 7, 18, 0.82)";
        modal.style.backdropFilter = "blur(20px) saturate(180%)";
        modal.style.webkitBackdropFilter = "blur(20px) saturate(180%)";
        modal.style.opacity = "0";
        modal.style.transition = "opacity 0.25s cubic-bezier(0.16, 1, 0.3, 1)";

        // Card
        const card = document.createElement("div");
        card.className = "glass-card modal-card";
        card.style.maxWidth = "460px";
        card.style.width = "100%";
        card.style.padding = "26px 28px";
        card.style.borderRadius = "20px";
        card.style.border = "1px solid rgba(255, 255, 255, 0.1)";
        card.style.background = "rgba(13, 18, 36, 0.94)";
        card.style.boxShadow = `0 25px 60px -10px rgba(0, 0, 0, 0.85), 0 0 35px ${glowColor}`;
        card.style.transform = "scale(0.92) translateY(12px)";
        card.style.transition = "transform 0.25s cubic-bezier(0.16, 1, 0.3, 1)";

        // Header
        const header = document.createElement("div");
        header.style.display = "flex";
        header.style.alignItems = "center";
        header.style.justifyContent = "space-between";
        header.style.marginBottom = "18px";

        const titleWrapper = document.createElement("div");
        titleWrapper.style.display = "flex";
        titleWrapper.style.alignItems = "center";
        titleWrapper.style.gap = "14px";

        const badge = document.createElement("div");
        badge.style.width = "40px";
        badge.style.height = "40px";
        badge.style.borderRadius = "12px";
        badge.style.background = badgeBg;
        badge.style.border = `1px solid ${accentColor}40`;
        badge.style.display = "flex";
        badge.style.alignItems = "center";
        badge.style.justifyContent = "center";
        badge.style.color = accentColor;
        badge.style.fontSize = "17px";
        badge.style.flexShrink = "0";
        badge.innerHTML = `<i class="${iconClass}"></i>`;

        const title = document.createElement("h3");
        title.style.margin = "0";
        title.style.fontSize = "17px";
        title.style.fontWeight = "700";
        title.style.letterSpacing = "-0.01em";
        title.style.color = "var(--text-primary, #f8fafc)";
        title.innerText = titleText;

        titleWrapper.appendChild(badge);
        titleWrapper.appendChild(title);

        const closeBtn = document.createElement("button");
        closeBtn.className = "btn icon-btn";
        closeBtn.style.background = "rgba(255, 255, 255, 0.04)";
        closeBtn.style.color = "var(--text-muted, #64748b)";
        closeBtn.style.border = "1px solid rgba(255, 255, 255, 0.05)";
        closeBtn.style.borderRadius = "10px";
        closeBtn.style.width = "32px";
        closeBtn.style.height = "32px";
        closeBtn.style.padding = "0";
        closeBtn.style.display = "flex";
        closeBtn.style.alignItems = "center";
        closeBtn.style.justifyContent = "center";
        closeBtn.style.cursor = "pointer";
        closeBtn.style.fontSize = "14px";
        closeBtn.style.transition = "all 0.15s ease";
        closeBtn.innerHTML = `<i class="fa-solid fa-xmark"></i>`;
        closeBtn.onmouseenter = () => { closeBtn.style.color = "#fff"; closeBtn.style.background = "rgba(255, 255, 255, 0.1)"; };
        closeBtn.onmouseleave = () => { closeBtn.style.color = "var(--text-muted, #64748b)"; closeBtn.style.background = "rgba(255, 255, 255, 0.04)"; };

        header.appendChild(titleWrapper);
        header.appendChild(closeBtn);

        // Body
        const body = document.createElement("div");
        body.style.marginBottom = "24px";
        body.style.paddingLeft = "54px";

        const text = document.createElement("p");
        text.style.margin = "0";
        text.style.fontSize = "14px";
        text.style.color = "var(--text-secondary, #cbd5e1)";
        text.style.lineHeight = "1.6";
        text.style.whiteSpace = "pre-line";
        text.innerText = messageText;

        body.appendChild(text);

        // Footer Buttons
        const footer = document.createElement("div");
        footer.style.display = "flex";
        footer.style.justifyContent = "flex-end";
        footer.style.gap = "12px";

        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "btn secondary-btn";
        cancelBtn.style.background = "rgba(255, 255, 255, 0.05)";
        cancelBtn.style.border = "1px solid rgba(255, 255, 255, 0.1)";
        cancelBtn.style.color = "var(--text-primary, #f8fafc)";
        cancelBtn.style.padding = "9px 18px";
        cancelBtn.style.fontSize = "13.5px";
        cancelBtn.style.fontWeight = "600";
        cancelBtn.style.borderRadius = "10px";
        cancelBtn.style.cursor = "pointer";
        cancelBtn.style.transition = "all 0.15s ease";
        cancelBtn.innerText = cancelText;
        cancelBtn.onmouseenter = () => { cancelBtn.style.background = "rgba(255, 255, 255, 0.1)"; };
        cancelBtn.onmouseleave = () => { cancelBtn.style.background = "rgba(255, 255, 255, 0.05)"; };

        const okBtn = document.createElement("button");
        okBtn.type = "button";
        okBtn.className = "btn";
        okBtn.style.background = btnBg;
        okBtn.style.color = btnColor;
        okBtn.style.border = "none";
        okBtn.style.boxShadow = btnShadow;
        okBtn.style.padding = "9px 22px";
        okBtn.style.fontSize = "13.5px";
        okBtn.style.fontWeight = "600";
        okBtn.style.borderRadius = "10px";
        okBtn.style.cursor = "pointer";
        okBtn.style.transition = "all 0.15s ease";
        okBtn.innerText = okText;
        okBtn.onmouseenter = () => { okBtn.style.transform = "translateY(-1px)"; okBtn.style.filter = "brightness(1.1)"; };
        okBtn.onmouseleave = () => { okBtn.style.transform = "translateY(0)"; okBtn.style.filter = "brightness(1.0)"; };

        footer.appendChild(cancelBtn);
        footer.appendChild(okBtn);

        card.appendChild(header);
        card.appendChild(body);
        card.appendChild(footer);
        modal.appendChild(card);
        document.body.appendChild(modal);

        // Animate in
        requestAnimationFrame(() => {
            modal.style.opacity = "1";
            card.style.transform = "scale(1) translateY(0)";
        });

        // Close functions
        let isClosed = false;
        const cleanup = (confirmed) => {
            if (isClosed) return;
            isClosed = true;
            document.removeEventListener("keydown", keyHandler);
            modal.style.opacity = "0";
            card.style.transform = "scale(0.94) translateY(8px)";
            setTimeout(() => {
                modal.remove();
            }, 200);
            resolve(confirmed);
        };

        const keyHandler = (e) => {
            if (e.key === "Escape") {
                e.preventDefault();
                cleanup(false);
            } else if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                cleanup(true);
            }
        };

        document.addEventListener("keydown", keyHandler);
        okBtn.addEventListener("click", () => cleanup(true));
        cancelBtn.addEventListener("click", () => cleanup(false));
        closeBtn.addEventListener("click", () => cleanup(false));

        // Click outside
        modal.addEventListener("click", (e) => {
            if (e.target === modal) {
                cleanup(false);
            }
        });

        // Focus confirm button
        setTimeout(() => okBtn.focus(), 50);
    });
}

export function showAlertModal(options) {
    const opts = typeof options === "string" ? { message: options } : (options || {});
    return showConfirmDialog({
        title: opts.title || t("info_title", "Информация"),
        message: opts.message || "",
        type: opts.type || "info",
        okText: opts.okText || t("confirm_ok_btn", "Понятно"),
        cancelText: null
    });
}

