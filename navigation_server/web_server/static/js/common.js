import { apiGet } from './api.js';
import { backendConnected } from './config.js';
import { toast } from './windows.js';
import { getRefresh } from './runtime.js';
import { t } from './translations-bridge.js';

export { disableAllButtons };
export { enableAllButtons };
export { escapeHtml };
export { fmt };
export { isBackendDisconnected };
export { retryConnection };
export { showConnectionLost };
export { showConnectionRestored };

function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

function fmt(v) { return v === 0 || v ? escapeHtml(v) : "—"; }

// Function to disable all buttons on the page
function disableAllButtons() {
    const allButtons = document.querySelectorAll('button');
    allButtons.forEach(button => {
        button.disabled = true;
    });
    // Also disable input elements
    const allInputs = document.querySelectorAll('input[type="checkbox"], input[type="text"], select');
    allInputs.forEach(input => {
        input.disabled = true;
    });
}

// Function to enable all buttons on the page
function enableAllButtons() {
    const allButtons = document.querySelectorAll('button');
    allButtons.forEach(button => {
        button.disabled = false;
    });
    // Also enable input elements
    const allInputs = document.querySelectorAll('input[type="checkbox"], input[type="text"], select');
    allInputs.forEach(input => {
        input.disabled = false;
    });
}

// Function to show connection lost state (network-level only)
function showConnectionLost() {
    if (!backendConnected) return; // Already in disconnected state
    
    backendConnected = false;
    disableAllButtons();
    const overlay = $("connection-lost-overlay");
    if (overlay) {
        overlay.style.display = "flex";
    }
    // Update connection status pill
    const pill = $("conn-status");
    if (pill) {
        pill.className = "status-pill disconnected";
        pill.textContent = t.t("status.disconnected");
    }
    
    // Translate the overlay message
    const messageEl = overlay ? overlay.querySelector('[data-i18n]') : null;
    if (messageEl) {
        messageEl.textContent = t.t("error.connection_lost");
    }
    
    // Also translate the retry button
    const retryBtn = overlay ? overlay.querySelector('button') : null;
    if (retryBtn) {
        retryBtn.textContent = t.t("button.retry");
    }
}

// Function to show connection restored state (network-level only)
function showConnectionRestored() {
    if (backendConnected) return; // Already connected
    
    backendConnected = true;
    enableAllButtons();
    const overlay = $("connection-lost-overlay");
    if (overlay) {
        overlay.style.display = "none";
    }
    // The pill will be updated by render() based on agent connection state
}

// Function to check if error indicates backend disconnection
function isBackendDisconnected(error) {
    // HTTP errors (404, 500, etc.) are NOT connection errors
    if (error.status) {
        return false;
    }
    
    // Check if the error indicates a network/server issue
    const errorStr = String(error).toLowerCase();
    const errorName = String(error.name || "").toLowerCase();
    
    // Only TypeError with "Failed to fetch" indicates actual network failure
    return errorName.includes("typeerror") && errorStr.includes("failed to fetch");
}

// Function to retry connection
async function retryConnection() {
    try {
        // Try to fetch the system status
        const data = await apiGet("/api/system/status");
        // If we got a successful response, the network connection is restored
        showConnectionRestored();
        // Refresh the page to get fresh data
        getRefresh()();
    } catch (e) {
        toast(t.t("toast.refresh_error", {error: e.message}), false);
    }
}

