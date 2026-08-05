import { showToast } from "../../../ui.js";
import { t } from "../../../i18n.js";

export function initEditorModal() {
    window.openJsonEditModal = function(title, currentObj, onSave) {
        const modal = document.getElementById("json-edit-modal");
        if (!modal) return;
        
        const titleEl = document.getElementById("json-modal-title");
        const textareaEl = document.getElementById("json-modal-textarea");
        const labelEl = document.getElementById("json-modal-label");
        
        if (titleEl) titleEl.innerText = title;
        if (labelEl) labelEl.innerText = t("config_json_modal_label", "Введите корректный JSON-код:");
        if (textareaEl) textareaEl.value = JSON.stringify(currentObj, null, 2);
        
        modal.classList.add("active");
        
        const saveBtn = document.getElementById("json-modal-save-btn");
        const newSaveBtn = saveBtn.cloneNode(true);
        saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
        
        const cancelBtn = document.getElementById("json-modal-cancel-btn");
        const newCancelBtn = cancelBtn.cloneNode(true);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);
        
        const closeBtn = document.getElementById("json-modal-close-btn");
        const newCloseBtn = closeBtn.cloneNode(true);
        closeBtn.parentNode.replaceChild(newCloseBtn, closeBtn);
        
        const closeModal = () => modal.classList.remove("active");
        
        newCancelBtn.addEventListener("click", closeModal);
        newCloseBtn.addEventListener("click", closeModal);
        
        newSaveBtn.addEventListener("click", async () => {
            const textVal = textareaEl.value;
            let parsed = null;
            try {
                parsed = JSON.parse(textVal);
            } catch (err) {
                showToast(t("config_invalid_json", "Некорректный формат JSON"), "error");
                return;
            }
            
            newSaveBtn.disabled = true;
            try {
                await onSave(parsed);
                closeModal();
            } catch (err) {
                showToast(err.message || t("config_save_error", "Ошибка при сохранении"), "error");
            } finally {
                newSaveBtn.disabled = false;
            }
        });
    };
}
