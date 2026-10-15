import { apiGet, apiPost, checkEnergyServiceAvailable, startKeepAliveMonitoring, stopKeepAliveMonitoring, updateEmsVisibility } from '../api.js';
import { escapeHtml, fmt, isBackendDisconnected, showConnectionLost, showConnectionRestored } from '../common.js';
import { REFRESH_INTERVAL, autoEnabled, autoTimer, backendConnected, isRefreshing, showHidden, $ } from '../config.js';
import { translateAllElements } from '../i18n.js';
import { openLog } from '../utilities/logs.js';
import { openNetwork } from '../utilities/network.js';
import { showSettings } from '../utilities/settings.js';
import { activeWindows, closeWindow, createWindow, focusWindow, toast, windowKey } from '../windows.js';
import { t } from '../translations-bridge.js';

export { closeConsole };
export { couplerCmd };
export { openConsole };
export { procCard };
export { procCmd };
export { refresh };
export { refreshConsole };
export { render };
export { renderConsole };
export { scheduleNext };
export { systemCmd };
export { systemCmdConfirm };
export { toggleAuto };
export { toggleHidden };

function toggleHidden() {
    showHidden = !showHidden;
    const btn = $("show-hidden-text");
    btn.textContent = showHidden ? "Hide Hidden" : "Show Hidden";
    refresh();
}

// Authentication: when the backend returns 401 we show the login
// overlay, await a successful login, then replay the original request.
// Cookies travel automatically with same-origin fetch(), so once the
async function refresh() {
    if (isRefreshing) return;
    isRefreshing = true;
    const btn = $("refresh-btn");
    btn.disabled = true;
    try {
        const data = await apiGet("/api/system/status");
        render(data);
        $("last-refresh").textContent = new Date().toLocaleTimeString("fr-FR");
        
        // Check EnergyService availability on each refresh
        const newEmsAvailable = await checkEnergyServiceAvailable();
        if (newEmsAvailable !== emsAvailable) {
            emsAvailable = newEmsAvailable;
            await updateEmsVisibility();
        }
        
        // If backend reports disconnected (agent not connected), show overlay
        // This handles the case where web server is up but agent is not connected
        if (data && !data.connected) {
            if (backendConnected) {
                showConnectionLost();
            }
        } else {
            // If we were in disconnected state and now connected, restore UI
            if (!backendConnected) {
                showConnectionRestored();
            }
        }
    } catch (e) {
        toast(t.t("toast.refresh_error", {error: e.message}), false);
        // For network failures, show connection lost overlay
        if (e.isConnectionError || isBackendDisconnected(e)) {
            if (backendConnected) {
                showConnectionLost();
            }
        }
    } finally {
        isRefreshing = false;
        btn.disabled = false;
    }
    // Note: Automatic scheduling removed - refresh is now driven by KeepAlive mechanism
}

function scheduleNext() {
    // With KeepAlive mechanism, we only need to trigger an immediate refresh
    // The KeepAlive will handle subsequent refresh timing based on changes
    if (autoTimer) clearTimeout(autoTimer);
    autoTimer = null;
    if (autoEnabled) {
        // Trigger immediate refresh, KeepAlive will handle the scheduling
        refresh().catch(() => {});
    }
}

function render(data) {
    const pill = $("conn-status");
    const info = $("agent-info");
    const summary = $("system-summary");
    const grid = $("processes-grid");

    if (!data.connected) {
        // Agent is not connected - show disconnected state
        // This is different from backend being unreachable (handled by overlay)
        pill.className = "status-pill disconnected";
        pill.textContent = t.t("status.disconnected");
        const sys = data.system || {};
        info.textContent = (sys.hostname || sys.ip_address)
            ? `— ${fmt(sys.hostname)} · ${fmt(sys.ip_address)}`
            : "— ?";
        summary.innerHTML = `<div class="empty">${escapeHtml(data.error || t.t("general.not_connected"))}</div>`;
        grid.innerHTML = "";
        t.translateAllElements();
        return;
    }

    pill.className = "status-pill connected";
    pill.textContent = t.t("status.connected");
    const s = data.system;
    info.textContent = `— ${fmt(s.hostname)} · ${fmt(s.ip_address)}`;
    summary.innerHTML = `
        <h2>${escapeHtml(s.name)} <span class="sub" style="color:var(--muted);font-weight:400;">v${fmt(s.version)}</span></h2>
        <div class="row"><span class="k" data-i18n="system.host">Host</span><span class="v">${fmt(s.hostname)}</span></div>
        <div class="row"><span class="k" data-i18n="system.ip_address">IP Address</span><span class="v">${fmt(s.ip_address)}</span></div>
        <div class="row"><span class="k" data-i18n="system.started">Started</span><span class="v">${fmt(s.start_time)}</span></div>
        <div class="row"><span class="k" data-i18n="system.configuration">Configuration</span><span class="v">${fmt(s.settings)}</span></div>
        <div class="card-actions">
            <button class="danger" onclick="systemCmdConfirm('halt')">⏻ Halt</button>
            <button class="danger" onclick="systemCmdConfirm('reboot')">⟲ Reboot</button>
            <button onclick="systemCmdConfirm('navigation_restart')" title="Restart all processes">⟲ Restart App</button>
            <button class="open-btn" onclick="showSettings('agent')" title="Agent settings">⚙ Agent Settings</button>
            <button class="open-btn" onclick="showSettings('network')" title="Network settings">⚙ Network Settings</button>
            <button class="open-btn" onclick="openNetwork()" style="margin-left: auto;">⚙ Network</button>
        </div>
    `;

    const procs = s.processes || [];
    if (!procs.length) {
        grid.innerHTML = `<div class="empty" data-i18n="main.no_processes">No processes registered.</div>`;
        t.translateAllElements();
        return;
    }
    // Filter and sort processes: filter out hidden processes unless showHidden is true, then sort by display_order (with name as tiebreaker for stability)
    const filtered = procs.filter(p => showHidden || p.hidden !== true);
    const ordered = filtered.slice().sort((a, b) => {
        const orderA = a.display_order !== undefined ? a.display_order : 0;
        const orderB = b.display_order !== undefined ? b.display_order : 0;
        if (orderA !== orderB) {
            return orderA - orderB;
        }
        return a.name.localeCompare(b.name);
    });
    grid.innerHTML = ordered.map(procCard).join("");
    t.translateAllElements();
}

function procCard(p) {
    const servers = (p.servers || []).map(srv => `
        <div class="server-item">
            <strong>${escapeHtml(srv.name)}</strong> [${escapeHtml(srv.server_class)}]
            ${srv.running ? '\u00b7 <span style="color:var(--green)">running</span>' : '\u00b7 <span style="color:var(--red)">stopped</span>'}
            ${srv.port ? `\u00b7 port ${srv.port}` : ""}
            ${srv.protocol ? `\u00b7 ${escapeHtml(srv.protocol)}` : ""}
            ${srv.nb_connections ? `\u00b7 ${srv.nb_connections} conn.` : ""}
        </div>
    `).join("");
    // Contextual action buttons based on process state.
    const isRunning = p.state === "RUNNING";
    const startBtn = `<button ${isRunning ? 'disabled' : ''} onclick="procCmd('${escapeHtml(p.name)}','start')">\u25b6 Start</button>`;
    const stopBtn = `<button ${!isRunning ? 'disabled' : ''} onclick="procCmd('${escapeHtml(p.name)}','stop')">\u25a0 Stop</button>`;
    const restartBtn = `<button ${!isRunning ? 'disabled' : ''} onclick="procCmd('${escapeHtml(p.name)}','restart')">\u27f2 Restart</button>`;
    const logBtn = `<button onclick="openLog('${escapeHtml(p.name)}')">\ud83d\udccb Log</button>`;
    const settingsBtn = p.settings ? `<button class="open-btn" onclick="showSettings('${escapeHtml(p.name)}')">\u2699 Settings</button>` : '';
    
    // Build service buttons from the services list
    const serviceButtons = [];
    const services = p.services || [];
    for (const svc of services) {
        const rpcService = svc.rpc_service || '';
        const svcName = svc.service_name || '';
        if (rpcService === 'NavigationConsole') {
            serviceButtons.push(`<button class="open-btn" onclick="openConsole('${escapeHtml(p.name)}')">\u2913 Console</button>`);
        } else if (rpcService === 'Nmea2000ControllerService') {
            serviceButtons.push(`<button class="open-btn" onclick="openNmea2000('${escapeHtml(p.name)}')">\u2699 NMEA2000</button>`);
        } else if (rpcService === 'EngineData') {
            serviceButtons.push(`<button class="open-btn" onclick="openEngineData('${escapeHtml(p.name)}')">\u26a1 Engine</button>`);
        } else if (rpcService === 'MPPTService') {
            serviceButtons.push(`<button class="open-btn" onclick="openMppt('${escapeHtml(p.name)}')">\u2600 MPPT</button>`);
        } else if (rpcService === 'BatteryService') {
            serviceButtons.push(`<button class="open-btn" onclick="openBattery('${escapeHtml(p.name)}')">\u26a1\ufe0f Battery</button>`);
        } else if (rpcService === 'DC_DC_Service') {
            serviceButtons.push(`<button class="open-btn" onclick="openDcDc('${escapeHtml(p.name)}')">\u26a1 DC-DC</button>`);
        }
    }
    
    return `
        <div class="card">
            <h2>
                <span class="proc-name">${escapeHtml(p.name)}</span>
                ${p.secure_grpc ? '<span class="secure-badge" title="TLS">\ud83d\udd12</span>' : ''}
                <span class="badge ${p.state}">${p.state}</span>
            </h2>
            <div class="row"><span class="k">PID</span><span class="v">${fmt(p.pid)}</span></div>
            <div class="row"><span class="k">Port gRPC</span><span class="v">${fmt(p.grpc_port)}</span></div>
            <div class="row"><span class="k">Version</span><span class="v">${fmt(p.version)}</span></div>
            <div class="row"><span class="k" data-i18n="process.started">Started</span><span class="v">${fmt(p.start_time)}</span></div>
            ${p.status ? `<div class="row"><span class="k" data-i18n="process.status">Status</span><span class="v">${fmt(p.status)}</span></div>` : ""}
            ${p.error ? `<div class="row"><span class="k" data-i18n="process.error">Error</span><span class="v" style="color:var(--red)">${fmt(p.error)}</span></div>` : ""}

            ${p.is_systemd ? '<div class="row"><span class="k" data-i18n="process.control">Control</span><span class="v" data-i18n="process.systemd">systemd</span></div>' : ""}
            ${servers ? `<div class="servers">${servers}</div>` : ""}
            <div class="card-actions">
                ${startBtn}
                ${stopBtn}
                ${restartBtn}
                ${logBtn}
                ${settingsBtn}
            </div>
            ${serviceButtons.length > 0 ? `<div class="card-actions">${serviceButtons.join('')}</div>` : ''}
        </div>
    `;
    t.translateAllElements();
}
async function procCmd(target, cmd) {
    try {
        const r = await apiPost(`/api/process/${encodeURIComponent(target)}/${cmd}`, {});
        toast(`${cmd} ${target}: ${r.ok ? "OK" : (r.error || t.t("toast.failure"))}`, r.ok);
        if (r.ok) setTimeout(refresh, 800);
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}

async function systemCmd(cmd) {
    try {
        const r = await apiPost(`/api/system/${cmd}`, {});
        toast(`${cmd}: ${r.ok ? "OK" : (r.error || t.t("toast.failure"))}`, r.ok);
        if (r.ok) setTimeout(refresh, 800);
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}

// --- Console view ----------------------------------------------------
async function openConsole(processName) {
    const win = createWindow('console', processName, `Console — ${processName}`, (w) => {
        if (w.timer) { clearTimeout(w.timer); w.timer = null; }
    });
    win.processName = processName;
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    await refreshConsole(win);
}

async function refreshConsole(win) {
    if (!win || activeWindows.get(windowKey('console', win.processName)) !== win) return;
    const processName = win.processName;
    try {
        const d = await apiGet(`/api/console/${encodeURIComponent(processName)}/status`);
        if (activeWindows.get(windowKey('console', processName)) === win) {
            renderConsole(d, processName, win.body);
            win.timer = setTimeout(() => refreshConsole(win), REFRESH_INTERVAL);
        }
    } catch (e) {
        win.body.innerHTML = `<div class="empty">Erreur: ${escapeHtml(e.message)}</div>`;
        win.timer = setTimeout(() => refreshConsole(win), REFRESH_INTERVAL);
    }
}

function renderConsole(d, processName, body) {
    if (!d.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(d.error || "Erreur console")}</div>`;
        t.translateAllElements();
        return;
    }
    const servers = (d.servers || []).map(srv => {
        const conns = (srv.connections || []).map(c => `
            <div class="server-item">
                ${escapeHtml(c.remote_ip)}:${fmt(c.remote_port)}
                · ${fmt(c.total_msg)} msg · ${fmt(c.msg_rate && c.msg_rate.toFixed(1))}/s
            </div>
        `).join("");
        return `
            <div class="console-server">
                <strong>${escapeHtml(srv.name)}</strong> [${escapeHtml(srv.server_class)}]
                ${srv.running ? '· <span style="color:var(--green)">running</span>' : '· <span style="color:var(--red)">stopped</span>'}
                ${srv.port ? `· port ${srv.port}` : ""}
                ${srv.protocol ? `· ${escapeHtml(srv.protocol)}` : ""}
                ${srv.nb_connections ? `· ${srv.nb_connections} conn.` : ""}
                ${conns ? `<div class="servers">${conns}</div>` : ""}
            </div>
        `;
    }).join("");

    const couplers = (d.couplers || []).map(c => {
        const state = c.state;
        const isRunning = state === "RUNNING";
        const isSuspended = state === "SUSPENDED";
        const isActive = isRunning || isSuspended;
        const startStopBtn = isActive
            ? `<button onclick="couplerCmd('${escapeHtml(processName)}','${escapeHtml(c.name)}','stop')">■ Stop</button>`
            : `<button onclick="couplerCmd('${escapeHtml(processName)}','${escapeHtml(c.name)}','start')">▶ Start</button>`;
        const suspendResumeBtn = isRunning
            ? `<button onclick="couplerCmd('${escapeHtml(processName)}','${escapeHtml(c.name)}','suspend')">⏸ Suspend</button>`
            : (isSuspended
                ? `<button onclick="couplerCmd('${escapeHtml(processName)}','${escapeHtml(c.name)}','resume')">▶ Resume</button>`
                : `<button disabled>⏸ Suspend</button>`);
        const traceOn = c.trace_on === true;
        const traceBtn = traceOn
            ? `<button onclick="couplerCmd('${escapeHtml(processName)}','${escapeHtml(c.name)}','stop_trace')">⏹ Stop trace</button>`
            : `<button ${!isActive ? 'disabled' : ''} onclick="couplerCmd('${escapeHtml(processName)}','${escapeHtml(c.name)}','start_trace_raw')">⏵ Start trace</button>`;
        return `
            <div class="card coupler-card">
                <h2>
                    <span class="proc-name">${escapeHtml(c.name)}</span>
                    <span class="badge ${c.state}">${c.state}</span>
                </h2>
                <div class="row"><span class="k">Classe</span><span class="v">${fmt(c.coupler_class)}</span></div>
                <div class="row"><span class="k">Protocole</span><span class="v">${fmt(c.protocol)}</span></div>
                <div class="row"><span class="k" data-i18n="coupler.device_state">Device State</span><span class="v">${fmt(c.dev_state)}</span></div>
                <div class="row"><span class="k" data-i18n="coupler.msg_in_out">Msg in/out</span><span class="v">${fmt(c.msg_in)} / ${fmt(c.msg_out)}</span></div>
                <div class="row"><span class="k" data-i18n="coupler.rate_in_out">Rate in/out</span><span class="v">${fmt(c.input_rate && c.input_rate.toFixed(1))} / ${fmt(c.output_rate && c.output_rate.toFixed(1))} /s</span></div>
                ${c.error ? `<div class="row"><span class="k">Erreur</span><span class="v" style="color:var(--red)">${fmt(c.error)}</span></div>` : ""}
                ${c.status ? `<div class="row"><span class="k">Statut</span><span class="v">${fmt(c.status)}</span></div>` : ""}
                <div class="row"><span class="k" data-i18n="coupler.trace">Trace</span><span class="v" style="color:${c.trace_on ? 'var(--green)' : 'var(--muted)'}" data-i18n-text="${c.trace_on ? 'coupler.activated' : 'coupler.inactive'}">${c.trace_on ? 'activated' : 'inactive'}</span></div>
                <div class="card-actions">${startStopBtn}${suspendResumeBtn}${traceBtn}</div>
            </div>
        `;
    }).join("");

    body.innerHTML = `
        <div class="console-section">
            <h3 data-i18n="console.servers">TCP/UDP Servers</h3> (${(d.servers||[]).length})
            ${servers || '<div class="empty" data-i18n="console.no_servers">No servers.</div>'}
        </div>
        <div class="console-section">
            <h3 data-i18n="console.couplers">Couplers</h3> (${(d.couplers||[]).length})
            <div class="grid">${couplers || '<div class="empty" data-i18n="console.no_couplers">No couplers.</div>'}</div>
        </div>
    `;
    t.translateAllElements();
}

async function couplerCmd(process, coupler, cmd) {
    try {
        const r = await apiPost(`/api/console/${encodeURIComponent(process)}/coupler/${encodeURIComponent(coupler)}`, { cmd });
        toast(`${cmd} ${coupler}: ${r.ok ? "OK" : (r.error || t.t("toast.failure"))}`, r.ok);
        if (r.ok) {
            const win = focusWindow('console', process);
            if (win) setTimeout(() => refreshConsole(win), 800);
        }
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}

function closeConsole(processName) {
    closeWindow(windowKey('console', processName));
}

function toggleAuto() {
    autoEnabled = $("auto-refresh").checked;
    if (autoEnabled) {
        // Restart KeepAlive monitoring and trigger immediate refresh
        startKeepAliveMonitoring();
        scheduleNext();
    } else {
        // Stop KeepAlive monitoring
        stopKeepAliveMonitoring();
        if (autoTimer) {
            clearTimeout(autoTimer);
            autoTimer = null;
        }
    }
}

async function systemCmdConfirm(cmd) {
    const labels = {halt: t.t("command.halt_confirm"), reboot: t.t("command.reboot_confirm"),
                    navigation_restart: t.t("command.navigation_restart_confirm")};
    if (!confirm(`Confirmer : ${labels[cmd] || cmd} ?`)) return;
    try {
        const r = await apiPost("/api/system", { cmd });
        toast(`${cmd}: ${r.ok ? "OK" : (r.error || t.t("toast.failure"))}`, r.ok);
        if (r.ok) setTimeout(refresh, 1500);
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}

// Log window management using createWindow system
