import { autoEnabled, isRefreshing } from './config.js';
import { getRefresh, getShowPage } from './runtime.js';
import { isBackendDisconnected } from './common.js';
import { t } from './translations-bridge.js';

export { apiGet };
export { apiPost };
export { awaitLogin };
export { checkEnergyServiceAvailable };
export { checkKeepAlive };
export { handleAuthFailure };
export { hideLoginOverlay };
export { performLogin };
export { showLoginOverlay };
export { startKeepAliveMonitoring };
export { stopKeepAliveMonitoring };
export { updateConnectionStatusFromKeepAlive };
export { updateEmsVisibility };

let loginResolver = null; // resolves once a login attempt succeeds

function showLoginOverlay() {
    $("login-overlay").classList.add("show");
    const u = $("login-username");
    if (u) u.focus();
}

function hideLoginOverlay() {
    $("login-overlay").classList.remove("show");
    const err = $("login-error");
    if (err) err.textContent = "";
    if (loginResolver) {
        loginResolver();
        loginResolver = null;
    }
}

function awaitLogin() {
    return new Promise((resolve) => { loginResolver = resolve; });
}

async function performLogin(username, password) {
    const r = await fetch("/api/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
    });
    const data = await r.json().catch(() => ({}));
    return r.ok && data.ok;
}

// Intercepts 401: shows the login overlay, waits for a successful
// login, then resolves so the caller can retry the request.
async function handleAuthFailure() {
    showLoginOverlay();
    await awaitLogin();
}

async function apiGet(path) {
    try {
        let r = await fetch(path, { cache: "no-store", credentials: "include" });
        if (r.status === 401) {
            await handleAuthFailure();
            // Add a small delay to allow the browser to process the authentication cookies
            await new Promise(resolve => setTimeout(resolve, 100));
            r = await fetch(path, { cache: "no-store", credentials: "include" });
        }
        if (!r.ok) {
            // HTTP errors (404, 500, etc.) are not connection errors
            const error = new Error(`HTTP ${r.status}`);
            error.status = r.status; // Mark as HTTP error
            throw error;
        }
        return r.json();
    } catch (e) {
        // For now, only mark as connection error if it's clearly a network failure
        // This prevents false positives from API errors
        if (isBackendDisconnected(e)) {
            e.isConnectionError = true;
        }
        throw e; // Re-throw so callers can handle the error
    }
}

// KeepAlive interval for connection monitoring (shorter than full refresh)
const KEEPALIVE_INTERVAL = 2000; // 2 seconds for quick connection status checks
const FULL_REFRESH_SAFETY_INTERVAL = 30000; // 30 seconds safety net for full refresh
let keepaliveTimer = null;
let keepaliveCount = 0;
let lastSystemChanged = false;
let lastFullRefreshTime = 0;

async function checkKeepAlive() {
    const now = Date.now();
    
    // Safety net: do a full refresh periodically even if no changes detected
    // This handles cases where keep_alive might not be working properly
    if (autoEnabled && now - lastFullRefreshTime > FULL_REFRESH_SAFETY_INTERVAL) {
        lastFullRefreshTime = now;
        if (!isRefreshing) {
            getRefresh()().catch(() => {});
        }
        return;
    }
    
    try {
        const keepalive = await apiGet("/api/keepalive");
        if (keepalive.ok && keepalive.connected) {
            // Update connection status based on keepalive
            updateConnectionStatusFromKeepAlive(keepalive);
            
            // If system has changed, trigger a full refresh
            if (keepalive.system_changed && !lastSystemChanged) {
                lastSystemChanged = true;
                lastFullRefreshTime = now; // Reset the safety timer
                if (!isRefreshing && autoEnabled) {
                    getRefresh()().catch(() => {});
                }
            } else if (!keepalive.system_changed) {
                lastSystemChanged = false;
            }
            keepaliveCount++;
        } else {
            // Connection lost - update status
            updateConnectionStatusFromKeepAlive(keepalive);
        }
        return keepalive;
    } catch (e) {
        // Connection error - mark as disconnected
        const pill = $("conn-status");
        if (pill) {
            pill.className = "status-pill disconnected";
            pill.textContent = t.t("status.disconnected");
        }
        return { ok: false, connected: false, system_changed: false, error: e.message };
    }
}

function updateConnectionStatusFromKeepAlive(keepalive) {
    const pill = $("conn-status");
    if (pill) {
        if (keepalive.connected) {
            pill.className = "status-pill connected";
            pill.textContent = t.t("status.connected");
        } else {
            pill.className = "status-pill disconnected";
            pill.textContent = t.t("status.disconnected");
        }
    }
}

function startKeepAliveMonitoring() {
    stopKeepAliveMonitoring();
    lastFullRefreshTime = Date.now(); // Start the safety timer
    checkKeepAlive().then(() => {
        keepaliveTimer = setTimeout(startKeepAliveMonitoring, KEEPALIVE_INTERVAL);
    });
}

function stopKeepAliveMonitoring() {
    if (keepaliveTimer) {
        clearTimeout(keepaliveTimer);
        keepaliveTimer = null;
    }
}

async function apiPost(path, body) {
    try {
        let r = await fetch(path, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (r.status === 401) {
            await handleAuthFailure();
            r = await fetch(path, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
        }
        if (!r.ok) {
            // HTTP errors (404, 500, etc.) are not connection errors
            const error = new Error(`HTTP ${r.status}`);
            error.status = r.status; // Mark as HTTP error
            throw error;
        }
        return r.json();
    } catch (e) {
        // For now, only mark as connection error if it's clearly a network failure
        if (isBackendDisconnected(e)) {
            e.isConnectionError = true;
        }
        throw e; // Re-throw so callers can handle the error
    }
}

// Check if EnergyService is available
async function checkEnergyServiceAvailable() {
    try {
        const data = await apiGet("/api/energy_available");
        return data.available || false;
    } catch (e) {
        // Don't treat EnergyService check failures as connection errors
        // EnergyService might not be running, but backend could still be fine
        console.error("Error checking EnergyService availability:", e);
        return false;
    }
}

// Update EMS button visibility based on service availability
async function updateEmsVisibility() {
    const emsAvailable = await checkEnergyServiceAvailable();
    const emsBtn = $("nav-ems");
    const emsPage = $("ems-page");
    
    if (emsBtn) {
        emsBtn.style.display = emsAvailable ? "" : "none";
    }
    if (emsPage) {
        emsPage.style.display = emsAvailable ? "" : "none";
    }
    
    // If EMS is not available and user is trying to view EMS page, switch to services
    if (!emsAvailable && window.location.hash === "#ems") {
        getShowPage()("services");
    }
    
    return emsAvailable;
}

