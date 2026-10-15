// Point d'entree: exports window.* pour les onclick inline, bindings, init.
import {
  REFRESH_INTERVAL, autoTimer, isRefreshing, autoEnabled, showHidden,
  backendConnected, $
} from './config.js';
import { toast } from './windows.js';
import {
  apiGet, apiPost, performLogin, hideLoginOverlay, startKeepAliveMonitoring,
  stopKeepAliveMonitoring, checkEnergyServiceAvailable, updateEmsVisibility
} from './api.js';
import { retryConnection } from './common.js';
import {
  refresh, render, systemCmd, systemCmdConfirm, procCmd, toggleAuto,
  toggleHidden, openConsole, closeConsole, couplerCmd
} from './collectors/system.js';
import { openLog } from './utilities/logs.js';
import {
  openNetwork, closeNetwork, applyNetworkConfig, networkInterfaceCmd,
  addConnection, showAddConnection
} from './utilities/network.js';
import { showSettings } from './utilities/settings.js';
import {
  openNmea2000, closeNmea2000, nmea2000TraceCmd, openNmea2000Device,
  backToNmea2000List
} from './collectors/nmea2000.js';
import { openEngineData, closeEngine, setEngineEventsMode } from './collectors/engine.js';
import { openMppt, closeMppt, closeMpptDetails } from './collectors/mppt.js';
import { openBattery, closeBattery, closeBatteryDetails } from './collectors/battery.js';
import { openDcDc, closeDcDc } from './collectors/dc_dc.js';
import { showPage, startEmsRefresh } from './collectors/energy_mgmt.js';
import { initPageTranslations } from './i18n.js';
import { saveSettings } from './utilities/settings.js';
import { setRefresh, setShowPage } from './runtime.js';
import { t } from './translations-bridge.js';

// Branchement des indirections (cycles api/system et api/energy_mgmt)
setRefresh(refresh);
setShowPage(showPage);

// Exports window.* supplémentaires pour les onclick inline générés dynamiquement
window.saveSettings = saveSettings;

// --- Exports window.* pour les gestionnaires onclick inline du HTML ---
window.procCmd = procCmd;
window.systemCmd = systemCmd;
window.systemCmdConfirm = systemCmdConfirm;
window.openLog = openLog;
window.openNetwork = openNetwork;
window.closeNetwork = closeNetwork;
window.openNmea2000 = openNmea2000;
window.closeNmea2000 = closeNmea2000;
window.nmea2000TraceCmd = nmea2000TraceCmd;
window.openNmea2000Device = openNmea2000Device;
window.backToNmea2000List = backToNmea2000List;
window.applyNetworkConfig = applyNetworkConfig;
window.openConsole = openConsole;
window.closeConsole = closeConsole;
window.couplerCmd = couplerCmd;
window.networkInterfaceCmd = networkInterfaceCmd;
window.addConnection = addConnection;
window.showAddConnection = showAddConnection;
window.openEngineData = openEngineData;
window.closeEngine = closeEngine;
window.setEngineEventsMode = setEngineEventsMode;
window.openMppt = openMppt;
window.closeMppt = closeMppt;
window.closeMpptDetails = closeMpptDetails;
window.openBattery = openBattery;
window.closeBattery = closeBattery;
window.closeBatteryDetails = closeBatteryDetails;
window.openDcDc = openDcDc;
window.closeDcDc = closeDcDc;
window.showSettings = showSettings;
window.showPage = showPage;
window.toggleHidden = toggleHidden;
window.toggleAuto = toggleAuto;
window.retryConnection = retryConnection;

// --- Bindings ---
$("refresh-btn").addEventListener("click", refresh);
$("auto-refresh").addEventListener("change", toggleAuto);
$("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("login-error");
    err.textContent = "";
    const u = $("login-username").value;
    const p = $("login-password").value;
    const btn = $("login-submit");
    btn.disabled = true;
    try {
        const ok = await performLogin(u, p);
        if (ok) {
            hideLoginOverlay();
            // Reload the page to ensure authenticated state is properly loaded
            window.location.reload();
        } else {
            err.textContent = t.t("auth.invalid");
        }
    } catch (ex) {
        err.textContent = t.t("auth.error");
    } finally {
        btn.disabled = false;
    }
});
refresh();

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function() {
    initPageTranslations().then(() => {
        // Do an initial refresh to load data
        if (autoEnabled) {
            refresh().then(() => {
                // Start KeepAlive monitoring after initial data is loaded
                startKeepAliveMonitoring();
            }).catch(() => {
                // Even if initial refresh fails, start KeepAlive to monitor connection
                startKeepAliveMonitoring();
            });
        } else {
            // Auto-refresh is disabled, but still monitor connection status
            startKeepAliveMonitoring();
        }
    });
});
