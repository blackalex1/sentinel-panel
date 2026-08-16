/**
 * Sentinel Schema-Driven UI Engine
 * Dynamically renders tabs, field groups, inputs, generators, and handles conditional visibility.
 */
import { t } from "../../i18n.js";
import { initCustomSelects } from "../../components/customSelect.js";

export function getByPath(obj, path, defaultValue = undefined) {
    if (!obj || !path) return defaultValue;
    const parts = path.split(".");
    let current = obj;
    for (const part of parts) {
        if (current === undefined || current === null) return defaultValue;
        current = current[part];
    }
    return current !== undefined ? current : defaultValue;
}

export function setByPath(obj, path, value) {
    if (!obj || !path) return;
    const parts = path.split(".");
    let current = obj;
    for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        if (!current[part] || typeof current[part] !== "object") {
            current[part] = {};
        }
        current = current[part];
    }
    current[parts[parts.length - 1]] = value;
}

export function evaluateShowIfCondition(showIf, formValues) {
    if (!showIf || typeof showIf !== "object") return true;
    for (const [path, expectedVal] of Object.entries(showIf)) {
        const actualVal = getByPath(formValues, path);
        if (Array.isArray(expectedVal)) {
            if (!expectedVal.includes(actualVal)) return false;
        } else {
            if (actualVal !== expectedVal) return false;
        }
    }
    return true;
}

export function generateRandomPort() {
    return Math.floor(Math.random() * (65535 - 10000 + 1)) + 10000;
}

export function generateRandomPassword(length = 16) {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    let res = "";
    for (let i = 0; i < length; i++) {
        res += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return res;
}

/**
 * Dynamically renders tab navigation buttons based on schema tab definitions
 */
export function renderDynamicModalTabs(tabsContainer, tabDefinitions, currentActiveTab, onTabClick) {
    if (!tabsContainer || !Array.isArray(tabDefinitions)) return;

    tabsContainer.innerHTML = "";
    tabDefinitions.forEach((tab, index) => {
        const isActive = (tab.id === currentActiveTab) || (!currentActiveTab && index === 0);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `btn secondary-btn modal-tab-btn ${isActive ? "active" : ""}`;
        btn.setAttribute("data-tab", tab.id);
        btn.id = `ib-tab-${tab.id}`;

        const iconHtml = tab.icon ? `<i class="fa-solid ${tab.icon}" style="margin-right: 6px;"></i>` : "";
        btn.innerHTML = `${iconHtml}<span>${tab.title || tab.id}</span>`;

        btn.addEventListener("click", () => {
            if (typeof onTabClick === "function") {
                onTabClick(tab.id);
            }
        });

        tabsContainer.appendChild(btn);
    });
}

/**
 * Updates tab button states
 */
export function switchActiveSchemaTab(tabsContainer, activeTabId) {
    if (!tabsContainer) return;
    const tabButtons = tabsContainer.querySelectorAll(".modal-tab-btn");
    tabButtons.forEach(btn => {
        if (btn.getAttribute("data-tab") === activeTabId) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    const panels = document.querySelectorAll("#inbound-form-tabs-container .tab-panel, #outbound-schema-container .tab-panel");
    panels.forEach(panel => {
        if (panel.id === `tab-panel-${activeTabId}` || panel.id === `ob-tab-panel-${activeTabId}`) {
            panel.classList.add("active-panel");
            panel.style.display = "block";
        } else {
            panel.classList.remove("active-panel");
            panel.style.display = "none";
        }
    });
}

/**
 * Dynamically renders the entire Outbound form based on sentinel-core Outbound tabDefinitions
 */
export function renderDynamicOutboundForm(containerEl, tabsContainerEl, tabDefinitions, currentValues = {}, onFieldChange = null) {
    if (!containerEl || !Array.isArray(tabDefinitions)) return;

    containerEl.innerHTML = "";
    if (tabsContainerEl) {
        tabsContainerEl.innerHTML = "";
    }

    let activeTabId = tabDefinitions.length > 0 ? tabDefinitions[0].id : "basic";

    // 1. Render Tab Buttons
    if (tabsContainerEl) {
        tabDefinitions.forEach((tab, idx) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = `btn secondary-btn modal-tab-btn ${idx === 0 ? "active" : ""}`;
            btn.setAttribute("data-tab", tab.id);
            btn.id = `ob-tab-${tab.id}`;
            const iconHtml = tab.icon ? `<i class="fa-solid ${tab.icon}" style="margin-right: 6px;"></i>` : "";
            btn.innerHTML = `${iconHtml}<span>${tab.title || tab.id}</span>`;

            btn.addEventListener("click", () => {
                activeTabId = tab.id;
                tabsContainerEl.querySelectorAll(".modal-tab-btn").forEach(b => {
                    b.classList.toggle("active", b.getAttribute("data-tab") === tab.id);
                });
                containerEl.querySelectorAll(".tab-panel").forEach(p => {
                    const isCurrent = (p.id === `ob-tab-panel-${tab.id}`);
                    p.classList.toggle("active-panel", isCurrent);
                    p.style.display = isCurrent ? "block" : "none";
                });
            });
            tabsContainerEl.appendChild(btn);
        });
    }

    // Function to re-evaluate all showIf conditions across the form
    function refreshVisibility() {
        containerEl.querySelectorAll("[data-show-if]").forEach(el => {
            try {
                const condition = JSON.parse(el.getAttribute("data-show-if"));
                const isVisible = evaluateShowIfCondition(condition, currentValues);
                el.style.display = isVisible ? "" : "none";
            } catch (e) {
                console.warn("Invalid showIf JSON:", e);
            }
        });
    }

    // 2. Render Tab Panels & Field Groups
    tabDefinitions.forEach((tab, tabIdx) => {
        const panel = document.createElement("div");
        panel.className = `tab-panel ${tabIdx === 0 ? "active-panel" : ""}`;
        panel.id = `ob-tab-panel-${tab.id}`;
        panel.style.display = (tabIdx === 0) ? "block" : "none";

        if (Array.isArray(tab.groups)) {
            tab.groups.forEach(group => {
                const groupCard = document.createElement("div");
                groupCard.className = "settings-group-card";
                groupCard.style.cssText = "background: rgba(15, 23, 42, 0.45); border: 1px solid var(--border-color); border-radius: 12px; padding: 18px 22px; margin-bottom: 18px;";

                if (group.title) {
                    const headerDiv = document.createElement("div");
                    headerDiv.style.marginBottom = "14px";
                    headerDiv.innerHTML = `
                        <h4 style="margin: 0 0 4px 0; font-size: 14.5px; font-weight: 600; color: var(--text-primary);">${group.title}</h4>
                        ${group.description ? `<p style="margin: 0; font-size: 12px; color: var(--text-secondary);">${group.description}</p>` : ""}
                    `;
                    groupCard.appendChild(headerDiv);
                }

                if (group.showIf) {
                    groupCard.setAttribute("data-show-if", JSON.stringify(group.showIf));
                }

                // Render fields inside group grid
                const row = document.createElement("div");
                row.className = "input-row";
                row.style.cssText = "display: flex; flex-wrap: wrap; gap: 14px;";

                if (Array.isArray(group.fields)) {
                    group.fields.forEach(field => {
                        const fieldWrap = document.createElement("div");
                        fieldWrap.className = `input-group ${field.gridColumn || "col-12"}`;
                        
                        // Map grid columns to flex basis
                        let flexBasis = "100%";
                        if (field.gridColumn === "col-6") flexBasis = "calc(50% - 7px)";
                        else if (field.gridColumn === "col-4") flexBasis = "calc(33.33% - 10px)";
                        else if (field.gridColumn === "col-8") flexBasis = "calc(66.66% - 10px)";
                        else if (field.gridColumn === "col-3") flexBasis = "calc(25% - 11px)";
                        fieldWrap.style.cssText = `flex: 1 1 ${flexBasis}; min-width: 220px; display: flex; flex-direction: column; gap: 6px;`;

                        if (field.showIf) {
                            fieldWrap.setAttribute("data-show-if", JSON.stringify(field.showIf));
                        }

                        // Label
                        if (field.type !== "checkbox") {
                            const label = document.createElement("label");
                            label.htmlFor = field.id;
                            label.style.cssText = "font-size: 12.5px; font-weight: 500; color: var(--text-secondary);";
                            label.textContent = field.label;
                            fieldWrap.appendChild(label);
                        }

                        // Value lookup
                        const val = getByPath(currentValues, field.targetField, (field.default !== undefined ? field.default : ""));

                        if (field.type === "select") {
                            const sel = document.createElement("select");
                            sel.id = field.id;
                            sel.className = "glass-select";
                            sel.setAttribute("data-target-field", field.targetField);
                            if (Array.isArray(field.options)) {
                                field.options.forEach(opt => {
                                    const optEl = document.createElement("option");
                                    optEl.value = opt.value;
                                    optEl.textContent = opt.label;
                                    if (String(val) === String(opt.value)) {
                                        optEl.selected = true;
                                    }
                                    sel.appendChild(optEl);
                                });
                            }
                            sel.addEventListener("change", (e) => {
                                setByPath(currentValues, field.targetField, e.target.value);
                                refreshVisibility();
                                if (typeof onFieldChange === "function") onFieldChange(currentValues);
                            });
                            fieldWrap.appendChild(sel);
                        } else if (field.type === "checkbox") {
                            const checkLabel = document.createElement("label");
                            checkLabel.style.cssText = "display: flex; align-items: center; justify-content: space-between; cursor: pointer; user-select: none; padding: 8px 0;";
                            checkLabel.innerHTML = `
                                <span style="font-size: 13px; font-weight: 500; color: var(--text-primary);">${field.label}</span>
                                <span class="switch-toggle">
                                    <input type="checkbox" id="${field.id}" data-target-field="${field.targetField}" ${Boolean(val) ? "checked" : ""}/>
                                    <span class="switch-slider"></span>
                                </span>
                            `;
                            const checkInput = checkLabel.querySelector("input");
                            checkInput.addEventListener("change", (e) => {
                                setByPath(currentValues, field.targetField, e.target.checked);
                                refreshVisibility();
                                if (typeof onFieldChange === "function") onFieldChange(currentValues);
                            });
                            fieldWrap.appendChild(checkLabel);
                        } else {
                            // Text, Number, Password inputs
                            const isNumeric = (field.type === "number" && field.targetField !== "port" && field.id !== "ob-port" && !String(val).includes("-") && !String(val).includes(",") && !String(val).includes(":"));
                            const input = document.createElement("input");
                            input.id = field.id;
                            input.type = isNumeric ? "number" : ((field.type === "password") ? "password" : "text");
                            input.className = "glass-input";
                            input.setAttribute("data-target-field", field.targetField);
                            input.autocomplete = (field.type === "password") ? "new-password" : "off";
                            input.placeholder = field.placeholder || "";
                            input.value = (val !== undefined && val !== null) ? val : "";

                            input.addEventListener("input", (e) => {
                                const raw = e.target.value;
                                let inputVal = raw;
                                if (isNumeric && raw !== "") {
                                    inputVal = Number(raw);
                                }
                                setByPath(currentValues, field.targetField, inputVal);
                                refreshVisibility();
                                if (typeof onFieldChange === "function") onFieldChange(currentValues);
                            });

                            fieldWrap.appendChild(input);
                        }

                        // Help text
                        if (field.helpText) {
                            const help = document.createElement("span");
                            help.style.cssText = "font-size: 11px; color: var(--text-secondary); opacity: 0.8;";
                            help.textContent = field.helpText;
                            fieldWrap.appendChild(help);
                        }

                        row.appendChild(fieldWrap);
                    });
                }

                groupCard.appendChild(row);
                panel.appendChild(groupCard);
            });
        }

        containerEl.appendChild(panel);
    });

    // Initial showIf evaluation
    refreshVisibility();

    // Initialize custom select on generated dropdowns
    import("../../components/customSelect.js").then(mod => {
        if (mod && mod.enhanceAllSelects) {
            mod.enhanceAllSelects(containerEl);
        }
    });
}

