import { apiFetch } from "../../../api.js";
import { t, translatePage } from "../../../i18n.js";
import { saveXrayConfigToServer } from "./api.js";
import { initEditorModal } from "./editor_modal.js";

// Ensure openJsonEditModal is initialized
initEditorModal();

export function getLogLevelStyle(level) {
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

export async function loadXrayConfig() {
    const res = await apiFetch("/api/xray/config");
    if (!res || !res.success) return;
    
    window.xrayConfig = res.config;
    const config = window.xrayConfig;
    
    // Fill Raw JSON
    const rawPre = document.getElementById("xray-config-raw-pre");
    if (rawPre) {
        rawPre.value = JSON.stringify(config, null, 2);
    }
    
    // Parse & Render Structure
    const parsedContainer = document.getElementById("xray-config-parsed-container");
    if (!parsedContainer) return;
    
    let html = "";

    // -- 1. LOGGING & GLOBAL SETTINGS --
    config.log = config.log || {};
    const currLevel = config.log.loglevel || "info";
    const logStyle = getLogLevelStyle(currLevel);
    html += `<div style="margin-bottom: 25px;">
        <h4 style="margin-top: 0; margin-bottom: 12px; font-size: 15px; font-weight: 600; color: var(--accent-orange); display: flex; align-items: center; gap: 8px; width: 100%;">
            <i class="fa-solid fa-file-invoice"></i> <span data-i18n="config_log_title">Системные настройки и логирование</span>
            <button class="btn secondary-btn edit-json-btn" data-type="xray-log" style="margin-left: auto; padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
        </h4>
        <div class="glass-card" style="padding: 15px; border-radius: 10px; background: rgba(255,255,255,0.015);">
            <div style="font-size: 13px; line-height: 1.6; color: var(--text-secondary);">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">
                    <span>LogLevel:</span>
                    <select id="xray-loglevel-select" style="padding: 3px 22px 3px 10px; font-size: 12px; border-radius: 6px; background: ${logStyle.bg}; color: ${logStyle.color}; border: ${logStyle.border}; font-weight: 600; cursor: pointer; outline: none; appearance: none; -webkit-appearance: none; -moz-appearance: none; transition: all 0.2s ease;">
                        <option value="debug" style="background: #0f172a; color: #f8fafc;" ${currLevel === 'debug' ? 'selected' : ''}>debug</option>
                        <option value="info" style="background: #0f172a; color: #f8fafc;" ${currLevel === 'info' ? 'selected' : ''}>info</option>
                        <option value="warning" style="background: #0f172a; color: #f8fafc;" ${currLevel === 'warning' ? 'selected' : ''}>warning</option>
                        <option value="error" style="background: #0f172a; color: #f8fafc;" ${currLevel === 'error' ? 'selected' : ''}>error</option>
                        <option value="none" style="background: #0f172a; color: #f8fafc;" ${currLevel === 'none' ? 'selected' : ''}>none</option>
                    </select>
                </div>
                <div style="margin-top: 5px;">Access Log: <code style="font-size: 11px; word-break: break-all; color: var(--text-primary);">${config.log.access || "—"}</code></div>
                <div style="margin-top: 5px;">Error Log: <code style="font-size: 11px; word-break: break-all; color: var(--text-primary);">${config.log.error || "—"}</code></div>
            </div>
        </div>
    </div>`;
    
    // -- 2. INBOUNDS --
    html += `<div style="margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px;">
            <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: var(--accent-blue); display: flex; align-items: center; gap: 8px;">
                <i class="fa-solid fa-arrow-right-to-bracket"></i> <span data-i18n="xray_config_inbounds">Входящие подключения (Inbounds)</span>
            </h4>
            <button class="btn primary-btn" id="xray-config-add-inbound-btn" style="padding: 4px 10px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-solid fa-plus"></i> <span data-i18n="config_add_inbound">Добавить Inbound</span></button>
        </div>`;
                
    if (config.inbounds && config.inbounds.length > 0) {
        config.inbounds.forEach((ib, idx) => {
            let streamDesc = "";
            let securityType = "None";
            
            if (ib.streamSettings) {
                const ss = ib.streamSettings;
                securityType = ss.security || "None";
                if (ss.network) {
                    streamDesc += `Network: <code>${ss.network}</code>`;
                }
                if (ss.security === "reality" && ss.realitySettings) {
                    const rs = ss.realitySettings;
                    streamDesc += ` | Reality Dest: <code style="color: #18dcff;">${rs.dest || "—"}</code> | ServerNames: <code>${(rs.serverNames || []).join(", ")}</code>`;
                } else if (ss.security === "tls" && ss.tlsSettings) {
                    const ts = ss.tlsSettings;
                    streamDesc += ` | TLS ServerName: <code style="color: #18dcff;">${ts.serverName || "—"}</code>`;
                }
            }
            
            // Clients parsing
            let clientsRows = "";
            let clientsList = [];
            if (ib.settings && ib.settings.clients) {
                clientsList = ib.settings.clients;
            }
            
            if (clientsList.length > 0) {
                clientsRows = `<div class="table-container" style="margin-top: 10px;">
                    <table class="glass-table" style="font-size: 12px; background: rgba(0,0,0,0.15); border-radius: 8px;">
                        <thead>
                            <tr>
                                <th style="padding: 8px 12px;" data-i18n="xray_config_th_email">Email</th>
                                <th style="padding: 8px 12px;" data-i18n="xray_config_th_uuid">UUID / Password</th>
                                <th style="padding: 8px 12px;" data-i18n="xray_config_th_flow">Flow / AlterId</th>
                            </tr>
                        </thead>
                        <tbody>`;
                clientsList.forEach(c => {
                    const pwd = c.id || c.password || "—";
                    const flow = c.flow || (c.alterId !== undefined ? `AlterId: ${c.alterId}` : "—");
                    clientsRows += `<tr>
                        <td style="padding: 8px 12px;"><strong>${c.email || "—"}</strong></td>
                        <td style="padding: 8px 12px; font-family: monospace; user-select: text;">${pwd}</td>
                        <td style="padding: 8px 12px;"><code>${flow}</code></td>
                    </tr>`;
                });
                clientsRows += `</tbody></table></div>`;
            } else if (ib.protocol === "dokodemo-door") {
                clientsRows = `<div style="font-size: 12px; color: var(--text-muted); margin-top: 8px; font-style: italic;" data-i18n="config_grpc_api">Management gRPC API</div>`;
            } else if (ib.settings && ib.settings.accounts) {
                const users = ib.settings.accounts.map(a => a.user || "unknown");
                clientsRows = `<div style="font-size: 12px; color: var(--text-secondary); margin-top: 8px;">
                     Socks5 Auth: ` + users.map(u => `<span class="badge active" style="margin: 2px; display: inline-block;">${u}</span>`).join(" ") + 
                `</div>`;
            } else {
                clientsRows = `<div style="font-size: 12px; color: var(--text-muted); margin-top: 8px; font-style: italic;" data-i18n="config_no_clients">No clients</div>`;
            }
            
            let ssOptions = "";
            if (ib.protocol === "shadowsocks" && ib.settings && ib.settings.method) {
                ssOptions = `<div style="margin-top: 4px;">Method: <code>${ib.settings.method}</code></div>`;
            }
            
            let securityBadgeClass = "tag-badge-direct";
            if (securityType === "reality") securityBadgeClass = "tag-badge-warp";
            else if (securityType === "tls") securityBadgeClass = "tag-badge-proxy";
            
            html += `<div class="glass-card" style="padding: 16px; margin-bottom: 15px; border-radius: 12px; background: rgba(255,255,255,0.015); border: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 10px;">
                    <div>
                        <span class="tag-badge tag-badge-warp" style="text-transform: uppercase; font-size: 11px;">${ib.protocol}</span>
                        <strong style="font-size: 14px; color: var(--text-primary); margin-left: 8px;">:${ib.port || ib.listen || "—"}</strong>
                        <span style="font-size: 12px; color: var(--text-muted); font-family: monospace; margin-left: 10px;">(Tag: ${ib.tag || "—"})</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <button class="btn secondary-btn edit-json-btn" data-type="xray-inbound" data-index="${idx}" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
                        <span class="tag-badge ${securityBadgeClass}">${securityType}</span>
                    </div>
                </div>
                <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
                    ${streamDesc ? `<div>Transport: ${streamDesc}</div>` : ""}
                    ${ssOptions}
                </div>
                ${clientsRows}
            </div>`;
        });
    } else {
        html += `<div class="glass-card" style="padding: 20px; text-align: center; color: var(--text-muted);" data-i18n="config_no_inbounds">Входящие подключения отсутствуют</div>`;
    }
    html += `</div>`;
    
    // -- 3. OUTBOUNDS --
    html += `<div style="margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px;">
            <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: var(--accent-green); display: flex; align-items: center; gap: 8px;">
                <i class="fa-solid fa-arrow-right-from-bracket"></i> <span data-i18n="xray_config_outbounds">Исходящие подключения (Outbounds)</span>
            </h4>
            <button class="btn primary-btn" id="xray-config-add-outbound-btn" style="padding: 4px 10px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-solid fa-plus"></i> <span data-i18n="config_add_outbound">Добавить Outbound</span></button>
        </div>`;
                
    if (config.outbounds && config.outbounds.length > 0) {
        config.outbounds.forEach((ob, idx) => {
            let details = "";
            let extra = "";
            
            if (ob.settings && ob.settings.vnext) {
                ob.settings.vnext.forEach(v => {
                    const address = v.address || "—";
                    const port = v.port || "—";
                    let users = "";
                    if (v.users) {
                        users = v.users.map(u => u.id || u.email || "—").join(", ");
                    }
                    details += `<div>Server: <strong style="color: var(--text-primary);">${address}:${port}</strong>${users ? ` | Users: <code>${users}</code>` : ""}</div>`;
                });
            } else if (ob.settings && ob.settings.servers) {
                ob.settings.servers.forEach(s => {
                    const address = s.address || "—";
                    const port = s.port || "—";
                    details += `<div>Server: <strong style="color: var(--text-primary);">${address}:${port}</strong></div>`;
                });
            } else if (ob.protocol === "freedom") {
                details = `<span style="color: var(--accent-green);" data-i18n="xray_outbound_direct">Прямое подключение (Direct)</span>`;
            } else if (ob.protocol === "blackhole") {
                details = `<span style="color: var(--accent-rose);" data-i18n="xray_outbound_blocked">Блокировка трафика (Blocked)</span>`;
            } else {
                details = `<span style="color: var(--text-muted); font-style: italic;">—</span>`;
            }
            
            if (ob.streamSettings) {
                const ss = ob.streamSettings;
                let security = ss.security || "none";
                extra = `<div>Transport: <code>${ss.network || "tcp"}</code> (Security: <code>${security}</code>)</div>`;
            }
            
            let badgeClass = "tag-badge-direct";
            if (ob.tag === "blocked") badgeClass = "tag-badge-blocked";
            else if (ob.tag === "warp") badgeClass = "tag-badge-warp";
            else if (ob.tag === "api") badgeClass = "tag-badge-api";
            else if (ob.protocol !== "freedom") badgeClass = "tag-badge-proxy";
            
            html += `<div class="glass-card" style="padding: 15px; margin-bottom: 12px; border-radius: 10px; background: rgba(255,255,255,0.015); border: 1px solid var(--border-color);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 6px;">
                    <div>
                        <span class="tag-badge ${badgeClass}" style="text-transform: uppercase; font-size: 11px;">${ob.protocol}</span>
                        <strong style="font-family: monospace; font-size: 13px; margin-left: 8px; color: var(--text-primary);">${ob.tag || "—"}</strong>
                    </div>
                    <div>
                        <button class="btn secondary-btn edit-json-btn" data-type="xray-outbound" data-index="${idx}" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
                    </div>
                </div>
                <div style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
                    ${details}
                    ${extra}
                </div>
            </div>`;
        });
    } else {
        html += `<div class="glass-card" style="padding: 20px; text-align: center; color: var(--text-muted);" data-i18n="config_no_outbounds">Исходящие подключения отсутствуют</div>`;
    }
    html += `</div>`;
    
    // -- 4. ROUTING RULES --
    html += `<div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: var(--accent-purple); display: flex; align-items: center; gap: 8px;">
                <i class="fa-solid fa-route"></i> <span data-i18n="xray_config_rules">Правила маршрутизации (Routing Rules)</span>
            </h4>
            <button class="btn secondary-btn edit-json-btn" data-type="xray-routing" style="padding: 4px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; height: auto;"><i class="fa-regular fa-pen-to-square"></i> JSON</button>
        </div>
        <div class="table-container">
            <table class="glass-table">
                <thead>
                    <tr>
                        <th data-i18n="xray_config_th_rules_details">Правило / Фильтр (Rule Match)</th>
                        <th data-i18n="xray_config_th_outbound">Назначение (Target Outbound)</th>
                    </tr>
                </thead>
                <tbody>`;
                
    if (config.routing && config.routing.rules && config.routing.rules.length > 0) {
        config.routing.rules.forEach(rule => {
            let ruleDetails = [];
            if (rule.inboundTag) ruleDetails.push(`Inbound: <code>${JSON.stringify(rule.inboundTag)}</code>`);
            if (rule.domain) ruleDetails.push(`Domains: <code>${rule.domain.length}</code>`);
            if (rule.ip) ruleDetails.push(`IPs: <code>${rule.ip.length}</code>`);
            if (rule.protocol) ruleDetails.push(`Protocols: <code>${JSON.stringify(rule.protocol)}</code>`);
            if (rule.user) ruleDetails.push(`Users: <code>${rule.user.length}</code>`);
            
            let badgeClass = "tag-badge-direct";
            if (rule.outboundTag === "blocked") badgeClass = "tag-badge-blocked";
            else if (rule.outboundTag === "warp") badgeClass = "tag-badge-warp";
            else if (rule.outboundTag === "api") badgeClass = "tag-badge-api";
            else if (rule.outboundTag !== "direct") badgeClass = "tag-badge-proxy";
            
            html += `<tr>
                <td style="font-size: 13px; line-height: 1.5; color: var(--text-secondary);">${ruleDetails.join(" | ") || '<span style="color: var(--text-muted); font-style: italic;" data-i18n="config_any_traffic">Любой трафик</span>'}</td>
                <td><span class="tag-badge ${badgeClass}">${rule.outboundTag}</span></td>
            </tr>`;
        });
    } else {
        html += `<tr><td colspan="2" style="text-align: center; color: var(--text-muted);" data-i18n="config_no_rules">Правила маршрутизации отсутствуют</td></tr>`;
    }
    html += `</tbody></table></div></div>`;
    
    parsedContainer.innerHTML = html;
    
    const xrayLogLevelSelect = parsedContainer.querySelector("#xray-loglevel-select");
    if (xrayLogLevelSelect) {
        xrayLogLevelSelect.addEventListener("change", async (e) => {
            const newLevel = e.target.value;
            const st = getLogLevelStyle(newLevel);
            xrayLogLevelSelect.style.background = st.bg;
            xrayLogLevelSelect.style.color = st.color;
            xrayLogLevelSelect.style.border = st.border;
            window.xrayConfig.log = window.xrayConfig.log || {};
            window.xrayConfig.log.loglevel = newLevel;
            await saveXrayConfigToServer();
        });
    }
    
    // Bind dynamically generated edit buttons
    parsedContainer.querySelectorAll(".edit-json-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const type = btn.getAttribute("data-type");
            const idx = parseInt(btn.getAttribute("data-index"));
            
            if (type === "xray-log") {
                window.openJsonEditModal(t("config_log_title", "Системные настройки и логирование"), config.log || {}, async (newObj) => {
                    config.log = newObj;
                    await saveXrayConfigToServer();
                });
            } else if (type === "xray-inbound") {
                const ib = config.inbounds[idx];
                window.openJsonEditModal(`${t("nav_inbounds", "Подключение")}: ${ib.protocol} (:${ib.port || ib.listen || ""})`, ib, async (newObj) => {
                    config.inbounds[idx] = newObj;
                    await saveXrayConfigToServer();
                });
            } else if (type === "xray-outbound") {
                const ob = config.outbounds[idx];
                window.openJsonEditModal(`${t("xray_config_outbounds", "Исходящее")}: ${ob.protocol} (${ob.tag || ""})`, ob, async (newObj) => {
                    config.outbounds[idx] = newObj;
                    await saveXrayConfigToServer();
                });
            } else if (type === "xray-routing") {
                window.openJsonEditModal(t("xray_config_rules", "Правила маршрутизации"), config.routing || {}, async (newObj) => {
                    config.routing = newObj;
                    await saveXrayConfigToServer();
                });
            }
        });
    });

    const addInboundBtn = document.getElementById("xray-config-add-inbound-btn");
    if (addInboundBtn) {
        addInboundBtn.addEventListener("click", () => {
            const template = {
                "protocol": "vless",
                "port": 12345,
                "settings": {
                    "clients": []
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "none"
                },
                "tag": "vless_custom"
            };
            window.openJsonEditModal(t("config_add_inbound_title", "Добавление Inbound JSON"), template, async (newObj) => {
                if (!config.inbounds) config.inbounds = [];
                config.inbounds.push(newObj);
                await saveXrayConfigToServer();
            });
        });
    }

    const addOutboundBtn = document.getElementById("xray-config-add-outbound-btn");
    if (addOutboundBtn) {
        addOutboundBtn.addEventListener("click", () => {
            const template = {
                "protocol": "freedom",
                "settings": {},
                "tag": "direct_custom"
            };
            window.openJsonEditModal(t("config_add_outbound_title", "Добавление Outbound JSON"), template, async (newObj) => {
                if (!config.outbounds) config.outbounds = [];
                config.outbounds.push(newObj);
                await saveXrayConfigToServer();
            });
        });
    }
    
    translatePage();
}
