import { apiGet } from '../api.js';
import { escapeHtml } from '../common.js';
import { translateAllElements } from '../i18n.js';
import { t } from '../translations-bridge.js';

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
    let emsAutoRefreshTimer = null;
    const EMS_REFRESH_INTERVAL = 10000; // 10 seconds - reduced frequency since KeepAlive monitors every 2s
    let emsAvailable = false; // Track EMS availability

    // Show either services or ems page
    function showPage(page) {
// If EMS is requested but not available, fallback to services
if (page === "ems" && !emsAvailable) {
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
if (emsAutoRefreshTimer) {
    clearTimeout(emsAutoRefreshTimer);
    emsAutoRefreshTimer = null;
}
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

// Left box: Energy Controller Data (excluding sources_data and batteries_data)
html += '<div class="ems-box">';
html += '<h2 data-i18n="ems.controller_title">Energy Controller</h2>';
html += '<div class="ems-bars">';

// Main voltage
html += createEmsBar(
    t.t("ems.main_voltage"),
    data.main_voltage || 0,
    "V",
    "#0000ff",
    0,
    data.maximum_main_voltage || 30
);

// Auxiliary voltage
html += createEmsBar(
    t.t("ems.auxiliary_voltage"),
    data.auxiliary_voltage || 0,
    "V",
    "#55aaff",
    0,
    data.maximum_main_voltage || 30
);

// Production power
html += createEmsBar(
    t.t("ems.production_power"),
    data.production_power || 0,
    "W",
    "#ff9900",
    0,
    Math.max((data.production_power || 0) * 2, 1000)
);

// Consumption power
html += createEmsBar(
    t.t("ems.consumption_power"),
    data.consumption_power || 0,
    "W",
    "#ff9900",
    0,
    Math.max((data.consumption_power || 0) * 2, 1000)
);

// Energy stock
html += createEmsBar(
    t.t("ems.energy_stock"),
    (data.energy_stock || 0) * 10,
    "Wh",
    "#9900ff",
    0,
    Math.max((data.energy_stock || 0) * 20, 10000)
);

// Battery balance
html += createEmsCenteredBar(
    t.t("ems.battery_balance"),
    data.battery_balance || 0,
    "W",
    "#ff9900",
    Math.max(Math.abs(data.battery_balance || 0) * 2, 500)
);

html += '</div></div>';

// Right box: Battery Data
html += '<div class="ems-box">';
html += '<h2 data-i18n="ems.battery_title">Battery</h2>';
html += '<div class="ems-bars">';

// Battery current (centered at 0)
const batteryCurrent = batteryData.current || 0;
html += createEmsCenteredBar(
    t.t("ems.battery_current"),
    batteryCurrent,
    "A",
    "#ff00ff",
    Math.max(Math.abs(batteryCurrent) * 2, 2)
);

// State of charge
const soc = batteryData.state_of_charge || 0;
html += createEmsBar(
    t.t("ems.state_of_charge"),
    soc,
    "%",
    "#ffff00",
    0,
    100
);

// Battery power
const batteryPower = batteryData.power || 0;
html += createEmsCenteredBar(
    t.t("ems.battery_power"),
    batteryPower,
    "W",
    "#ff9900",
    Math.max(Math.abs(batteryPower) * 2, 20)
);

// Battery energy
const batteryEnergy = batteryData.energy || 0;
html += createEmsBar(
    t.t("ems.battery_energy"),
    batteryEnergy,
    "Wh",
    "#9900ff",
    0,
    Math.max(batteryEnergy * 2, 10000)
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

        const current = sourceData.current || 0;
        const power = sourceData.power || 0;
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
        html += createEmsBar(t.t("ems.current"), Math.abs(current), "A", "#ff00ff", 0, Math.max(Math.abs(current) * 2, 50));
        html += createEmsBar(t.t("ems.power"), Math.abs(power), "W", "#ff9900", 0, Math.max(Math.abs(power) * 2, 500));
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
const percent = Math.min((absValue / maxAbsValue) * 100, 100);
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
emsAutoRefreshTimer = setTimeout(startEmsRefresh, EMS_REFRESH_INTERVAL);
    }


