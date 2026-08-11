import { apiFetch } from "../../api.js";
import { showToast } from "../../ui.js";
import { t, translatePage } from "../../i18n.js";
import { initCustomSelect } from "../../components/customSelect.js";
import { initEditorModal } from "../xray/config_ui/editor_modal.js";

initEditorModal();

function getLogLevelStyle(level) {
    const l = (level || "").toLowerCase();
    let bg, color, border, arrowColor;
    if (l === "trace" || l === "debug") {
        bg = "rgba(0, 240, 255, 0.15)";
        color = "#00f0ff";
        border = "1px solid rgba(0, 240, 255, 0.3)";
        arrowColor = "%2300f0ff";
    } else if (l === "info") {
        bg = "rgba(46, 213, 115, 0.15)";
        color = "#2ed573";
        border = "1px solid rgba(46, 213, 115, 0.3)";
        arrowColor = "%232ed573";
    } else if (l === "warning" || l === "warn") {
        bg = "rgba(255, 165, 2, 0.15)";
        color = "#ffa502";
        border = "1px solid rgba(255, 165, 2, 0.3)";
        arrowColor = "%23ffa502";
    } else if (l === "error" || l === "fatal" || l === "panic") {
        bg = "rgba(255, 71, 87, 0.15)";
        color = "#ff4757";
        border = "1px solid rgba(255, 71, 87, 0.3)";
        arrowColor = "%23ff4757";
    } else {
        bg = "rgba(255, 255, 255, 0.08)";
        color = "var(--text-secondary, #94a3b8)";
        border = "1px solid rgba(255, 255, 255, 0.15)";
        arrowColor = "%2394a3b8";
    }
    const svgArrow = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5' viewBox='0 0 8 5'%3E%3Cpath fill='${arrowColor}' d='M0 0l4 5 4-5z'/%3E%3C/svg%3E")`;
    return {
        bg: `${bg} ${svgArrow} no-repeat right 8px center / 8px 5px`,
        color,
        border
    };
}

export async function loadSingboxConfig() {
    const res = await apiFetch("/api/singbox/config");
    if (!res || !res.success) return;

    window.singboxConfig = res.config;
    const config = window.singboxConfig;

    // Update config mode badge (Auto / Custom)
    const modeBadge = document.getElementById("singbox-config-mode-badge");
    if (modeBadge) {
        const isCustom = res.use_custom === true;
        if (isCustom) {
            modeBadge.className = "tag-badge tag-badge-blocked";
            modeBadge.setAttribute("data-i18n", "config_mode_custom");
            modeBadge.innerText = t("config_mode_custom", "КАСТОМ");
        } else {
            modeBadge.className = "tag-badge tag-badge-direct";
            modeBadge.setAttribute("data-i18n", "config_mode_auto");
            modeBadge.innerText = t("config_mode_auto", "АВТО");
        }
    }

    const rawPre = document.getElementById("singbox-config-raw-pre");
    if (rawPre) {
        rawPre.value = JSON.stringify(config, null, 2);
    }

    renderSingboxConfig(config);
}

export function renderSingboxConfig(config) {
    const parsedContainer = document.getElementById("singbox-config-parsed-container");
    if (!parsedContainer) return;

    if (!config) {
        parsedContainer.innerHTML = `<div style="text-align: center; padding: 40px 20px; color: var(--text-muted);">` + t("singbox_no_config", "Конфигурация Sing-box пуста или не загружена") + `</div>`;
        return;
    }

    let html = "";

    // -- 1. LOGGING & GLOBAL SETTINGS --
    config.log = config.log || {};
    const currLevel = config.log.level || "debug";
    html += `<div style="margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: var(--accent-orange); display: flex; align-items: center; gap: 8px;">
                <i class="fa-solid fa-file-invoice"></i> <span data-i18n="singbox_config_log_title">Системные настройки и логирование</span>
            </h4>
            <button class="btn secondary-btn edit-json-btn" data-type="singbox-log" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
        </div>
        <div class="glass-card" style="padding: 16px; border-radius: 12px; background: rgba(255,255,255,0.015); border: 1px solid var(--border-color);">
            <div style="font-size: 13px; line-height: 1.6; color: var(--text-secondary);">
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 6px;">
                    <span style="font-weight: 500;">LogLevel:</span>
                    <select id="singbox-loglevel-select" class="inline-select">
                        <option value="trace" ${currLevel === 'trace' ? 'selected' : ''}>trace</option>
                        <option value="debug" ${currLevel === 'debug' ? 'selected' : ''}>debug</option>
                        <option value="info" ${currLevel === 'info' ? 'selected' : ''}>info</option>
                        <option value="warn" ${currLevel === 'warn' ? 'selected' : ''}>warn</option>
                        <option value="error" ${currLevel === 'error' ? 'selected' : ''}>error</option>
                        <option value="fatal" ${currLevel === 'fatal' ? 'selected' : ''}>fatal</option>
                        <option value="panic" ${currLevel === 'panic' ? 'selected' : ''}>panic</option>
                    </select>
                </div>
                <div style="margin-top: 5px;">DNS Servers: <code style="font-size: 11px; color: var(--text-primary);">${(config.dns && config.dns.servers ? config.dns.servers.map(s => typeof s === 'string' ? s : `${s.tag || ''}: ${s.server || s.address || ''}`).join(", ") : "—")}</code></div>
            </div>
        </div>
    </div>`;

    // -- 2. INBOUNDS --
    html += `<div style="margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px;">
            <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: var(--accent-blue); display: flex; align-items: center; gap: 8px;">
                <i class="fa-solid fa-arrow-right-to-bracket"></i> <span data-i18n="singbox_config_inbounds">Входящие подключения (Inbounds)</span>
            </h4>
            <button class="btn secondary-btn edit-json-btn" data-type="singbox-inbounds" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
        </div>`;

    if (config.inbounds && config.inbounds.length > 0) {
        config.inbounds.forEach((ib, idx) => {
            let securityType = (ib.tls && ib.tls.enabled) ? "TLS" : "None";
            let securityBadgeClass = (ib.tls && ib.tls.enabled) ? "tag-badge-proxy" : "tag-badge-direct";

            let streamDesc = `Listen: <code>${ib.listen || "::"}:${ib.listen_port || ib.port || "—"}</code>`;
            if (ib.tls && ib.tls.enabled) {
                streamDesc += ` | TLS ServerName: <code style="color: #18dcff;">${ib.tls.server_name || "Enabled"}</code>`;
            }

            let usersRows = "";
            if (ib.users && ib.users.length > 0) {
                usersRows = `<div class="table-container" style="margin-top: 10px;">
                    <table class="glass-table" style="font-size: 12px; background: rgba(0,0,0,0.15); border-radius: 8px;">
                        <thead>
                            <tr>
                                <th style="padding: 8px 12px;">Name / Email</th>
                                <th style="padding: 8px 12px;">UUID / Password</th>
                                <th style="padding: 8px 12px;">Flow</th>
                            </tr>
                        </thead>
                        <tbody>`;
                ib.users.forEach(u => {
                    usersRows += `<tr>
                        <td style="padding: 8px 12px;"><strong>${u.name || "—"}</strong></td>
                        <td style="padding: 8px 12px; font-family: monospace; user-select: text;">${u.uuid || u.password || "—"}</td>
                        <td style="padding: 8px 12px;"><code>${u.flow || "—"}</code></td>
                    </tr>`;
                });
                usersRows += `</tbody></table></div>`;
            } else {
                usersRows = `<div style="font-size: 12px; color: var(--text-muted); margin-top: 8px; font-style: italic;">Нет клиентов</div>`;
            }

            html += `<div class="glass-card" style="padding: 16px; margin-bottom: 12px; border-radius: 12px; background: rgba(255,255,255,0.015); border: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 10px;">
                    <div>
                        <span class="tag-badge tag-badge-warp" style="text-transform: uppercase; font-size: 11px;">${ib.type || "inbound"}</span>
                        <strong style="font-size: 14px; color: var(--text-primary); margin-left: 8px;">:${ib.listen_port || ib.port || "—"}</strong>
                        <span style="font-size: 12px; color: var(--text-muted); font-family: monospace; margin-left: 10px;">(Tag: ${ib.tag || "—"})</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <button class="btn secondary-btn edit-json-btn" data-type="singbox-inbound" data-index="${idx}" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
                        <span class="tag-badge ${securityBadgeClass}">${securityType}</span>
                    </div>
                </div>
                <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
                    ${streamDesc}
                </div>
                ${usersRows}
            </div>`;
        });
    } else {
        html += `<div class="glass-card" style="padding: 20px; text-align: center; color: var(--text-muted);" data-i18n="config_no_inbounds">Входящие подключения отсутствуют</div>`;
    }
    html += `</div>`;

    // -- 3. OUTBOUNDS --
    html += `<div style="margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: var(--accent-green); display: flex; align-items: center; gap: 8px;">
                <i class="fa-solid fa-arrow-right-from-bracket"></i> <span data-i18n="singbox_config_outbounds">Исходящие подключения (Outbounds)</span>
            </h4>
            <button class="btn secondary-btn edit-json-btn" data-type="singbox-outbounds" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
        </div>`;

    if (config.outbounds && config.outbounds.length > 0) {
        config.outbounds.forEach((ob) => {
            let portStr = ob.server_port || (ob.server_ports ? ob.server_ports.join(", ") : "—");
            let typeBadgeClass = (ob.type === "direct") ? "tag-badge-direct" : (ob.type === "block") ? "tag-badge-warp" : "tag-badge-proxy";
            let serverDesc = ob.server ? `Server: <code>${ob.server}:${portStr}</code>` : "";
            let tlsDesc = (ob.tls && ob.tls.enabled) ? ` | TLS SNI: <code style="color: #18dcff;">${ob.tls.server_name || "Enabled"}</code> (Insecure: ${ob.tls.insecure})` : "";

            html += `<div class="glass-card" style="padding: 14px 16px; margin-bottom: 10px; border-radius: 10px; background: rgba(255,255,255,0.015); border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <span class="tag-badge ${typeBadgeClass}" style="text-transform: uppercase; font-size: 11px;">${ob.type || "outbound"}</span>
                    <strong style="font-size: 13px; color: var(--text-primary); margin-left: 8px;">${ob.tag || "—"}</strong>
                    <span style="font-size: 12px; color: var(--text-secondary); margin-left: 12px;">${serverDesc}${tlsDesc}</span>
                </div>
            </div>`;
        });
    } else {
        html += `<div class="glass-card" style="padding: 20px; text-align: center; color: var(--text-muted);">Нет исходящих подключений</div>`;
    }
    html += `</div>`;

    // -- 4. ROUTING RULES --
    if (config.route && config.route.rules && config.route.rules.length > 0) {
        html += `<div style="margin-bottom: 25px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: var(--accent-purple); display: flex; align-items: center; gap: 8px;">
                    <i class="fa-solid fa-route"></i> <span data-i18n="singbox_config_routing">Маршрутизация (Routing Rules)</span>
                </h4>
                <button class="btn secondary-btn edit-json-btn" data-type="singbox-routing" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
            </div>
            <div class="table-container">
                <table class="glass-table" style="font-size: 12px;">
                    <thead>
                        <tr>
                            <th style="padding: 10px 14px;">Rule Match</th>
                            <th style="padding: 10px 14px;">Target Outbound</th>
                        </tr>
                    </thead>
                    <tbody>`;
        config.route.rules.forEach(r => {
            let matchDesc = [];
            if (r.inbound) matchDesc.push(`Inbound: <code>${r.inbound.join(", ")}</code>`);
            if (r.domain) matchDesc.push(`Domain: <code>${r.domain.join(", ")}</code>`);
            if (r.domain_suffix) matchDesc.push(`Domain Suffix: <code>${r.domain_suffix.join(", ")}</code>`);
            if (r.domain_regex) matchDesc.push(`Domain Regex: <code>${r.domain_regex.join(", ")}</code>`);
            if (r.domain_keyword) matchDesc.push(`Domain Keyword: <code>${r.domain_keyword.join(", ")}</code>`);
            if (r.ip_is_private) matchDesc.push(`IP: <code>Private / LAN</code>`);
            if (r.ip_cidr) matchDesc.push(`IP CIDR: <code>${r.ip_cidr.join(", ")}</code>`);
            if (r.protocol) matchDesc.push(`Protocol: <code>${r.protocol.join(", ")}</code>`);
            if (r.rule_set) matchDesc.push(`RuleSet: <code>${r.rule_set.join(", ")}</code>`);
            if (matchDesc.length === 0) matchDesc.push("Default / Any");

            html += `<tr>
                <td style="padding: 10px 14px; color: var(--text-secondary);">${matchDesc.join(" | ")}</td>
                <td style="padding: 10px 14px;"><span class="tag-badge tag-badge-proxy" style="font-size: 11px;">${r.outbound || "—"}</span></td>
            </tr>`;
        });
        html += `</tbody></table></div></div>`;
    }

    parsedContainer.innerHTML = html;

    const singboxLogLevelSelect = parsedContainer.querySelector("#singbox-loglevel-select");
    if (singboxLogLevelSelect) {
        initCustomSelect(singboxLogLevelSelect);
        singboxLogLevelSelect.addEventListener("change", async (e) => {
            const newLevel = e.target.value;
            window.singboxConfig.log = window.singboxConfig.log || {};
            window.singboxConfig.log.level = newLevel;
            const res = await apiFetch("/api/singbox/config/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ config: window.singboxConfig })
            });
            if (res && res.success) {
                showToast(t("singbox_loglevel_saved", "Уровень журнала Sing-box сохранен!"));
                loadSingboxConfig();
            } else {
                showToast(res ? res.msg : t("singbox_loglevel_error", "Ошибка сохранения уровня журнала"), "error");
            }
        });
    }

    // Bind dynamically generated JSON edit buttons
    parsedContainer.querySelectorAll(".edit-json-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const type = btn.getAttribute("data-type");
            const idx = parseInt(btn.getAttribute("data-index"));

            if (type === "singbox-log") {
                window.openJsonEditModal(t("singbox_config_log_title", "Системные настройки и логирование"), config.log || {}, async (newObj) => {
                    config.log = newObj;
                    await saveSingboxConfigDirect(config);
                });
            } else if (type === "singbox-inbounds") {
                window.openJsonEditModal(t("singbox_config_inbounds", "Входящие подключения (Inbounds)"), config.inbounds || [], async (newObj) => {
                    config.inbounds = newObj;
                    await saveSingboxConfigDirect(config);
                });
            } else if (type === "singbox-inbound") {
                const ib = config.inbounds && config.inbounds[idx] ? config.inbounds[idx] : {};
                window.openJsonEditModal(`${t("nav_inbounds", "Подключение")}: ${ib.type || "inbound"} (:${ib.listen_port || ib.port || ""})`, ib, async (newObj) => {
                    if (!config.inbounds) config.inbounds = [];
                    config.inbounds[idx] = newObj;
                    await saveSingboxConfigDirect(config);
                });
            } else if (type === "singbox-outbounds") {
                window.openJsonEditModal(t("singbox_config_outbounds", "Исходящие подключения (Outbounds)"), config.outbounds || [], async (newObj) => {
                    config.outbounds = newObj;
                    await saveSingboxConfigDirect(config);
                });
            } else if (type === "singbox-routing") {
                window.openJsonEditModal(t("singbox_config_routing", "Маршрутизация (Routing Rules)"), config.route || {}, async (newObj) => {
                    config.route = newObj;
                    await saveSingboxConfigDirect(config);
                });
            }
        });
    });

    translatePage(parsedContainer);
}

async function saveSingboxConfigDirect(cfg) {
    const res = await apiFetch("/api/singbox/config/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: cfg })
    });
    if (res && res.success) {
        showToast(t("singbox_config_saved", "Конфигурация Sing-box сохранена"));
        loadSingboxConfig();
    } else {
        showToast(res ? res.msg : t("singbox_config_save_error", "Ошибка сохранения конфигурации"), "error");
    }
}

export function setupSingboxConfigListeners() {
    const tabParsed = document.getElementById("singbox-config-tab-parsed");
    const tabRaw = document.getElementById("singbox-config-tab-raw");
    const containerParsed = document.getElementById("singbox-config-parsed-container");
    const containerRaw = document.getElementById("singbox-config-raw-container");
    const saveBtn = document.getElementById("singbox-config-save-btn");
    const resetBtn = document.getElementById("singbox-config-reset-btn");

    if (tabParsed && tabRaw && containerParsed && containerRaw) {
        tabParsed.addEventListener("click", () => {
            tabParsed.classList.add("active");
            tabRaw.classList.remove("active");
            containerParsed.style.display = "block";
            containerRaw.style.display = "none";
            if (saveBtn) saveBtn.style.display = "none";
            if (resetBtn) resetBtn.style.display = "none";
        });

        tabRaw.addEventListener("click", () => {
            tabRaw.classList.add("active");
            tabParsed.classList.remove("active");
            containerRaw.style.display = "block";
            containerParsed.style.display = "none";
            if (saveBtn) saveBtn.style.display = "inline-flex";
            if (resetBtn) resetBtn.style.display = "inline-flex";
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener("click", async () => {
            const textarea = document.getElementById("singbox-config-raw-pre");
            if (!textarea) return;

            try {
                const configObj = JSON.parse(textarea.value);
                const res = await apiFetch("/api/singbox/config/save", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ config: configObj, is_custom: true })
                });
                if (res && res.success) {
                    showToast(t("singbox_config_saved", "Конфигурация sing-box сохранена"));
                    loadSingboxConfig();
                } else {
                    showToast(res ? res.msg : t("singbox_config_save_error", "Ошибка сохранения конфигурации"), "error");
                }
            } catch (err) {
                showToast(t("invalid_json", "Некорректный JSON синтаксис"), "error");
            }
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", async () => {
            if (!confirm(t("confirm_reset_config", "Вы уверены, что хотите сбросить конфигурацию к дефолтной?"))) return;
            const res = await apiFetch("/api/singbox/config/reset", { method: "POST" });
            if (res && res.success) {
                showToast(t("singbox_config_reset", "Конфигурация сброшена"));
                loadSingboxConfig();
            } else {
                showToast(res ? res.msg : t("singbox_config_reset_error", "Ошибка сброса конфигурации"), "error");
            }
        });
    }
}
