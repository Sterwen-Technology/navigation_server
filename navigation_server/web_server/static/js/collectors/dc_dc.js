import {
  apiGet
} from '../api.js';
import {
  getVeErrorName, getVeStateName
} from './energy_mgmt.js';
import {
  escapeHtml, fmt
} from '../common.js';
import {
  translateAllElements
} from '../i18n.js';
import {
  closeWindow, createWindow, windowKey
} from '../windows.js';
import {
  t
} from '../translations-bridge.js';

export { closeDcDc };
export { dcDcBar };
export { openDcDc };
export { refreshDcDc };
export { renderDcDcDashboard };
export { renderDcDcTrend };
export { startDcDcRefresh };
export { stopDcDcRefresh };

let dcDcAutoRefreshTimer = null;
const DC_DC_REFRESH_INTERVAL = 5000;

async function openDcDc(processName) {
    const win = createWindow('dc_dc', processName, t.t("dc_dc.title") || "DC-DC Charger", (w) => {
        stopDcDcRefresh(w);
    });
    win.processName = processName;
    win.element.style.width = '680px';
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    try {
        await refreshDcDc(win);
        startDcDcRefresh(win);
    } catch (e) {
        win.body.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
    }
}

function stopDcDcRefresh(win) {
    if (win.dcDcTimer) { clearTimeout(win.dcDcTimer); win.dcDcTimer = null; }
}

function startDcDcRefresh(win) {
    stopDcDcRefresh(win);
    win.dcDcTimer = setTimeout(() => {
        refreshDcDc(win);
        startDcDcRefresh(win);
    }, DC_DC_REFRESH_INTERVAL);
}

async function refreshDcDc(win) {
    const processName = win.processName;
    try {
        const data = await apiGet(`/api/dc_dc/${encodeURIComponent(processName)}/status`);
        renderDcDcDashboard(data, processName, win);
        // Fetch trend separately
        try {
            const trend = await apiGet(`/api/dc_dc/${encodeURIComponent(processName)}/trend`);
            renderDcDcTrend(trend, win);
        } catch (te) {
            const c = win.body.querySelector('.dc-dc-trend-canvas');
            if (c) c.innerHTML = `<div class="empty">${escapeHtml(te.message)}</div>`;
        }
    } catch (e) {
        win.body.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
    }
}

// DC-DC bargraph helper
function dcDcBar(label, value, max, unit, fillClass) {
    const fc = fillClass || 'dc-dc-fill-input-power';
    if (value === null || value === undefined) {
        return `<div class="dc-dc-bar">
            <div class="dc-dc-bar-track"></div>
            <div class="dc-dc-bar-label">${label}</div>
            <div class="dc-dc-bar-value">-- ${unit}</div>
        </div>`;
    }
    const v = Number(value) || 0;
    const m = Number(max) || 0;
    const pct = m > 0 ? Math.max(0, Math.min(100, (v / m) * 100)) : 0;
    const displayValue = v.toFixed(v % 1 === 0 ? 0 : 1);
    return `<div class="dc-dc-bar">
        <div class="dc-dc-bar-track">
            <div class="dc-dc-bar-fill ${fc}" style="height:${pct}%"></div>
        </div>
        <div class="dc-dc-bar-label">${label}</div>
        <div class="dc-dc-bar-value">${displayValue} ${unit}</div>
    </div>`;
}

function renderDcDcTrend(trend, win) {
    const canvas = win.body.querySelector('.dc-dc-trend-canvas');
    if (!canvas) return;
    if (!trend.ok) {
        canvas.innerHTML = `<div class="empty">${escapeHtml(trend.error || "Error")}</div>`;
        return;
    }
    const values = trend.samples || [];
    if (!values.length) {
        canvas.innerHTML = `<div class="empty" data-i18n="general.loading">Loading...</div>`;
        t.translateAllElements();
        return;
    }
    const W = 100, H = 100;
    // DC-DC trend uses output_power
    const powerValues = values.map(v => Number(v.output_power || 0));
    const maxAbs = Math.max(...powerValues.map(Math.abs), 1); // Maximum absolute value
    const n = values.length;
    const pts = powerValues.map((val, i) => {
        const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
        const y = H - ((val - Math.min(...powerValues, 0)) / (Math.max(...powerValues, 0) - Math.min(...powerValues, 0) || 1)) * H;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    const areaPts = [`0,${H}`].concat(pts.split(' ')).concat([`${W},${H}`]).join(" ");
    const maxVal = Math.max(...powerValues, 0);
    const minVal = Math.min(...powerValues, 0);
    canvas.innerHTML = `
        <svg class="dc-dc-trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
            <polygon class="dc-dc-trend-area" points="${areaPts}"/>
            <polyline class="dc-dc-trend-line" points="${pts}" fill="none"/>
        </svg>
        <div class="dc-dc-trend-axis">${fmt(maxVal)} W max, ${fmt(minVal)} W min</div>
    `;
}

function renderDcDcDashboard(data, processName, win) {
    const body = win.body;
    if (!data.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(data.error || "Error")}</div>`;
        t.translateAllElements();
        return;
    }
    
    const label = data.device_label || processName;
    const deviceModel = data.model || "Unknown";
    const inputVoltage = data.input_voltage || 0;
    const inputCurrent = data.input_current || 0;
    const inputPower = data.input_power || 0;
    const outputVoltage = data.output_voltage || 0;
    const outputCurrent = data.output_current || 0;
    const outputPower = data.output_power || 0;
    const veState = data.state || 0;
    const error = data.error || 0;
    
    win.headerTitle.textContent = `${t.t("dc_dc.title") || "DC-DC"} \u2014 ${escapeHtml(label)}`;
    
    // Calculate max values for bars
    const maxInputVoltage = 50;  // Reasonable default for input voltage
    const maxOutputVoltage = 50; // Reasonable default for output voltage
    const maxCurrent = 50;        // Reasonable default for current
    const maxPower = Math.max(inputPower, outputPower, 1000);
    
    const info = `
        <div class="dc-dc-info">
            ${data.device_label ? `<div class="row"><span class="k" data-i18n="dc_dc.device_label">Label</span><span class="v">${escapeHtml(data.device_label)}</span></div>` : ""}
            ${data.model ? `<div class="row"><span class="k" data-i18n="dc_dc.model">Model</span><span class="v">${escapeHtml(data.model)}</span></div>` : ""}
            <div class="row"><span class="k" data-i18n="dc_dc.state">State</span><span class="v">${escapeHtml(getVeStateName(veState))}</span></div>
            <div class="row"><span class="k" data-i18n="dc_dc.error">Error</span><span class="v">${escapeHtml(getVeErrorName(error))}</span></div>
        </div>
    `;
    
    const bars = `
        <div class="dc-dc-bars">
            ${dcDcBar(t.t("dc_dc.input_voltage"), inputVoltage, maxInputVoltage, "V", "dc-dc-fill-input-voltage")}
            ${dcDcBar(t.t("dc_dc.input_current"), inputCurrent, maxCurrent, "A", "dc-dc-fill-input-current")}
            ${dcDcBar(t.t("dc_dc.input_power"), inputPower, maxPower, "W", "dc-dc-fill-input-power")}
            ${dcDcBar(t.t("dc_dc.output_voltage"), outputVoltage, maxOutputVoltage, "V", "dc-dc-fill-output-voltage")}
            ${dcDcBar(t.t("dc_dc.output_current"), outputCurrent, maxCurrent, "A", "dc-dc-fill-output-current")}
            ${dcDcBar(t.t("dc_dc.output_power"), outputPower, maxPower, "W", "dc-dc-fill-output-power")}
        </div>
    `;
    
    body.innerHTML = `
        <div class="dc-dc-dashboard">
            <div class="dc-dc-top">${info}${bars}</div>
            <div class="dc-dc-trend">
                <div class="dc-dc-trend-title" data-i18n="dc_dc.trend">Power trend</div>
                <div class="dc-dc-trend-canvas"><div class="empty">${t.t("general.loading")}</div></div>
            </div>
        </div>
    `;
    
    t.translateAllElements();
}

function closeDcDc(processName) {
    closeWindow(windowKey('dc_dc', processName));
}

