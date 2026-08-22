/**
 * Premium Glassmorphism Custom Select Component for Sentinel Panel
 * Converts standard HTML <select> elements into modern animated glassmorphism dropdowns.
 */

// Single global click listener — registered once for all select instances at module load time.
// Previously it was inside initCustomSelect, causing N listeners for N select elements.
function _closeAllSelects() {
    document.querySelectorAll(".custom-select-container.open").forEach(c => {
        c.classList.remove("open");
    });
    document.querySelectorAll(".custom-select-open-parent").forEach(p => {
        p.classList.remove("custom-select-open-parent");
    });
}
document.addEventListener("click", _closeAllSelects);

export function initCustomSelect(selectElement) {
    if (!selectElement || selectElement.dataset.customSelectInit) return;
    selectElement.dataset.customSelectInit = "true";
    
    // Hide original select element visually while keeping it in DOM for event listeners
    selectElement.style.display = "none";
    
    const container = document.createElement("div");
    container.className = "custom-select-container";
    if (selectElement.classList.contains("inline-select") || selectElement.classList.contains("compact-select") || selectElement.classList.contains("quick-outbound-select")) {
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
        if (options.length === 0) {
            selectedText.textContent = "";
            return;
        }
        let selectedIndex = selectElement.selectedIndex;
        if (selectedIndex < 0 || selectedIndex >= options.length) {
            selectedIndex = 0;
            selectElement.selectedIndex = 0;
        }
        const selectedOpt = options[selectedIndex] || options[0];
        selectedText.textContent = selectedOpt ? (selectedOpt.textContent || selectedOpt.value || "").trim() : "";
        
        options.forEach((opt, idx) => {
            const optDiv = document.createElement("div");
            optDiv.className = `custom-select-option ${idx === selectedIndex ? 'selected' : ''}`;
            
            const labelSpan = document.createElement("span");
            labelSpan.textContent = (opt.textContent || opt.value || "").trim();
            
            const checkI = document.createElement("i");
            checkI.className = "fa-solid fa-check check-icon";
            
            optDiv.appendChild(labelSpan);
            optDiv.appendChild(checkI);
            
            optDiv.addEventListener("click", (e) => {
                e.stopPropagation();
                selectElement.selectedIndex = idx;
                selectElement.value = opt.value;
                selectElement.dispatchEvent(new Event("change", { bubbles: true }));
                updateSelectedUI();
                container.classList.remove("open");
            });
            
            dropdown.appendChild(optDiv);
        });
    }
    
    function updateSelectedUI() {
        const options = Array.from(selectElement.options);
        if (options.length === 0) {
            selectedText.textContent = "";
            return;
        }
        let selectedIndex = selectElement.selectedIndex;
        if (selectedIndex < 0 || selectedIndex >= options.length) {
            selectedIndex = 0;
        }
        const selectedOpt = options[selectedIndex] || options[0];
        selectedText.textContent = selectedOpt ? (selectedOpt.textContent || selectedOpt.value || "").trim() : "";
        
        const optionDivs = dropdown.querySelectorAll(".custom-select-option");
        optionDivs.forEach((div, idx) => {
            if (idx === selectedIndex) {
                div.classList.add("selected");
            } else {
                div.classList.remove("selected");
            }
        });
    }
    
    buildOptions();
    
    trigger.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = container.classList.contains("open");
        _closeAllSelects();
        if (!isOpen) {
            // Smart collision / drop direction calculation based on viewport space
            const triggerRect = trigger.getBoundingClientRect();
            const bottomSpace = window.innerHeight - triggerRect.bottom;
            
            // Only drop upward if overflowing off the bottom of the entire window viewport
            if (bottomSpace < 200 && triggerRect.top > 220) {
                container.classList.add("dropup");
            } else {
                container.classList.remove("dropup");
            }

            container.classList.add("open");
            let p = container.parentElement;
            while (p && !p.classList.contains("modal-card") && !p.classList.contains("content-area") && p !== document.body) {
                p.classList.add("custom-select-open-parent");
                p = p.parentElement;
            }
        }
    });
    
    selectElement.addEventListener("change", () => {
        updateSelectedUI();
    });
    
    // Rebuild options safely if options change dynamically (debounced to avoid freeze loops)
    let rebuildTimeout = null;
    const observer = new MutationObserver(() => {
        if (rebuildTimeout) clearTimeout(rebuildTimeout);
        rebuildTimeout = setTimeout(() => {
            buildOptions();
        }, 30);
    });
    observer.observe(selectElement, { childList: true });
    
    selectElement.parentNode.insertBefore(container, selectElement);
    container.appendChild(trigger);
    container.appendChild(dropdown);
    container.appendChild(selectElement);
}

export function enhanceAllSelects(parent = document) {
    const selects = parent.querySelectorAll("select:not([data-custom-select-init])");
    selects.forEach(sel => initCustomSelect(sel));
}

export function initCustomSelects(parent = document) {
    enhanceAllSelects(parent);
}

