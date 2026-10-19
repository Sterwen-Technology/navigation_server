import {
  $, state
} from '../config.js';
import {
  apiGet
} from '../api.js';
import {
  escapeHtml
} from '../common.js';
import {
  translateAllElements
} from '../i18n.js';
import {
  t
} from '../translations-bridge.js';

// Dual-scale power display constants
// High power mode: full scale = 100% of capacity
// Low power mode: full scale = 20% of capacity (better precision for small values)
// Switch threshold: if |value| > 10% of capacity -> High power, else Low power
const HIGH_POWER_THRESHOLD = 0.10;  // 10%
const LOW_POWER_SCALE = 0.20;        // 20% of capacity


export { createEmsBar };
export { createEmsCenteredBar };
export { emsFmt };
export { fetchEmsData };
export { getEnergySourceTypeName };
export { getVeErrorName };
export { getVeMpptName };
export { getVeOffReasonName };
export { getVeStateName };
export { refreshEms };
export { renderEmsDashboard };
export { renderEmsTrend };
export { showPage };
export { startEmsRefresh };
export { stopEmsRefresh };

    // --- Energy Management System (EMS) --------------------------------
    state.emsAutoRefreshTimer = null;
    const EMS_REFRESH_INTERVAL = 10000; // 10 seconds - reduced frequency since KeepAlive monitors every 2s
    state.emsAvailable = false; // Track EMS availability

    // Show either services or ems page
    function showPage(page) {
// If EMS is requested but not available, fallback to services
if (page === "ems" && !state.emsAvailable) {
    page = "services";
}

// Update nav button states
const servicesBtn = $("nav-services");
const emsBtn = $("nav-ems");
if (servicesBtn) {
    servicesBtn.classList.remove("active");
    if (page === "services") servicesBtn.classList.add("active");
}
if (emsBtn) {
    emsBtn.classList.remove("active");
    if (page === "ems") emsBtn.classList.add("active");
}

// Show/hide pages
const servicesPage = $("services-page");
const emsPage = $("ems-page");
if (servicesPage) {
    servicesPage.classList.remove("active");
    if (page === "services") servicesPage.classList.add("active");
}
if (emsPage) {
    emsPage.classList.remove("active");
    if (page === "ems") emsPage.classList.add("active");
}

// Start/stop EMS auto-refresh
if (page === "ems") {
    startEmsRefresh();
} else {
    stopEmsRefresh();
}
    }

    function stopEmsRefresh() {
if (state.emsAutoRefreshTimer) {
    clearTimeout(state.emsAutoRefreshTimer);
    state.emsAutoRefreshTimer = null;
}
    }



    // Helper function to calculate dynamic scale max for power/current values
    // Uses dual-scale approach: High power (100% scale) or Low power (20% scale)
    function getPowerScaleMax(value, referenceMax) {
        const absValue = Math.abs(value);
        const threshold = referenceMax * HIGH_POWER_THRESHOLD;
        return absValue > threshold ? referenceMax : referenceMax * LOW_POWER_SCALE;
    }

    // Map EnergySource enum values to human-readable type names
    const energySourceTypeNames = {
0: "Battery",
1: "Solar",
2: "Alternator",
3: "AC Charger",
4: "DC-DC Charger",
5: "Windmill",
6: "Hydro Generator",
7: "AC Generator",
8: "AC-DC Converter"
    };

    // Map VE_state enum values to human-readable names
    const veStateNames = {
0: "Off",
1: "Low Power",
2: "Fault",
3: "Bulk",
4: "Absorption",
5: "Float",
6: "Storage",
7: "Equalize",
9: "Inverting",
11: "Power Supply",
245: "Starting Up",
246: "Repeated Absorption",
247: "Auto Equalize",
248: "Battery Safe",
252: "External Control"
    };

    // Map VE_Error enum values to human-readable names
    const veErrorNames = {
0: "No Error",
2: "Battery Voltage Too High",
17: "Charger Temperature Too High",
18: "Charger Over Current",
19: "Charger Current Reversed",
20: "Bulk Time Limit Exceeded",
21: "Current Sensor Issue",
33: "Input Voltage Too High",
34: "Input Current Too High"
    };

    // Map VE_Off_Reason enum values to human-readable names
    const veOffReasonNames = {
0: "No Reason",
1: "No Input Power",
2: "Switched Off (Switch)",
4: "Switched Off (Register)",
8: "Remote Input",
0x10: "Protection Active",
0x20: "PayGo",
0x40: "BMS",
0x80: "Engine Shutdown Detection",
0x81: "Input voltage low",
0x100: "Analyzing Input Voltage"
    };

    // Map VE_MPPT enum values to human-readable names
    const veMpptNames = {
0: "MPPT Off",
1: "Limited",
2: "Active"
    };

    // Format value with unit
    function emsFmt(value, unit = "") {
if (value === 0 || value === null || value === undefined) return "--";
if (typeof value === "number") {
    if (unit === "W" || unit === "Wh") {
        return value.toFixed(0) + " " + unit;
    }
    if (unit === "A" || unit === "V") {
        return value.toFixed(1) + " " + unit;
    }
    if (unit === "%") {
        return value.toFixed(1) + " " + unit;
    }
    return value.toFixed(2);
}
return escapeHtml(value);
    }

    // Energy source type name from enum value
    function getEnergySourceTypeName(typeValue) {
return energySourceTypeNames[typeValue] || ("Type " + typeValue);
    }

    // VE_State name from enum value
    function getVeStateName(stateValue) {
return veStateNames[stateValue] || ("State " + stateValue);
    }

    // VE_Error name from enum value
    function getVeErrorName(errorValue) {
return veErrorNames[errorValue] || ("Error " + errorValue);
    }

    // VE_Off_Reason name from enum value
    function getVeOffReasonName(reasonValue) {
return veOffReasonNames[reasonValue] || ("Reason " + reasonValue);
    }

    // VE_MPPT name from enum value
    function getVeMpptName(mpptValue) {
return veMpptNames[mpptValue] || ("MPPT " + mpptValue);
    }

    // Render EMS dashboard
    function renderEmsDashboard(data) {
const dashboard = $("ems-dashboard");
if (!dashboard) return;

// Handle missing or invalid data gracefully
if (!data) {
    dashboard.innerHTML = '<div class="empty" data-i18n="ems.loading">Loading Energy Management System data...</div>';
    t.translateAllElements();
    return;
}

// Extract data with defaults
const batteries = data.batteries || [];
const sources = data.sources || [];

// Filter to get only instance 0 for single instance assumption
const battery = batteries.find(b => b.instance === 0) || batteries[0] || {};
const batteryData = battery.battery_data || {};

// Build the dashboard HTML
let html = '';

// Top row: Energy Controller Data (left) and Battery Data (right)
html += '<div class="ems-top">';

// Helper function to extract numeric value from either object or primitive
function getValue(objOrVal) {
    if (objOrVal && typeof objOrVal === 'object' && objOrVal.parsedValue !== undefined) {
        return objOrVal.parsedValue || 0;
    }
    return objOrVal || 0;
}

// Left box: Energy Controller Data (excluding sources_data and batteries_data)
// Determine scale mode for Energy Controller box (use production power as indicator)
const productionPower = getValue(data.production_power);
const totalPowerHigh = getValue(data.total_power_high) || 1000.0;
const totalPowerLow = getValue(data.total_power_low) || 200.0;
// total_power_low is the threshold to switch from low to high power
const isHighPowerEms = Math.abs(productionPower) > totalPowerLow;
const emsScaleTooltip = isHighPowerEms ? 'Power Scale: High' : 'Power Scale: Low';
const emsScaleIcon = isHighPowerEms ? '⚡' : '◎';
const emsScaleClass = isHighPowerEms ? 'power-scale-icon high' : 'power-scale-icon low';

html += '<div class="ems-box">';
html += `<h2><span data-i18n="ems.controller_title">Energy Controller</span><span class="${emsScaleClass}" title="${emsScaleTooltip}">${emsScaleIcon}</span></h2>`;
html += '<div class="ems-bars">';

// Main voltage
html += createEmsBar(
    t.t("ems.main_voltage"),
    getValue(data.main_voltage),
    "V",
    "#0000ff",
    0,
    getValue(data.maximum_main_voltage) || 30
);

// Auxiliary voltage
html += createEmsBar(
    t.t("ems.auxiliary_voltage"),
    getValue(data.auxiliary_voltage),
    "V",
    "#55aaff",
    0,
    getValue(data.maximum_main_voltage) || 30
);

// Production power - dual scale using parameters from EnergyController
const productionMax = Math.abs(productionPower) > totalPowerLow ? totalPowerHigh : totalPowerLow;
html += createEmsBar(
    t.t("ems.production_power"),
    productionPower,
    "W",
    "#ff9900",
    0,
    productionMax
);

// Consumption power - dual scale using parameters from EnergyController
const consumptionPower = getValue(data.consumption_power);
const consumptionMax = Math.abs(consumptionPower) > totalPowerLow ? totalPowerHigh : totalPowerLow;
html += createEmsBar(
    t.t("ems.consumption_power"),
    consumptionPower,
    "W",
    "#ff9900",
    0,
    consumptionMax
);

// Energy stock - using total_energy_capacity from EnergyController
const energyStockValue = getValue(data.energy_stock);
const totalEnergyCapacity = getValue(data.total_energy_capacity) || Math.max(energyStockValue * 1.5, 1000);
html += createEmsBar(
    t.t("ems.energy_stock"),
    energyStockValue,
    "Wh",
    "#9900ff",
    0,
    totalEnergyCapacity
);

// Battery balance - dual scale using parameters from EnergyController
const batteryBalance = getValue(data.battery_balance);
const batteryBalanceMax = Math.abs(batteryBalance) > totalPowerLow ? totalPowerHigh : totalPowerLow;
html += createEmsCenteredBar(
    t.t("ems.battery_balance"),
    batteryBalance,
    "W",
    "#ff9900",
    batteryBalanceMax
);

html += '</div></div>';

// Right box: Battery Data
// Determine scale mode for Battery box (use battery current as indicator)
const batteryCurrent = getValue(batteryData.current);
const highPowerScaleAmp = getValue(battery.high_power_scale_amp) || 50.0;
const lowPowerScaleAmp = getValue(battery.low_power_scale_amp) || 10.0;
// low_power_scale_amp is the threshold to switch from low to high power
const isHighPowerBattery = Math.abs(batteryCurrent) > lowPowerScaleAmp;
const batteryScaleTooltip = isHighPowerBattery ? 'Power Scale: High' : 'Power Scale: Low';
const batteryScaleIcon = isHighPowerBattery ? '⚡' : '◎';
const batteryScaleClass = isHighPowerBattery ? 'power-scale-icon high' : 'power-scale-icon low';

html += '<div class="ems-box">';
html += `<h2><span data-i18n="ems.battery_title">Battery</span><span class="${batteryScaleClass}" title="${batteryScaleTooltip}">${batteryScaleIcon}</span></h2>`;
html += '<div class="ems-bars">';

// Battery current (centered at 0) - dual scale using battery parameters
const batteryCurrentMax = Math.abs(batteryCurrent) > lowPowerScaleAmp ? highPowerScaleAmp : lowPowerScaleAmp;
html += createEmsCenteredBar(
    t.t("ems.battery_current"),
    batteryCurrent,
    "A",
    "#ff00ff",
    batteryCurrentMax
);

// State of charge - FIXED SCALE (not dual-scale)
const soc = getValue(batteryData.state_of_charge);
html += createEmsBar(
    t.t("ems.state_of_charge"),
    soc,
    "%",
    "#ffff00",
    0,
    100
);

// Battery power (centered at 0) - dual scale using battery parameters
const batteryPower = getValue(batteryData.power);
// Calculate power scales from current scales and nominal voltage
// If we don't have nominal_voltage, use reasonable defaults
const highPowerScaleWatt = (getValue(battery.high_power_scale_amp) || 50.0) * (getValue(battery.nominal_voltage) || 12.0);
const lowPowerScaleWatt = (getValue(battery.low_power_scale_amp) || 10.0) * (getValue(battery.nominal_voltage) || 12.0);
const batteryPowerMax = Math.abs(batteryPower) > lowPowerScaleWatt ? highPowerScaleWatt : lowPowerScaleWatt;
html += createEmsCenteredBar(
    t.t("ems.battery_power"),
    batteryPower,
    "W",
    "#ff9900",
    batteryPowerMax
);

// Battery energy
const batteryEnergy = getValue(batteryData.energy);
const batterySoc = getValue(batteryData.state_of_charge);
// Calculate max energy based on current energy and SOC: max_energy = current_energy / (soc/100)
const maxEnergy = batterySoc > 0 ? batteryEnergy / (batterySoc / 100.0) : 10000;
html += createEmsBar(
    t.t("ems.battery_energy"),
    batteryEnergy,
    "Wh",
    "#9900ff",
    0,
    maxEnergy
);

// Battery trend
if (battery.trend && battery.trend.samples && battery.trend.samples.length > 0) {
    html += '</div>';
    html += '<div class="ems-trend">';
    html += '<div class="ems-trend-title" data-i18n="ems.battery_trend">Battery Trend</div>';
    html += '<div class="ems-trend-canvas" id="ems-battery-trend"></div>';
    html += '</div>';
}
html += '</div></div>';

// Energy source rows
html += '<div class="ems-sources">';

if (sources.length === 0) {
    html += '<div class="empty" data-i18n="ems.no_sources">No energy sources.</div>';
} else {
    for (const source of sources) {
        const sourceData = source.source_data || {};
        const instance = source.instance_id || source.instance || 0;
        const label = source.label || ("Source " + instance);
        const type = source.type || 0;
        const typeName = getEnergySourceTypeName(type);
        
        // For single instance, only show instance 0
        if (instance !== 0) continue;

        const current = getValue(sourceData.current);
        const power = getValue(sourceData.power);
        const communicationOk = sourceData.communication_ok !== undefined ? sourceData.communication_ok : true;
        const deviceOn = sourceData.device_on !== undefined ? sourceData.device_on : true;

        html += '<div class="ems-source-row">';
        html += '<div class="ems-source-header">';
        html += '<span class="ems-source-title">' + escapeHtml(label) + '</span>';
        html += '<span class="ems-source-type">' + escapeHtml(typeName) + '</span>';
        html += '<span class="ems-source-state">';
        if (!communicationOk) {
            html += '<span class="ems-source-state-indicator grey"></span>';
            html += '<span>' + t.t("ems.no_communication") + '</span>';
        } else {
            html += '<span class="ems-source-state-indicator ' + (deviceOn ? '' : 'off') + '"></span>';
            html += '<span>' + (deviceOn ? t.t("ems.on") : t.t("ems.off")) + '</span>';
        }
        html += '</span>';
        html += '</div>';
        html += '<div class="ems-source-body">';
        // Bars container - takes 1/3 width
        html += '<div class="ems-source-bars">';
        // Source current - dual scale using fixed thresholds
        const sourceHighPowerScaleAmp = 50.0;   // Default high power scale (A)
        const sourceLowPowerScaleAmp = 10.0;    // Default low power threshold (A)
        const sourceCurrentMax = Math.abs(current) > sourceLowPowerScaleAmp ? sourceHighPowerScaleAmp : sourceLowPowerScaleAmp;
        html += createEmsBar(t.t("ems.current"), Math.abs(current), "A", "#ff00ff", 0, sourceCurrentMax);
        // Source power - dual scale using fixed thresholds
        const sourceHighPowerScaleWatt = 500.0;  // Default high power scale (W)
        const sourceLowPowerScaleWatt = 100.0;   // Default low power threshold (W)
        const sourcePowerMax = Math.abs(power) > sourceLowPowerScaleWatt ? sourceHighPowerScaleWatt : sourceLowPowerScaleWatt;
        html += createEmsBar(t.t("ems.power"), Math.abs(power), "W", "#ff9900", 0, sourcePowerMax);
        html += '</div>';
        
        // Trend container - takes 2/3 width
        html += '<div class="ems-source-trend-container">';
        if (source.trend && source.trend.samples && source.trend.samples.length > 0) {
            html += '<div class="ems-trend">';
            html += '<div class="ems-trend-title" data-i18n="ems.source_trend">Trend</div>';
            html += '<div class="ems-trend-canvas" id="ems-source-trend-' + instance + '"></div>';
            html += '</div>';
        }
        html += '</div>';
        html += '</div></div>';
    }
}

html += '</div>';

dashboard.innerHTML = html;
t.translateAllElements();

// Render trends if data is available
if (battery.trend && battery.trend.samples && battery.trend.samples.length > 0) {
    renderEmsTrend(battery.trend, "ems-battery-trend", "state_of_charge");
}
for (const source of sources) {
    const instance = source.instance_id || source.instance || 0;
    if (instance !== 0) continue;
    if (source.trend && source.trend.samples && source.trend.samples.length > 0) {
        renderEmsTrend(source.trend, "ems-source-trend-" + instance, "power");
    }
}
    }

    function createEmsBar(label, value, unit, color, minVal, maxVal) {
const percent = Math.min(Math.max((value - minVal) / (maxVal - minVal) * 100, 0), 100);
return `
    <div class="ems-bar">
        <div class="ems-bar-label">${escapeHtml(label)}</div>
        <div class="ems-bar-container">
            <div class="ems-bar-fill" style="height: ${percent}%; background: ${color}; bottom: 0; width: 100%;"></div>
        </div>
        <div class="ems-bar-value">${emsFmt(value, unit)}</div>
    </div>
`;
    }

    function createEmsCenteredBar(label, value, unit, color, maxAbsValue) {
const absValue = Math.abs(value);
// For centered bars, maxAbsValue represents the value at which the fill takes half the bar height (50%)
// So we multiply by 50, not 100, to keep the fill within bounds (0-50% for positive, 0-50% for negative)
const percent = Math.min((absValue / maxAbsValue) * 50, 50);
const isPositive = value >= 0;
const fillClass = isPositive ? "positive" : "negative";
const positionStyle = isPositive ? 'bottom: 50%' : 'top: 50%';

return `
    <div class="ems-bar">
        <div class="ems-bar-label">${escapeHtml(label)}</div>
        <div class="ems-bar-container">
            <div class="ems-bar-fill ${fillClass}" style="height: ${percent}%; background: ${color};"></div>
            <div class="ems-bar-zero-line"></div>
        </div>
        <div class="ems-bar-value">${emsFmt(value, unit)}</div>
    </div>
`;
    }

    function renderEmsTrend(trend, canvasId, fieldName) {
const canvas = $(canvasId);
if (!canvas) return;

const values = trend.samples || [];
if (!values.length) {
    canvas.innerHTML = '<div class="empty">No data</div>';
    return;
}

const W = 100, H = 100;
let dataValues = [];

if (fieldName === "state_of_charge") {
    dataValues = values.map(v => v.state_of_charge || 0);
} else {
    dataValues = values.map(v => {
        if (v.power !== undefined) return v.power;
        if (v.panel_power !== undefined) return v.panel_power;
        if (v.current !== undefined && v.voltage !== undefined) return v.current * v.voltage;
        return 0;
    });
}

const minVal = Math.min(...dataValues, 0);
const maxVal = Math.max(...dataValues, 1);
const range = maxVal - minVal || 1;

const n = dataValues.length;
const pts = dataValues.map((val, i) => {
    const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
    const y = H - ((val - minVal) / range) * H;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
}).join(" ");

const area = `0,${H} ${pts} ${W},${H}`;

canvas.innerHTML = `
    <svg class="ems-trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <polygon class="ems-trend-area" points="${area}"/>
        <polyline class="ems-trend-line" points="${pts}" fill="none"/>
    </svg>
    <div class="ems-trend-axis">${emsFmt(maxVal, fieldName === "state_of_charge" ? "%" : "W")} max</div>
`;
    }

    async function fetchEmsData() {
try {
    const data = await apiGet("/api/energy");
    return data;
} catch (e) {
    return { ok: false, error: e.message };
}
    }

    async function refreshEms() {
const data = await fetchEmsData();
renderEmsDashboard(data);
    }

    function startEmsRefresh() {
stopEmsRefresh();
// Integrate with KeepAlive: use the EMS_REFRESH_INTERVAL for EMS-specific refreshes
refreshEms();
state.emsAutoRefreshTimer = setTimeout(startEmsRefresh, EMS_REFRESH_INTERVAL);
    }


