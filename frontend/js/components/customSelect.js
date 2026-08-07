/**
 * Premium Glassmorphism Custom Select Component for Spectre Panel
 * Converts standard HTML <select> elements into modern animated glassmorphism dropdowns.
 */

export function initCustomSelect(selectElement) {
    if (!selectElement || selectElement.dataset.customSelectInit) return;
    selectElement.dataset.customSelectInit = "true";
    
    // Hide original select element visually while keeping it in DOM for event listeners
    selectElement.style.display = "none";
    
    const container = document.createElement("div");
    container.className = "custom-select-container";
    if (selectElement.classList.contains("inline-select") || selectElement.classList.contains("compact-select")) {
        container.classList.add("inline-select");
    }
    
    const trigger = document.createElement("div");
    trigger.className = "custom-select-trigger";
    
    const selectedText = document.createElement("span");
    const arrow = document.createElement("i");
    arrow.className = "fa-solid fa-chevron-down custom-select-arrow";
    
    trigger.appendChild(selectedText);
    trigger.appendChild(arrow);
    
    const dropdown = document.createElement("div");
    dropdown.className = "custom-select-dropdown";
    
    function buildOptions() {
        dropdown.innerHTML = "";
        const options = Array.from(selectElement.options);
        const selectedOpt = selectElement.options[selectElement.selectedIndex] || options[0];
        selectedText.textContent = selectedOpt ? selectedOpt.textContent : "";
        
        options.forEach((opt, idx) => {
            const optDiv = document.createElement("div");
            optDiv.className = `custom-select-option ${idx === selectElement.selectedIndex ? 'selected' : ''}`;
            
            const labelSpan = document.createElement("span");
            labelSpan.textContent = opt.textContent;
            
            const checkI = document.createElement("i");
            checkI.className = "fa-solid fa-check check-icon";
            
            optDiv.appendChild(labelSpan);
            optDiv.appendChild(checkI);
            
            optDiv.addEventListener("click", (e) => {
                e.stopPropagation();
                selectElement.selectedIndex = idx;
                selectElement.dispatchEvent(new Event("change", { bubbles: true }));
                updateSelectedUI();
                container.classList.remove("open");
            });
            
            dropdown.appendChild(optDiv);
        });
    }
    
    function updateSelectedUI() {
        const options = Array.from(selectElement.options);
        const selectedOpt = selectElement.options[selectElement.selectedIndex] || options[0];
        selectedText.textContent = selectedOpt ? selectedOpt.textContent : "";
        
        const optionDivs = dropdown.querySelectorAll(".custom-select-option");
        optionDivs.forEach((div, idx) => {
            if (idx === selectElement.selectedIndex) {
                div.classList.add("selected");
            } else {
                div.classList.remove("selected");
            }
        });
    }
    
    buildOptions();
    
    function closeAll() {
        document.querySelectorAll(".custom-select-container.open").forEach(c => {
            c.classList.remove("open");
            const parentCard = c.closest(".settings-card, .glass-card, .input-group, .modal-body, .form-group, .settings-section-panel");
            if (parentCard) parentCard.classList.remove("custom-select-open-parent");
        });
    }
    
    trigger.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = container.classList.contains("open");
        closeAll();
        if (!isOpen) {
            container.classList.add("open");
            const parentCard = container.closest(".settings-card, .glass-card, .input-group, .modal-body, .form-group, .settings-section-panel");
            if (parentCard) parentCard.classList.add("custom-select-open-parent");
        }
    });
    
    document.addEventListener("click", () => {
        closeAll();
    });
    
    selectElement.addEventListener("change", () => {
        updateSelectedUI();
    });
    
    // Rebuild options if options change dynamically (e.g. i18n translation updates)
    const observer = new MutationObserver(() => {
        buildOptions();
    });
    observer.observe(selectElement, { childList: true, subtree: true, characterData: true });
    
    selectElement.parentNode.insertBefore(container, selectElement);
    container.appendChild(trigger);
    container.appendChild(dropdown);
    container.appendChild(selectElement);
}

export function enhanceAllSelects(parent = document) {
    const selects = parent.querySelectorAll("select:not([data-custom-select-init])");
    selects.forEach(sel => initCustomSelect(sel));
}
