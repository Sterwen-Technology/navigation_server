import {
  apiGet
} from '../api.js';
import {
  escapeHtml, fmt
} from '../common.js';
import {
  REFRESH_INTERVAL
} from '../config.js';
import {
  translateAllElements
} from '../i18n.js';
import {
  activeWindows, closeWindow, createWindow, focusWindow, windowKey
} from '../windows.js';
import {
  t
} from '../translations-bridge.js';

export { closeEngine };
export { openEngineData };
export { renderEngineDashboard };
export { renderEngineEvents };
export { setEngineEventsMode };
export { startEngineRefresh };
export { stopEngineRefresh };

function stopEngineRefresh(win) {
    if (win && win.refreshTimer) {
        clearTimeout(win.refreshTimer);
        win.refreshTimer = null;
    }
}

async function openEngineData(processName) {
    const win = createWindow('engine', processName, t.t("engine.title") || "Engine Data", (w) => {
        stopEngineRefresh(w);
    });
    win.processName = processName;
    win.eventsMode = 'runs';
    win.headerTitle.textContent = "";
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    try {
        const data = await apiGet(`/api/engine/${encodeURIComponent(processName)}`);
        renderEngineDashboard(data, processName, win);
        startEngineRefresh(win);
        await setEngineEventsMode(processName, 'runs');
    } catch (e) {
        win.body.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
    }
}

function startEngineRefresh(win) {
    if (win.refreshTimer) {
        clearTimeout(win.refreshTimer);
        win.refreshTimer = null;
    }
    const processName = win.processName;
    async function doRefresh() {
        if (activeWindows.get(windowKey('engine', processName)) !== win) return;
        let data = null;
        let engine = null;
        try {
            data = await apiGet(`/api/engine/${encodeURIComponent(processName)}`);
            if (data && data.ok) {
                const engines = data.engines || [];
                engine = engines.find(e => e.process === processName);
                if (engine) {
                    // Preserve the events section across the dashboard refresh so
                    // it is not wiped/flashed on every refresh tick.
                    const evContainer = $(`engine-events-${processName}`);
                    const savedEventsHtml = evContainer ? evContainer.innerHTML : null;
                    const savedMode = win.eventsMode || 'runs';
                    renderEngineDashboard(data, processName, win);
                    win.eventsMode = savedMode;
                    if (savedEventsHtml !== null) {
                        const restored = $(`engine-events-${processName}`);
                        if (restored) restored.innerHTML = savedEventsHtml;
                    }
                }
            }
        } catch (e) {
            console.error("Engine refresh error:", e);
        }
        const delay = (engine && engine.state === "ENGINE_RUNNING") ? 1000 : REFRESH_INTERVAL;
        win.refreshTimer = setTimeout(doRefresh, delay);
    }
    doRefresh();
}

function renderEngineDashboard(data, processName, win) {
    const body = win.body;
    if (!data.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(data.error || "Error")}</div>`;
        t.translateAllElements();
        return;
    }
    const engines = data.engines || [];
    if (engines.length === 0) {
        body.innerHTML = '<div class="empty" data-i18n="engine.no_engines">No engines found.</div>';
        t.translateAllElements();
        return;
    }
    const engine = engines.find(e => e.process === processName);
    if (!engine) {
        body.innerHTML = '<div class="empty" data-i18n="engine.no_engines">No engines found.</div>';
        t.translateAllElements();
        return;
    }
    const params = engine.parameters || {};
    win.headerTitle.textContent = `${escapeHtml(engine.label)} ${escapeHtml(engine.model)}`;
    const isRunning = engine.state === "ENGINE_RUNNING";
    const isOff = engine.state === "ENGINE_OFF";
    const speedPercent = isOff ? 0 : Math.min((engine.speed / (params.max_rpm || 1)) * 100, 100);
    const voltagePercent = isOff ? 0 : Math.min((engine.alternator_voltage / (params.voltage_scale || 1)) * 100, 100);
    const tempPercent = isOff ? 0 : Math.min((engine.temperature / (params.temperature_scale || 1)) * 100, 100);
    const voltageColor = isOff ? "var(--muted)" : "#55aaff";
    const tempColor = isOff ? "var(--muted)" : "#ff00ff";
    const stateSymbol = isRunning ? "▶️" : isOff ? "■" : "◆";
    const val = (v) => isOff ? "--" : fmt(v);
    // Tachometer: 270-degree arc from 7 o'clock (RPM=0) to 5 o'clock (100%),
    // with the bottom 90-degree gap neutralised in a distinct color. The green
    // arc represents the actual speed.
    const R = 45, C = 2 * Math.PI * R;        // circumference
    const ARC = C * (270 / 360);             // active 270deg arc length
    const GAP = C - ARC;                     // neutralised bottom gap
    const FILL = ARC * (speedPercent / 100);// green fill portion of the arc
    body.innerHTML = `
        <div class="engine-dashboard">
            <div class="dashboard-row">
                <div class="gauge-container">
                    <div class="gauge">
                        <svg viewBox="0 0 100 100" class="gauge-svg">
                            <circle cx="50" cy="50" r="${R}" fill="none" stroke="var(--panel-2)" stroke-width="8" stroke-dasharray="${GAP} ${ARC}" transform="rotate(45 50 50)" />
                            <circle cx="50" cy="50" r="${R}" fill="none" stroke="var(--border)" stroke-width="8" stroke-dasharray="${ARC} ${GAP}" transform="rotate(135 50 50)" />
                            <circle cx="50" cy="50" r="${R}" fill="none" stroke="var(--green)" stroke-width="8" stroke-dasharray="${FILL} ${C}" transform="rotate(135 50 50)" />
                            <text x="50" y="62" text-anchor="middle" font-size="15" fill="var(--text)">${val(engine.speed)}</text>
                            <text x="50" y="78" text-anchor="middle" font-size="10" fill="var(--muted)">RPM</text>
                        </svg>
                    </div>
                </div>
                <div class="status-display">
                    <div class="status-icon" style="font-size: 3rem;">${stateSymbol}</div>
                    <div class="status-text">
                        <span class="badge ${engine.state}" data-i18n="engine.state_${engine.state.toLowerCase()}">${engine.state}</span>
                    </div>
                </div>
            </div>
            <div class="dashboard-row">
                <div class="bar-graph">
                    <div class="bar-label" data-i18n="engine.voltage">Voltage</div>
                    <div class="bar-container">
                        <div class="bar-fill" style="height: ${voltagePercent}%; background: ${voltageColor};"></div>
                    </div>
                    <div class="bar-value">${val(engine.alternator_voltage)} V</div>
                </div>
                <div class="bar-graph">
                    <div class="bar-label" data-i18n="engine.temperature">Temperature</div>
                    <div class="bar-container">
                        <div class="bar-fill" style="height: ${tempPercent}%; background: ${tempColor};"></div>
                    </div>
                    <div class="bar-value">${val(engine.temperature)} °C</div>
                </div>
                <div class="stats-box">
                    <div class="stat-row">
                        <span class="stat-label" data-i18n="engine.total_hours">Total Hours</span>
                        <span class="stat-value">${fmt(engine.total_hours)} h</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label" data-i18n="engine.last_start">Last Start</span>
                        <span class="stat-value">${engine.last_start_time ? new Date(engine.last_start_time).toLocaleString() : "N/A"}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label" data-i18n="engine.last_stop">Last Stop</span>
                        <span class="stat-value">${engine.last_stop_time ? new Date(engine.last_stop_time).toLocaleString() : "N/A"}</span>
                    </div>
                </div>
            </div>
            <div class="events-section">
                <h3 style="display:flex; align-items:center; gap:12px;">
                    <span data-i18n="engine.history">History</span>
                    <div class="events-toggle ${win.eventsMode === 'events' ? 'mode-events' : ''}" id="engine-toggle-${escapeHtml(processName)}">
                        <span class="events-toggle-thumb"></span>
                        <input type="radio" name="events-mode-${escapeHtml(processName)}" id="events-runs-${escapeHtml(processName)}" ${win.eventsMode === 'runs' ? 'checked' : ''}>
                        <label for="events-runs-${escapeHtml(processName)}" data-i18n="engine.show_runs">Runs</label>
                        <input type="radio" name="events-mode-${escapeHtml(processName)}" id="events-events-${escapeHtml(processName)}" ${win.eventsMode === 'events' ? 'checked' : ''}>
                        <label for="events-events-${escapeHtml(processName)}" data-i18n="engine.show_events">Events</label>
                    </div>
                </h3>
                <div id="engine-events-${escapeHtml(processName)}" class="engine-events-list" data-process="${processName}" data-mode="${win.eventsMode || 'runs'}"><div class="empty" data-i18n="general.loading">Loading...</div></div>
            </div>
            <div class="card-actions">
                <button class="open-btn" onclick="closeEngine('${escapeHtml(processName)}')" data-i18n="general.close">Close</button>
            </div>
        </div>
    `;
    t.translateAllElements();
    const rRuns = $(`events-runs-${processName}`);
    const rEvents = $(`events-events-${processName}`);
    if (rRuns) rRuns.addEventListener('change', () => setEngineEventsMode(processName, 'runs'));
    if (rEvents) rEvents.addEventListener('change', () => setEngineEventsMode(processName, 'events'));
}

async function setEngineEventsMode(processName, mode) {
    const win = focusWindow('engine', processName);
    if (!win) return;
    win.eventsMode = mode;
    const toggleEl = $(`engine-toggle-${processName}`);
    if (toggleEl) toggleEl.classList.toggle('mode-events', mode === 'events');
    const container = $(`engine-events-${processName}`);
    if (container) {
        container.setAttribute('data-mode', mode);
        container.innerHTML = `<div class="empty" data-i18n="general.loading">Loading...</div>`;
        t.translateAllElements();
    }
    // Get engine data from the specific process, using engine_id 0
    const data = await apiGet(`/api/engine/${encodeURIComponent(processName)}/0`);
    if (data.ok) {
        renderEngineEvents(data, processName, mode);
    }
}

function renderEngineEvents(data, processName, mode) {
    const container = $(`engine-events-${processName}`);
    if (!container) return;
    if (!data.ok) {
        container.innerHTML = `<div class="empty">${escapeHtml(data.error || "Error")}</div>`;
        t.translateAllElements();
        return;
    }
    let html = '';
    if (mode === 'runs') {
        const runs = data.runs || [];
        if (runs.length === 0) {
            container.innerHTML = '<div class="empty" data-i18n="engine.no_runs">No runs found.</div>';
            t.translateAllElements();
            return;
        }
        const runRows = runs.map(run => `
            <div class="run-row">
                <span class="run-date">${new Date(run.start_time).toLocaleString()}</span>
                <span class="run-date">${run.stop_time ? new Date(run.stop_time).toLocaleString() : "N/A"}</span>
            <span class="run-duration">${fmt(Math.round(run.duration / 60))}</span>
                <span class="run-avg">${fmt(run.average_speed)} RPM</span>
                <span class="run-max">${fmt(run.max_speed)} RPM</span>
            </div>
        `).join("");
        html = `
            <div class="runs-list">
                <div class="run-header">
                    <span class="run-date" data-i18n="engine.start_time">Start Time</span>
                    <span class="run-date" data-i18n="engine.stop_time">Stop Time</span>
                    <span class="run-duration" data-i18n="engine.duration_min">Duration (min)</span>
                    <span class="run-avg" data-i18n="engine.avg_speed">Avg Speed</span>
                    <span class="run-max" data-i18n="engine.max_speed">Max Speed</span>
                </div>
                ${runRows}
            </div>
        `;
    } else {
        const events = data.events || [];
        if (events.length === 0) {
            container.innerHTML = '<div class="empty" data-i18n="engine.no_events">No events found.</div>';
            t.translateAllElements();
            return;
        }
        const eventRows = events.map(evt => `
            <div class="event-row">
                <span class="event-time">${new Date(evt.timestamp).toLocaleString()}</span>
                <span class="event-hours">${fmt(evt.total_hours)} h</span>
                <span class="event-from">${fmt(evt.previous_state)}</span>
                <span class="event-to">${fmt(evt.current_state)}</span>
            </div>
        `).join("");
        html = `
            <div class="events-list">
                <div class="event-header">
                    <span class="event-time" data-i18n="engine.time">Time</span>
                    <span class="event-hours" data-i18n="engine.total_hours">Total Hours</span>
                    <span class="event-from" data-i18n="engine.from_state">From</span>
                    <span class="event-to" data-i18n="engine.to_state">To</span>
                </div>
                ${eventRows}
            </div>
        `;
    }
    container.innerHTML = html;
    t.translateAllElements();
}

function closeEngine(processName) {
    closeWindow(windowKey('engine', processName));
}

// --- MPPT (solar charge controller) view -----------------------------
