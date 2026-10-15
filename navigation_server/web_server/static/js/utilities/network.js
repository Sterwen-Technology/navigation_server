import {
  $
} from '../config.js';
import {
  apiGet, apiPost
} from '../api.js';
import {
  escapeHtml
} from '../common.js';
import {
  translateAllElements
} from '../i18n.js';
import {
  toast
} from '../windows.js';
import {
  t
} from '../translations-bridge.js';

export { addConnection };
export { applyNetworkConfig };
export { closeNetwork };
export { networkInterfaceCmd };
export { openNetwork };
export { renderNetwork };
export { showAddConnection };

async function openNetwork() {
    $("network-modal").classList.add("show");
    $("network-body").innerHTML = `<div class="empty">${t.t("general.loading")}</div>`;
    try {
        const [status, configs, connections] = await Promise.all([
            apiGet("/api/network/status"),
            apiGet("/api/network/configurations"),
            apiGet("/api/network/connections"),
        ]);
        renderNetwork(status, configs, connections);
    } catch (e) {
        $("network-body").innerHTML = `<div class="empty">Erreur: ${escapeHtml(e.message)}</div>`;
    }
}

function renderNetwork(status, configs, connections) {
    const body = $("network-body");
    if (!status.ok) {
        body.innerHTML = `<div class="empty">${escapeHtml(status.error || "Erreur")}</div>`;
        t.translateAllElements();
        return;
    }
    const connectionOptions = (connections.ok ? (connections.connections || []) : [])
        .map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join("");
    
    const interfaces = (status.interfaces || []).map(iface => {
        const hasConnection = iface.connection_name && iface.connection_name !== "";
        const upDisabled = !hasConnection ? 'disabled' : '';
        const downDisabled = !hasConnection ? 'disabled' : '';
        const deleteDisabled = !hasConnection ? 'disabled' : '';
        return `
        <div class="net-interface">
            <strong>${escapeHtml(iface.name)}</strong>
            · ${escapeHtml(iface.type)}
            · ${escapeHtml(iface.state)}
            ${iface.function ? `· ${escapeHtml(iface.function)}` : ""}
            ${iface.device_name ? `· ${escapeHtml(iface.device_name)}` : ""}
            ${iface.connection_name ? `<br><span style="color:var(--muted)">Connexion: ${escapeHtml(iface.connection_name)}</span>` : ""}
            <div class="card-actions">
                <button ${upDisabled} onclick="networkInterfaceCmd('${escapeHtml(iface.name)}', '', 'up')" title="Up connection">↑ Up</button>
                <button ${downDisabled} onclick="networkInterfaceCmd('${escapeHtml(iface.name)}', '', 'down')" title="Down connection">↓ Down</button>
                <button ${deleteDisabled} onclick="networkInterfaceCmd('${escapeHtml(iface.name)}', '', 'del_connection')" title="Delete connection">✕ Delete</button>
                <select class="net-config-select" id="conn-select-${escapeHtml(iface.name)}">
                    <option value="" data-i18n="network.select_connection">Select connection...</option>
                    ${connectionOptions}
                </select>
                <button onclick="addConnection('${escapeHtml(iface.name)}')" title="Add connection">➕ Add</button>
            </div>
        </div>
    `;}).join("");

    const configOptions = (configs.ok ? (configs.configurations || []) : [])
        .map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");

    body.innerHTML = `
        <div class="console-section">
            <h3>NetworkManager: ${status.nm_running ? 'actif' : 'inactif'} ${status.status ? '· ' + escapeHtml(status.status) : ''}</h3>
            ${interfaces || '<div class="empty" data-i18n="network.no_interfaces">No interfaces.</div>'}
        </div>
        <div class="console-section">
            <h3 data-i18n="network.global_configs">Global Configurations</h3>
            <div class="card-actions">
                <select id="net-config-select" class="net-config-select">${configOptions}</select>
                <button onclick="applyNetworkConfig()">Appliquer</button>
            </div>
        </div>
    `;
    t.translateAllElements();
}

async function applyNetworkConfig() {
    const sel = $("net-config-select");
    if (!sel) return;
    const config = sel.value;
    if (!confirm(t.t("network.apply_config", {config: config}))) return;
    try {
        const r = await apiPost("/api/network/set_configuration", { config_name: config });
        toast(`Configuration ${config}: ${r.ok ? "OK" : (r.error || t.t("toast.failure"))}`, r.ok);
        if (r.ok) setTimeout(openNetwork, 1000);
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}


async function networkInterfaceCmd(interfaceName, connectionName, cmd) {
    if (!confirm(t.t("network.confirm_action", {action: cmd, interface: interfaceName}))) return;
    try {
        const r = await apiPost("/api/network/interface", { interface_name: interfaceName, connection_name: connectionName, cmd: cmd });
        toast(`${cmd} ${interfaceName}: ${r.ok ? "OK" : (r.error || t.t("toast.failure"))}`, r.ok);
        if (r.ok) setTimeout(openNetwork, 1000);
    } catch (e) {
        toast(t.t("toast.error", {error: e.message}), false);
    }
}

function addConnection(interfaceName) {
    const selectEl = $(`conn-select-${interfaceName}`);
    if (!selectEl) return;
    const connectionName = selectEl.value;
    if (!connectionName) {
        toast(t.t("network.select_connection_first"), false);
        return;
    }
    networkInterfaceCmd(interfaceName, connectionName, 'add');
}

function showAddConnection(interfaceName) {
    // This function can be used if we want to show a modal for adding connections
    // For now, we just use the inline select
}
function closeNetwork() {
    $("network-modal").classList.remove("show");
}

// --- Settings view ----------------------------------------------------
