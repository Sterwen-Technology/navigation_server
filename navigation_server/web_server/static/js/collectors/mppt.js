import {
  apiGet
} from '../api.js';
import {
  getVeErrorName, getVeMpptName, getVeStateName
} from './energy_mgmt.js';
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
  activeWindows, closeWindow, createWindow, windowKey
} from '../windows.js';
import {
  t
} from '../translations-bridge.js';

export { closeMppt };
export { closeMpptDetails };
export { mpptBar };
export { openMppt };
export { refreshMppt };
export { renderMpptDashboard };
export { renderMpptTrend };
export { startMpptRefresh };
export { stopMpptRefresh };

async function openMppt(processName) {
    const win = createWindow('mppt', processName, t.t("mppt.title") || "MPPT", (w) => {
        stopMpptRefresh(w);
    });
    win.processName = processName;
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    try {
        await refreshMppt(win);
        startMpptRefresh(win);
    } catch (e) {
        win.body.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
    }
}

function stopMpptRefresh(win) {
    if (win.mpptTimer) { clearTimeout(win.mpptTimer); win.mpptTimer = null; }
}

async function refreshMppt(win) {
    const processName = win.processName;
    try {
        const data = await apiGet(`/api/mppt/${encodeURIComponent(processName)}/status`);
        renderMpptDashboard(data, processName, win);
        // When communication with the device is lost, the readings are
        // frozen: do not fetch the trend, show a no-trend notice instead.
        if (data.ok && data.communication_ok === false) {
            const c = win.body.querySelector('.mppt-trend-canvas');
            if (c) c.innerHTML = `<div class="empty">${t.t("mppt.no_trend") || "No trend (communication lost)"}</div>`;
        } else {
            // Fetch the trend separately so the dashboard renders first.
            try {
                const trend = await apiGet(`/api/mppt/${encodeURIComponent(processName)}/trend`);
                renderMpptTrend(trend, win);
            } catch (te) {
                const c = win.body.querySelector('.mppt-trend-canvas');
                if (c) c.innerHTML = `<div class="empty">${escapeHtml(te.message)}</div>`;
            }
        }
    } catch (e) {
        win.body.innerHTML = `<div class="empty">${escapeHtml(e.message)}</div>`;
    }
}

function startMpptRefresh(win) {
    stopMpptRefresh(win);
    const processName = win.processName;
    async function tick() {
        if (activeWindows.get(windowKey('mppt', processName)) !== win) return;
        await refreshMppt(win);
        win.mpptTimer = setTimeout(tick, REFRESH_INTERVAL);
    }
    win.mpptTimer = setTimeout(tick, REFRESH_INTERVAL);
}

// A vertical bargraph (0 at the bottom). value/clamp against max.
// A null value (communication lost) renders an empty bar and '--'.
// fillClass selects the bar color scheme.
function mpptBar(label, value, max, unit, fillClass) {
    const fc = fillClass || 'mppt-fill-voltage';
    if (value === null || value === undefined) {
        return `<div class="mppt-bar">
            <div class="mppt-bar-track"></div>
            <div class="mppt-bar-label">${label}</div>
            <div class="mppt-bar-value">-- ${unit}</div>
        </div>`;
    }
    const v = Number(value) || 0;
    const m = Number(max) || 0;
    const pct = m > 0 ? Math.max(0, Math.min(100, (v / m) * 100)) : 0;
    return `<div class="mppt-bar">
        <div class="mppt-bar-track">
            <div class="mppt-bar-fill ${fc}" style="height:${pct}%"></div>
        </div>
        <div class="mppt-bar-label">${label}</div>
        <div class="mppt-bar-value">${fmt(Math.round(v * 100) / 100)} ${unit}</div>
    </div>`;
}

function renderMpptDashboard(data, processName, win) {
    const body = win.body;
    if (!data.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(data.error || "Error")}</div>`;
        t.translateAllElements();
        return;
    }
    const p = data.parameters || {};
    const o = data.output || {};
    // Bargraph maxima come from the device parameters; fall back to
    // sensible defaults when a parameter is absent.
    const maxPV = p.panel_max_voltage || 100;
    const maxV = p.max_voltage || 15;
    const maxI = (p.panel_max_power && maxV) ? p.panel_max_power / maxV : 50;
    const maxP = p.panel_max_power || 400;
    // window title carries the device identity: prefer the
    // device label, then the model, then the product id.
    const devTitle = data.device_label || data.device_model || data.product_id || processName;
    win.headerTitle.textContent = `${t.t("mppt.title") || "MPPT"} \u2014 ${escapeHtml(devTitle)}`;
    const comLost = data.communication_ok === false;
    const info = `
        <div class="mppt-info">
            ${comLost ? `<div class="mppt-com-lost" data-i18n="mppt.com_lost">Communication lost</div>` : ""}
            ${data.device_label ? `<div class="row"><span class="k" data-i18n="mppt.device_label">Label</span><span class="v">${escapeHtml(data.device_label)}</span></div>` : ""}
            ${data.device_model ? `<div class="row"><span class="k" data-i18n="mppt.device_model">Model</span><span class="v">${escapeHtml(data.device_model)}</span></div>` : ""}
            <div class="row"><span class="k" data-i18n="mppt.error">Error</span><span class="v">${escapeHtml(getVeErrorName(data.error))}</span></div>
            <div class="row"><span class="k" data-i18n="mppt.state">State</span><span class="v">${escapeHtml(getVeStateName(data.state))}</span></div>
            <div class="row"><span class="k" data-i18n="mppt.mppt_state">MPPT</span><span class="v">${escapeHtml(getVeMpptName(data.mppt_state))}</span></div>
            <div class="row"><span class="k" data-i18n="mppt.day_max_power">Day max power</span><span class="v">${fmt(data.day_max_power)} W</span></div>
            <div class="row"><span class="k" data-i18n="mppt.day_power">Day energy</span><span class="v">${fmt(data.day_power)} Wh</span></div>
            <div class="row"><button class="open-btn compact" id="mppt-details-${escapeHtml(processName)}" data-i18n="mppt.details">Details</button></div>
        </div>
    `;
    // panel_voltage is green when it exceeds the output voltage by
    // more than 5 V (panel producing), otherwise dark orange.
    const pvClass = (o.panel_voltage != null && o.voltage != null && Number(o.panel_voltage) > Number(o.voltage) + 5)
        ? 'mppt-fill-panel-ok' : 'mppt-fill-panel-low';
    const bars = `
        <div class="mppt-bars">
            ${mpptBar(t.t("mppt.panel_voltage"), o.panel_voltage, maxPV, "V", pvClass)}
            ${mpptBar(t.t("mppt.voltage"), o.voltage, maxV, "V", "mppt-fill-voltage")}
            ${mpptBar(t.t("mppt.current"), o.current, maxI, "A", "mppt-fill-current")}
            ${mpptBar(t.t("mppt.panel_power"), o.panel_power, maxP, "W", "mppt-fill-power")}
        </div>
    `;
    body.innerHTML = `
        <div class="mppt-dashboard">
            <div class="mppt-top">${info}${bars}</div>
            <div class="mppt-trend">
                <div class="mppt-trend-title" data-i18n="mppt.trend">Power trend</div>
                <div class="mppt-trend-canvas"><div class="empty">${t.t("general.loading")}</div></div>
            </div>
            <div id="mppt-details-modal-${escapeHtml(processName)}" class="modal">
                <div class="modal-content" style="max-width:420px">
                    <div class="modal-header">
                        <h2 data-i18n="mppt.details">Device details</h2>
                        <button class="modal-close" onclick="closeMpptDetails('${escapeHtml(processName)}')" title="Close">&times;</button>
                    </div>
                    <div class="mppt-info">
                        <div class="row"><span class="k" data-i18n="mppt.product">Product</span><span class="v">${fmt(data.product_id)}</span></div>
                        <div class="row"><span class="k" data-i18n="mppt.firmware">Firmware</span><span class="v">${fmt(data.firmware)}</span></div>
                        <div class="row"><span class="k" data-i18n="mppt.serial">Serial</span><span class="v">${fmt(data.serial)}</span></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    const detailsBtn = body.querySelector('#mppt-details-' + CSS.escape(processName));
    if (detailsBtn) detailsBtn.addEventListener('click', () => {
        const m = body.querySelector('#mppt-details-modal-' + CSS.escape(processName));
        if (m) m.classList.add('show');
    });
    t.translateAllElements();
}

function renderMpptTrend(trend, win) {
    const canvas = win.body.querySelector('.mppt-trend-canvas');
    if (!canvas) return;
    if (!trend.ok) {
        canvas.innerHTML = `<div class="empty">${escapeHtml(trend.error || "Error")}</div>`;
        return;
    }
    const values = trend.values || [];
    if (!values.length) {
        canvas.innerHTML = `<div class="empty" data-i18n="mppt.no_trend">No trend data</div>`;
        t.translateAllElements();
        return;
    }
    const W = 100, H = 100;
    const powers = values.map(v => Number(v.panel_power) || 0);
    const maxP = Math.max(...powers, 1);
    const n = values.length;
    // Polyline in a 100x100 viewBox; panel_power on Y (0 at bottom).
    const pts = powers.map((pwr, i) => {
        const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
        const y = H - (pwr / maxP) * H;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    // Area fill (yellow below) + line (blue above).
    const area = `0,${H} ${pts} ${W},${H}`;
    canvas.innerHTML = `
        <svg class="mppt-trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
            <polygon class="mppt-trend-area" points="${area}"/>
            <polyline class="mppt-trend-line" points="${pts}" fill="none"/>
        </svg>
        <div class="mppt-trend-axis">${t.t("mppt.trend_power") || "Panel power (W)"} \u00b7 ${Math.round(maxP)} W max</div>
    `;
}

function closeMppt(processName) {
    closeWindow(windowKey('mppt', processName));
}

function closeMpptDetails(processName) {
    const win = activeWindows.get(windowKey('mppt', processName));
    const m = win && win.body.querySelector('#mppt-details-modal-' + CSS.escape(processName));
    if (m) m.classList.remove('show');
}

// --- Battery Service Functions ---
