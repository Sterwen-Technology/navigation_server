import {
  apiGet
} from '../api.js';
import {
  getVeErrorName, getVeStateName
} from '../ui/enums.js';
import {
  escapeHtml, fmt
} from '../common.js';
import {
  translateAllElements
} from '../i18n.js';
import {
  activeWindows, closeWindow, createWindow, windowKey
} from '../windows.js';
import {
  t
} from '../translations-bridge.js';

export { batteryBar };
export { closeBattery };
export { closeBatteryDetails };
export { openBattery };
export { refreshBattery };
export { renderBatteryDashboard };
export { renderBatteryTrend };
export { startBatteryRefresh };
export { stopBatteryRefresh };

let batteryAutoRefreshTimer = null;
const BATTERY_REFRESH_INTERVAL = 5000;

async function openBattery(processName) {
    const win = createWindow('battery', processName, t.t("battery.title") || "Battery", (w) => {
        stopBatteryRefresh(w);
    });
    win.processName = processName;
    // Make battery window wider to accommodate labels and bars
    win.element.style.width = '680px';
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    try {
        await refreshBattery(win);
        startBatteryRefresh(win);
    } catch (e) {
        win.body.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
    }
}

function stopBatteryRefresh(win) {
    if (win.batteryTimer) { clearTimeout(win.batteryTimer); win.batteryTimer = null; }
}

function startBatteryRefresh(win) {
    stopBatteryRefresh(win);
    win.batteryTimer = setTimeout(() => {
        refreshBattery(win);
        startBatteryRefresh(win);
    }, BATTERY_REFRESH_INTERVAL);
}

async function refreshBattery(win) {
    const processName = win.processName;
    try {
        const data = await apiGet(`/api/battery/${encodeURIComponent(processName)}/status`);
        renderBatteryDashboard(data, processName, win);
        // Fetch trend separately
        try {
            const trend = await apiGet(`/api/battery/${encodeURIComponent(processName)}/trend`);
            renderBatteryTrend(trend, win);
        } catch (te) {
            const c = win.body.querySelector('.battery-trend-canvas');
            if (c) c.innerHTML = `<div class="empty">${escapeHtml(te.message)}</div>`;
        }
    } catch (e) {
        win.body.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
    }
}

// A vertical bargraph for battery with optional zero center.
// For positive/negative values, the fill starts from the middle (50%)
function batteryBar(label, value, max, unit, fillClass, centered = false) {
    if (value === null || value === undefined) {
        return `<div class="battery-bar">
            <div class="battery-bar-track"></div>
            <div class="battery-bar-label">${label}</div>
            <div class="battery-bar-value">-- ${unit}</div>
        </div>`;
    }
    const v = Number(value) || 0;
    const m = Number(max) || 0;
    const displayValue = v.toFixed(v % 1 === 0 ? 0 : 1);
    if (centered) {
        // Centered bar: positive grows up from middle, negative grows down from middle
        const absV = Math.abs(v);
        // For centered bars, max represents the value at which the fill takes half the bar height (50%)
        // So we multiply by 50, not 100, to keep the fill within bounds (0-50% for positive, 0-50% for negative)
        const pct = m > 0 ? Math.max(0, Math.min(50, (absV / m) * 50)) : 0;
        const fillClassName = v >= 0 ? fillClass + '-pos' : fillClass + '-neg';
        const positionStyle = v >= 0 ? 'bottom: 50%' : 'top: 50%';
        return `<div class="battery-bar">
            <div class="battery-bar-track">
                <div class="battery-bar-fill ${fillClassName}" style="height:${pct}%; ${positionStyle}; left: 0; right: 0; position: absolute;"></div>
                <div class="battery-bar-zero-line"></div>
            </div>
            <div class="battery-bar-label">${label}</div>
            <div class="battery-bar-value">${displayValue} ${unit}</div>
        </div>`;
    } else {
        // Standard bar: grows up from bottom
        const pct = m > 0 ? Math.max(0, Math.min(100, (v / m) * 100)) : 0;
        return `<div class="battery-bar">
            <div class="battery-bar-track">
                <div class="battery-bar-fill ${fillClass}" style="height:${pct}%; bottom: 0;"></div>
            </div>
            <div class="battery-bar-label">${label}</div>
            <div class="battery-bar-value">${displayValue} ${unit}</div>
        </div>`;
    }
}

function renderBatteryTrend(trend, win) {
    const canvas = win.body.querySelector('.battery-trend-canvas');
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
    // Battery trend uses power instead of energy_variation
    const powerValues = values.map(v => Number(v.power || 0));
    const maxAbs = Math.max(...powerValues.map(Math.abs), 1); // Maximum absolute value
    const n = values.length;
    // Polyline in a 100x100 viewBox; power on Y with 0 at center
    // Positive values above centerline, negative values below
    const pts = powerValues.map((val, i) => {
        const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
        const y = H / 2 - (val / maxAbs) * (H / 2);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    // Area fill: create polygon from centerline to points to edge
    const centerY = H / 2;
    const areaPts = [`0,${centerY}`].concat(pts.split(' ')).concat([`${W},${centerY}`]).join(" ");
    const maxVal = Math.max(...powerValues, 0);
    const minVal = Math.min(...powerValues, 0);
    canvas.innerHTML = `
        <svg class="battery-trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
            <polygon class="battery-trend-area" points="${areaPts}"/>
            <polyline class="battery-trend-line" points="${pts}" fill="none"/>
            <line class="battery-trend-zero" x1="0" y1="${centerY}" x2="${W}" y2="${centerY}" stroke="#ffffff" stroke-width="0.5" stroke-dasharray="2,2"/>
        </svg>
        <div class="battery-trend-axis">${fmt(maxVal)} W max, ${fmt(minVal)} W min</div>
    `;
}

function renderBatteryDashboard(data, processName, win) {
    const body = win.body;
    if (!data.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(data.error || "Error")}</div>`;
        t.translateAllElements();
        return;
    }
    
    const label = data.label || processName;
    const deviceModel = data.device_model || "Unknown";
    const nominalCapacityRaw = data.nominal_capacity || 100;
    const nominalVoltageRaw = data.nominal_voltage || 12;
    const voltage = data.voltage || 0;
    const current = data.current || 0;
    const power = data.power || 0;
    const soc = data.state_of_charge || 0;
    const energy = data.energy || 0;
    
    win.headerTitle.textContent = `${t.t("battery.title") || "Battery"} \u2014 ${escapeHtml(label)}`;
    
    // Calculate max values for bars
    // Use reasonable defaults that ensure bars are visible even for small values
    const maxVoltage = nominalVoltageRaw ? nominalVoltageRaw * 1.2 : 20; // 20% above nominal - FIXED SCALE
    
    // Current and power use DUAL SCALE (high/low power modes)
    // Get power scale parameters from data or use defaults
    const highPowerScaleAmp = data.high_power_scale_amp || 50.0;
    const lowPowerScaleAmp = data.low_power_scale_amp || 10.0;
    const maxCurrent = Math.abs(current) > lowPowerScaleAmp ? highPowerScaleAmp : lowPowerScaleAmp;
    const maxPower = (Math.abs(power) > (lowPowerScaleAmp * nominalVoltageRaw)) ? 
                    (highPowerScaleAmp * nominalVoltageRaw) : (lowPowerScaleAmp * nominalVoltageRaw);
    
    const maxEnergy = energy ? energy * 1.2 : 10000; // FIXED SCALE
    const maxSoc = 100; // FIXED SCALE
    
    // Format values for display
    const nominalCapacityDisplay = `${nominalCapacityRaw.toFixed(nominalCapacityRaw % 1 === 0 ? 0 : 1)} Ah`;
    const nominalVoltageDisplay = `${nominalVoltageRaw.toFixed(nominalVoltageRaw % 1 === 0 ? 0 : 1)} V`;
    
    const info = `
        <div class="battery-info">
            ${deviceModel !== "Unknown" ? `<div class="row"><span class="k" data-i18n="battery.device_model">Model</span><span class="v">${escapeHtml(deviceModel)}</span></div>` : ""}
            <div class="row"><span class="k" data-i18n="battery.nominal_capacity">Nominal Capacity</span><span class="v">${nominalCapacityDisplay}</span></div>
            <div class="row"><span class="k" data-i18n="battery.nominal_voltage">Nominal Voltage</span><span class="v">${nominalVoltageDisplay}</span></div>
            <div class="row"><button class="open-btn compact" id="battery-details-${CSS.escape(processName)}" data-i18n="battery.details">Details</button></div>
        </div>
    `;
    
    const bars = `
        <div class="battery-bars">
            ${batteryBar(t.t("battery.voltage"), voltage, maxVoltage, "V", "battery-fill-voltage")}
            ${batteryBar(t.t("battery.current"), current, maxCurrent, "A", "battery-fill-current", true)}
            ${batteryBar(t.t("battery.power"), power, maxPower, "W", "battery-fill-power", true)}
            ${batteryBar(t.t("battery.state_of_charge"), soc, maxSoc, "%", "battery-fill-soc")}
            ${batteryBar(t.t("battery.energy"), energy, maxEnergy, "Wh", "battery-fill-energy")}
        </div>
    `;
    
    body.innerHTML = `
        <div class="battery-dashboard">
            <div class="battery-top">${info}${bars}</div>
            <div class="battery-trend">
                <div class="battery-trend-title" data-i18n="battery.trend">Power Trend</div>
                <div class="battery-trend-canvas"><div class="empty" data-i18n="general.loading">Loading...</div></div>
            </div>
            <div id="battery-details-modal-${CSS.escape(processName)}" class="modal">
                <div class="modal-content" style="max-width:420px">
                    <div class="modal-header">
                        <h2 data-i18n="battery.details">Details</h2>
                        <button class="modal-close" onclick="closeBatteryDetails('${CSS.escape(processName)}')" title="Close">&times;</button>
                    </div>
                    <div class="battery-info">
                        <div class="row"><span class="k" data-i18n="battery.label">Label</span><span class="v">${escapeHtml(label)}</span></div>
                        <div class="row"><span class="k" data-i18n="battery.device_model">Model</span><span class="v">${escapeHtml(deviceModel)}</span></div>
                        <div class="row"><span class="k" data-i18n="battery.nominal_voltage">Nominal Voltage</span><span class="v">${nominalVoltageDisplay}</span></div>
                        <div class="row"><span class="k" data-i18n="battery.nominal_capacity">Nominal Capacity</span><span class="v">${nominalCapacityDisplay}</span></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Setup details button
    const detailsBtn = body.querySelector('#battery-details-' + CSS.escape(processName));
    if (detailsBtn) {
        detailsBtn.addEventListener('click', () => {
            const m = body.querySelector('#battery-details-modal-' + CSS.escape(processName));
            if (m) m.classList.add('show');
        });
    }
    
    t.translateAllElements();
}

function closeBattery(processName) {
    closeWindow(windowKey('battery', processName));
}

function closeBatteryDetails(processName) {
    const win = activeWindows.get(windowKey('battery', processName));
    const m = win && win.body.querySelector('#battery-details-modal-' + CSS.escape(processName));
    if (m) m.classList.remove('show');
}

// --- DC-DC Charger Service Functions ---
