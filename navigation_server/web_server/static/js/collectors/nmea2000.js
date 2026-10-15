import {
  apiGet, apiPost
} from '../api.js';
import {
  REFRESH_INTERVAL, $
} from '../config.js';
import {
  escapeHtml, fmt
} from '../common.js';
import {
  translateAllElements
} from '../i18n.js';
import {
  activeWindows, closeWindow, createWindow, focusWindow, toast, windowKey
} from '../windows.js';
import {
  t
} from '../translations-bridge.js';

export { backToNmea2000List };
export { closeNmea2000 };
export { getPgnDefinitionCached };
export { nmea2000TraceCmd };
export { openNmea2000 };
export { openNmea2000Device };
export { refreshNmea2000 };
export { renderNmea2000 };
export { renderNmea2000Device };
export { stopNmea2000Refresh };

function stopNmea2000Refresh(win) {
    if (win && win.refreshTimer) {
        clearTimeout(win.refreshTimer);
        win.refreshTimer = null;
    }
}

async function openNmea2000(processName) {
    const win = createWindow('nmea2000', processName, "NMEA2000 — " + processName, (w) => {
        stopNmea2000Refresh(w);
    });
    win.processName = processName;
    win.inDeviceView = false;
    win.headerTitle.textContent = "NMEA2000 — " + processName;
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    await refreshNmea2000(win);
}

async function refreshNmea2000(win) {
    if (!win || activeWindows.get(windowKey('nmea2000', win.processName)) !== win) return;
    if (win.inDeviceView) {
        win.refreshTimer = setTimeout(() => refreshNmea2000(win), REFRESH_INTERVAL);
        return;
    }
    const processName = win.processName;
    try {
        const data = await apiGet("/api/nmea2000/" + encodeURIComponent(processName) + "/status");
        if (activeWindows.get(windowKey('nmea2000', processName)) === win && !win.inDeviceView) {
            renderNmea2000(data, processName, win);
            win.refreshTimer = setTimeout(() => refreshNmea2000(win), REFRESH_INTERVAL);
        }
    } catch (e) {
        console.error("NMEA2000 refresh error:", e);
        win.refreshTimer = setTimeout(() => refreshNmea2000(win), REFRESH_INTERVAL);
    }
}

function closeNmea2000(processName) {
    closeWindow(windowKey('nmea2000', processName));
}

function renderNmea2000(data, processName, win) {
    const body = win.body;
    if (!data.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(data.error || "NMEA2000 Error")}</div>`;
        t.translateAllElements();
        return;
    }
    const devices = data.devices || [];
    const traceBtnText = data.traces_on ? "■ Stop Trace" : "▶ Start Trace";
    const traceBtnCmd = data.traces_on ? "stop_trace" : "start_trace";
    const incomingRate = data.incoming_rate ? data.incoming_rate.toFixed(1) : "0";
    const outgoingRate = data.outgoing_rate ? data.outgoing_rate.toFixed(1) : "0";
    let html = `<div class="console-section">
        <h3>NMEA2000 Controller</h3>
        <div class="row">
            <span class="k">Channel</span><span class="v">${fmt(data.channel)}</span>
            <span class="k">Status</span><span class="v">${fmt(data.status)}</span>
        </div>
        <div class="row">
            <span class="k">Incoming</span><span class="v">${incomingRate} msg/s</span>
            <span class="k">Outgoing</span><span class="v">${outgoingRate} msg/s</span>
        </div>
        <div class="card-actions">
            <button onclick="nmea2000TraceCmd('${escapeHtml(processName)}', '${traceBtnCmd}')">${traceBtnText}</button>
        </div>
    </div>
    <div class="console-section">
        <h3>Devices (${devices.length})</h3>
        <div class="nmea2000-devices">`;
    if (devices.length === 0) {
        html += '<div class="empty" data-i18n="nmea2000.no_devices">No NMEA2000 devices.</div>';
    } else {
        for (const dev of devices) {
            const proxySymbol = dev.is_proxy ? '<span class="proxy-symbol" title="Proxy"></span>' : '';
            html += `<div class="nmea2000-device">
                <span class="dev-addr">${dev.address}</span>
                ${proxySymbol}
                <span class="dev-mfg">${fmt(dev.manufacturer_name)}</span>
                <span class="dev-prod">${fmt(dev.product_name)}</span>
                <button class="open-btn compact" onclick="openNmea2000Device('${escapeHtml(processName)}', ${dev.address})">PGN Stats</button>
            </div>`;
        }
    }
    html += '</div></div>';
    body.innerHTML = html;
}

async function openNmea2000Device(processName, deviceAddress) {
    const win = focusWindow('nmea2000', processName);
    if (!win) return;
    win.inDeviceView = true;
    win.headerTitle.textContent = "NMEA2000 — " + processName + " — Device " + deviceAddress;
    win.body.innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    try {
        const data = await apiGet("/api/nmea2000/" + encodeURIComponent(processName) + "/device/" + deviceAddress);
        if (data.ok) {
            renderNmea2000Device(data, processName, deviceAddress, win);
        } else {
            toast(data.error || "Erreur", false);
        }
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}

async function renderNmea2000Device(data, processName, deviceAddress, win) {
    const title = win.headerTitle;
    title.textContent = "NMEA2000 — " + processName + " — Device " + deviceAddress;
    const body = win.body;
    let html = `<div class="console-section">
        <h3>NMEA2000 Device</h3>
        <div class="row">
            <span class="k">Address</span><span class="v">${data.address}</span>
            <span class="k">Proxy</span><span class="v">${data.is_proxy ? 'Yes' : 'No'}</span>
        </div>
        <div class="row">
            <span class="k">Manufacturer</span><span class="v">${fmt(data.manufacturer_name)}</span>
            <span class="k">Product</span><span class="v">${fmt(data.product_name)}</span>
        </div>
    </div>`;
    // Separate stats by direction
    const inStats = (data.pgn_stats || []).filter(s => s.direction === 'in');
    const outStats = (data.pgn_stats || []).filter(s => s.direction === 'out');
    if (inStats.length > 0 || outStats.length > 0) {
        html += '<div class="console-section"><h3>PGN Statistics</h3>';
        if (inStats.length > 0) {
            html += '<div class="pgn-list"><h4>Incoming</h4><div class="pgn-items">';
            for (const stat of inStats) {
                const pgnDef = await getPgnDefinitionCached(processName, stat.pgn);
                html += `<div class="pgn-item"><span class="pgn-num">${stat.pgn}</span><span class="pgn-desc">${pgnDef || ''}</span><span class="pgn-count">${stat.count}</span></div>`;
            }
            html += '</div></div>';
        }
        if (outStats.length > 0) {
            html += '<div class="pgn-list"><h4>Outgoing</h4><div class="pgn-items">';
            for (const stat of outStats) {
                const pgnDef = await getPgnDefinitionCached(processName, stat.pgn);
                html += `<div class="pgn-item"><span class="pgn-num">${stat.pgn}</span><span class="pgn-desc">${pgnDef || ''}</span><span class="pgn-count">${stat.count}</span></div>`;
            }
            html += '</div></div>';
        }
        html += '</div>';
    }
    html += `<div class="card-actions"><button class="open-btn" onclick="backToNmea2000List('${escapeHtml(processName)}')">Back</button></div>`;
    body.innerHTML = html;

    t.translateAllElements();}

// Simple cache for PGN definitions
const pgnDefCache = new Map();
async function getPgnDefinitionCached(processName, pgn) {
    const cacheKey = processName + ":" + pgn;
    if (pgnDefCache.has(cacheKey)) {
        return pgnDefCache.get(cacheKey);
    }
    try {
        const data = await apiGet("/api/nmea2000/" + encodeURIComponent(processName) + "/pgn/" + pgn);
        if (data.ok && data.definition) {
            pgnDefCache.set(cacheKey, data.definition);
            return data.definition;
        }
    } catch (e) {
        // ignore
    }
    return null;
}

function backToNmea2000List(processName) {
    const win = focusWindow('nmea2000', processName);
    if (!win) return;
    win.inDeviceView = false;
    win.headerTitle.textContent = "NMEA2000 — " + processName;
    refreshNmea2000(win);
}

async function nmea2000TraceCmd(processName, cmd) {
    try {
        const r = await apiPost("/api/nmea2000/" + encodeURIComponent(processName) + "/trace/" + cmd, {});
        toast(cmd + ": " + (r.ok ? "OK" : (r.error || t.t("toast.failure"))), r.ok);
        if (r.ok) {
            const win = focusWindow('nmea2000', processName);
            if (win && !win.inDeviceView) setTimeout(() => refreshNmea2000(win), 800);
        }
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}


// --- Engine Dashboard ----------------------------------------------------
// Single Engine window per process; refresh interval and the
// runs/events mode are kept on the window record.
