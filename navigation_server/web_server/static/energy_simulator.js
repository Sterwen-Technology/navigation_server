/**
 * Energy Simulator - JavaScript Functions
 * Handles simulation control, configuration, and UI updates
 */

// Global state
let isRunning = false;
let statusInterval = null;
let configData = null;
let configSectionsBuilt = false;
let mpptSliderTimeout = null;

/**
 * API Helper Functions
 */
function fetchAPI(endpoint, options = {}) {
    return fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        ...options
    })
    .then(response => response.json())
    .catch(error => {
        showError(`API Error: ${error}`);
        throw error;
    });
}

/**
 * Status Indicator Functions
 */
function updateStatusIndicator() {
    const indicator = document.getElementById('statusIndicator');
    const btnText = document.getElementById('startBtnText');
    
    if (isRunning) {
        indicator.classList.add('running');
        btnText.textContent = 'Running';
    } else {
        indicator.classList.remove('running');
        btnText.textContent = 'Start Simulation';
    }
}

function showError(message) {
    const errorElement = document.getElementById('errorMessage');
    if (message) {
        errorElement.textContent = message;
        errorElement.classList.add('show');
    } else {
        errorElement.classList.remove('show');
    }
}

/**
 * Simulation Control Functions
 */
function startSimulation() {
    fetch('/api/start', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.is_running) {
                isRunning = true;
                updateStatusIndicator();
                showError('');
                startStatusUpdates();
            }
        })
        .catch(error => {
            showError('Failed to start simulation: ' + error);
        });
}

function stopSimulation() {
    fetch('/api/stop', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            isRunning = false;
            updateStatusIndicator();
            showError('');
            stopStatusUpdates();
        })
        .catch(error => {
            showError('Failed to stop simulation: ' + error);
        });
}

function setCyclePeriod() {
    const period = parseFloat(document.getElementById('cyclePeriod').value);
    fetchAPI('/api/cycle_period', {
        body: JSON.stringify({ period: period })
    })
    .then(data => {
        if (data.status === 'ok') {
            showError('');
        }
    })
    .catch(error => {
        showError('Failed to set cycle period: ' + error);
    });
}

/**
 * Configuration Save Functions
 */
function saveBatteryConfig() {
    const config = {
        voltage_100pct: parseFloat(document.getElementById('batteryVoltage100').value),
        voltage_0pct: parseFloat(document.getElementById('batteryVoltage0').value),
        charging_efficiency: parseFloat(document.getElementById('batteryEfficiency').value),
        initial_soc: parseFloat(document.getElementById('batteryInitialSoc').value) / 100.0
    };
    
    fetchAPI('/api/battery', { body: JSON.stringify(config) })
        .then(data => { if (data.status === 'ok') showError(''); })
        .catch(error => showError('Failed to save battery config: ' + error));
}

function saveConsumptionConfig() {
    const config = {
        consumption_type: document.getElementById('consumptionType').value,
        constant_consumption: parseFloat(document.getElementById('constantConsumption').value),
        min_consumption: parseFloat(document.getElementById('minConsumption').value),
        max_consumption: parseFloat(document.getElementById('maxConsumption').value),
        variation_interval: parseFloat(document.getElementById('consumptionVariation').value)
    };
    
    fetchAPI('/api/consumption', { body: JSON.stringify(config) })
        .then(data => { if (data.status === 'ok') showError(''); })
        .catch(error => showError('Failed to save consumption config: ' + error));
}

function saveMPPTConfig(instance) {
    const config = {
        panel_voltage_min: parseFloat(document.getElementById(`mppt${instance}VoltageMin`).value),
        panel_voltage_max: parseFloat(document.getElementById(`mppt${instance}VoltageMax`).value),
        panel_voltage_max_power: parseFloat(document.getElementById(`mppt${instance}VoltageMaxPower`).value),
        max_output_voltage: parseFloat(document.getElementById(`mppt${instance}MaxOutput`).value),
        max_panel_power: parseFloat(document.getElementById(`mppt${instance}MaxPower`).value),
        min_voltage_delta: parseFloat(document.getElementById(`mppt${instance}MinDelta`).value),
        voltage_factor: parseFloat(document.getElementById(`mppt${instance}VoltageFactor`).value),
        output_power_factor: parseFloat(document.getElementById(`mppt${instance}PowerFactor`).value)
    };
    
    fetchAPI(`/api/mppt/${instance}`, { body: JSON.stringify(config) })
        .then(data => { if (data.status === 'ok') showError(''); })
        .catch(error => showError('Failed to save MPPT config: ' + error));
}

function saveChargerConfig(instance) {
    const config = {
        charger_efficiency: parseFloat(document.getElementById(`charger${instance}Efficiency`).value)
    };
    
    fetchAPI(`/api/charger/${instance}`, { body: JSON.stringify(config) })
        .then(data => { if (data.status === 'ok') showError(''); })
        .catch(error => showError('Failed to save charger config: ' + error));
}

function saveChargerManualParams(instance) {
    const params = {
        input_voltage: parseFloat(document.getElementById(`charger${instance}ManualInputVoltage`).value),
        input_current: parseFloat(document.getElementById(`charger${instance}ManualInputCurrent`).value),
        output_voltage: parseFloat(document.getElementById(`charger${instance}ManualOutputVoltage`).value)
    };
    
    fetchAPI(`/api/charger_manual/${instance}`, { body: JSON.stringify(params) })
        .then(data => { if (data.status === 'ok') showError(''); })
        .catch(error => showError('Failed to save charger manual params: ' + error));
}

/**
 * Slider Update Functions
 */
function updateMPPTPanelVoltage(instance) {
    const slider = document.getElementById(`mppt${instance}PanelVoltageSlider`);
    const valueDisplay = document.getElementById(`mppt${instance}PanelVoltageValue`);
    
    if (slider && valueDisplay) {
        const value = parseFloat(slider.value);
        valueDisplay.textContent = value.toFixed(1);
        
        // Clear previous timeout
        if (mpptSliderTimeout) {
            clearTimeout(mpptSliderTimeout);
        }
        
        // Send update after slider stops moving (200ms delay)
        mpptSliderTimeout = setTimeout(() => {
            const params = { panel_voltage: value };
            fetchAPI(`/api/mppt_manual/${instance}`, { body: JSON.stringify(params) })
                .then(data => { if (data.status !== 'ok') showError('Failed to update panel voltage'); })
                .catch(error => showError('Error updating panel voltage: ' + error));
        }, 200);
    }
}

function updateChargerCurrent(instance) {
    const slider = document.getElementById(`charger${instance}OutputCurrentSlider`);
    const valueDisplay = document.getElementById(`charger${instance}OutputCurrentValue`);
    
    if (slider && valueDisplay) {
        const current = parseFloat(slider.value);
        valueDisplay.textContent = current.toFixed(1);
        
        // Send update to server
        const params = { current: current };
        fetchAPI(`/api/charger_current/${instance}`, { body: JSON.stringify(params) })
            .then(data => { if (data.status !== 'ok') showError('Failed to update charger current'); })
            .catch(error => showError('Error updating charger current: ' + error));
    }
}

function updateBatteryInitialSoc() {
    const slider = document.getElementById('batteryInitialSocSlider');
    const valueDisplay = document.getElementById('batteryInitialSocValue');
    
    if (slider && valueDisplay) {
        const socPercent = parseFloat(slider.value);
        valueDisplay.textContent = socPercent.toFixed(0) + '%';
        
        // Send update to server
        const config = { initial_soc: socPercent / 100 };
        fetchAPI('/api/battery', { body: JSON.stringify(config) })
            .then(data => { if (data.status !== 'ok') showError('Failed to update battery initial SoC'); })
            .catch(error => showError('Error updating battery initial SoC: ' + error));
    }
}

/**
 * Toggle Functions
 */
function toggleMPPT(instance) {
    const toggleBtn = document.getElementById(`mppt${instance}ToggleBtn`);
    if (!toggleBtn) return;
    
    const currentState = toggleBtn.textContent.trim();
    const newEnabled = currentState === 'OFF';
    const newText = newEnabled ? 'ON' : 'OFF';
    const newClass = newEnabled ? 'toggle-btn-on' : 'toggle-btn-off';
    
    const params = { enabled: newEnabled };
    fetchAPI(`/api/mppt_enabled/${instance}`, { body: JSON.stringify(params) })
        .then(data => {
            if (data.status === 'ok') {
                toggleBtn.textContent = newText;
                toggleBtn.className = 'toggle-btn ' + newClass;
            } else {
                showError('Failed to update MPPT state');
            }
        })
        .catch(error => showError('Error updating MPPT state: ' + error));
}

function toggleCharger(instance) {
    const toggleBtn = document.getElementById(`charger${instance}ToggleBtn`);
    if (!toggleBtn) return;
    
    const currentState = toggleBtn.textContent.trim();
    const newEnabled = currentState === 'OFF';
    const newText = newEnabled ? 'ON' : 'OFF';
    const newClass = newEnabled ? 'toggle-btn-on' : 'toggle-btn-off';
    
    const params = { enabled: newEnabled };
    fetchAPI(`/api/charger_enabled/${instance}`, { body: JSON.stringify(params) })
        .then(data => {
            if (data.status === 'ok') {
                toggleBtn.textContent = newText;
                toggleBtn.className = 'toggle-btn ' + newClass;
            } else {
                showError('Failed to update Charger state');
            }
        })
        .catch(error => showError('Error updating Charger state: ' + error));
}

function setChargerVoltageMode(instance) {
    const selectElement = document.getElementById(`charger${instance}VoltageMode`);
    if (!selectElement) return;
    
    const mode = selectElement.value;
    const params = { mode: mode };
    
    fetchAPI(`/api/charger_mode/${instance}`, { body: JSON.stringify(params) })
        .then(data => { if (data.status !== 'ok') showError('Failed to update charger voltage mode'); })
        .catch(error => showError('Error updating charger voltage mode: ' + error));
}

/**
 * Status Update Functions
 */
function startStatusUpdates() {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
    updateStatus();
    statusInterval = setInterval(updateStatus, 2000);
}

function stopStatusUpdates() {
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
}

function updateStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            isRunning = data.is_running;
            updateStatusIndicator();
            
            // Update system values
            updateSystemValues(data);
            
            // Store config data for building UI
            configData = data;
            
            // Build config sections only once
            if (!configSectionsBuilt) {
                buildConfigSections(data);
                configSectionsBuilt = true;
                
                // Initialize toggle button states after building sections
                initializeToggleStates(data);
            }
        })
        .catch(error => {
            console.error('Failed to get status:', error);
        });
}

function initializeToggleStates(data) {
    // Initialize MPPT button states
    if (data.manual_mppt_params) {
        for (const [instance, params] of Object.entries(data.manual_mppt_params)) {
            const enabled = params.enabled !== undefined ? params.enabled : true;
            const toggleBtn = document.getElementById(`mppt${instance}ToggleBtn`);
            if (toggleBtn) {
                toggleBtn.textContent = enabled ? 'ON' : 'OFF';
                toggleBtn.className = 'toggle-btn ' + (enabled ? 'toggle-btn-on' : 'toggle-btn-off');
            }
        }
    }
    
    // Initialize charger button states
    if (data.manual_charger_params) {
        for (const [instance, params] of Object.entries(data.manual_charger_params)) {
            const enabled = params.enabled !== undefined ? params.enabled : true;
            const toggleBtn = document.getElementById(`charger${instance}ToggleBtn`);
            if (toggleBtn) {
                toggleBtn.textContent = enabled ? 'ON' : 'OFF';
                toggleBtn.className = 'toggle-btn ' + (enabled ? 'toggle-btn-on' : 'toggle-btn-off');
            }
        }
    }
}

function updateSystemValues(data) {
    // Get runtime data
    const runtime = data.runtime || {};
    const battery = runtime.battery || {};
    
    // Update system values
    document.getElementById('systemVoltage').textContent = runtime.system_voltage ? runtime.system_voltage.toFixed(2) : '0.0';
    document.getElementById('consumptionPower').textContent = runtime.consumption_power ? runtime.consumption_power.toFixed(2) : '0.0';
    document.getElementById('batterySoc').textContent = battery.state_of_charge ? (battery.state_of_charge * 100).toFixed(1) : '0.0';
    document.getElementById('batteryVoltage').textContent = battery.voltage ? battery.voltage.toFixed(2) : '0.0';
    
    // Update MPPT runtime values
    if (runtime.mppts) {
        for (const [instance, mpptData] of Object.entries(runtime.mppts)) {
            const panelVoltageEl = document.getElementById(`mppt${instance}RuntimePanelVoltage`);
            const panelPowerEl = document.getElementById(`mppt${instance}RuntimePanelPower`);
            const outputCurrentEl = document.getElementById(`mppt${instance}RuntimeOutputCurrent`);
            
            if (panelVoltageEl) panelVoltageEl.textContent = mpptData.panel_voltage ? mpptData.panel_voltage.toFixed(2) : '0.0';
            if (panelPowerEl) panelPowerEl.textContent = mpptData.panel_power ? mpptData.panel_power.toFixed(2) : '0.0';
            if (outputCurrentEl) outputCurrentEl.textContent = mpptData.output_current ? mpptData.output_current.toFixed(2) : '0.0';
        }
    }
    
    // Update charger runtime values
    if (runtime.chargers) {
        for (const [instance, chargerData] of Object.entries(runtime.chargers)) {
            const inputVoltageEl = document.getElementById(`charger${instance}RuntimeInputVoltage`);
            const inputCurrentEl = document.getElementById(`charger${instance}RuntimeInputCurrent`);
            const outputVoltageEl = document.getElementById(`charger${instance}RuntimeOutputVoltage`);
            const outputCurrentEl = document.getElementById(`charger${instance}RuntimeOutputCurrent`);
            
            if (inputVoltageEl) inputVoltageEl.textContent = chargerData.input_voltage ? chargerData.input_voltage.toFixed(2) : '0.0';
            if (inputCurrentEl) inputCurrentEl.textContent = chargerData.input_current ? chargerData.input_current.toFixed(2) : '0.0';
            if (outputVoltageEl) outputVoltageEl.textContent = chargerData.output_voltage ? chargerData.output_voltage.toFixed(2) : '0.0';
            if (outputCurrentEl) outputCurrentEl.textContent = chargerData.output_current ? chargerData.output_current.toFixed(2) : '0.0';
        }
    }
}

/**
 * Build Configuration Sections
 * Creates the dynamic configuration UI based on data from the API
 */
function buildConfigSections(data) {
    const container = document.getElementById('configSections');
    const config = data;
    
    let html = '<div class="config-grid">';
    
    // Battery Configuration
    if (config.battery_config) {
        html += buildBatterySection(config.battery_config);
    }
    
    // Consumption Configuration
    if (config.consumption) {
        html += buildConsumptionSection(config.consumption);
    }
    
    // MPPT Configurations
    if (config.mppt_configs) {
        for (const [instance, mpptConfig] of Object.entries(config.mppt_configs)) {
            html += buildMPPTSection(instance, mpptConfig, config);
        }
    }
    
    // DC-DC Charger Configurations
    if (config.charger_configs) {
        for (const [instance, chargerConfig] of Object.entries(config.charger_configs)) {
            html += buildChargerSection(instance, chargerConfig, config);
        }
    }
    
    html += '</div>';
    container.innerHTML = html;
}

function buildBatterySection(batteryConfig) {
    return `
    <div class="device-box">
        <div class="device-header">
            <div class="device-title">Battery Configuration</div>
        </div>
        <div class="device-body">
            <div class="param-list">
                <h4>Parameters (from Energy Controller)</h4>
                <div class="param-item">
                    <span class="param-label">Nominal Voltage:</span>
                    <span class="param-value">${(batteryConfig.nominal_voltage || 12.0).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Nominal Capacity:</span>
                    <span class="param-value">${(batteryConfig.nominal_capacity || 200.0).toFixed(0)} Ah</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Voltage at 100%:</span>
                    <span class="param-value">${(batteryConfig.voltage_100pct || 14.4).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Voltage at 0%:</span>
                    <span class="param-value">${(batteryConfig.voltage_0pct || 10.0).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Charging Efficiency:</span>
                    <span class="param-value">${((batteryConfig.charging_efficiency || 0.9) * 100).toFixed(0)}%</span>
                </div>
            </div>
            
            <div class="config-section">
                <label>Adjust Initial SoC</label>
                <div class="slider-container">
                    <span class="slider-label">0-100%</span>
                    <input type="range" 
                           id="batteryInitialSocSlider" 
                           min="0" 
                           max="100" 
                           step="1" 
                           value="${formatSocValue(batteryConfig.initial_soc || 0.8)}"
                           class="slider"
                           oninput="updateBatteryInitialSoc()">
                    <span class="slider-value" id="batteryInitialSocValue">${formatSocDisplay(batteryConfig.initial_soc || 0.8)}%</span>
                </div>
            </div>
        </div>
    </div>
    `;
}

function buildConsumptionSection(consumption) {
    return `
    <div class="device-box">
        <div class="device-header">
            <div class="device-title">Consumption Configuration</div>
        </div>
        <div class="device-body">
            <div class="form-group">
                <label>Consumption Type</label>
                <select id="consumptionType" class="form-group select">
                    <option value="constant" ${consumption.type === 'constant' ? 'selected' : ''}>Constant</option>
                    <option value="variable" ${consumption.type === 'variable' ? 'selected' : ''}>Variable</option>
                </select>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Constant Consumption (W)</label>
                    <input type="number" id="constantConsumption" class="form-group input" value="${consumption.constant || 100}" step="1">
                </div>
                <div class="form-group">
                    <label>Variation Interval (s)</label>
                    <input type="number" id="consumptionVariation" class="form-group input" value="${consumption.variation_interval || 30}" step="1">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Min Consumption (W)</label>
                    <input type="number" id="minConsumption" class="form-group input" value="${consumption.min || 50}" step="1">
                </div>
                <div class="form-group">
                    <label>Max Consumption (W)</label>
                    <input type="number" id="maxConsumption" class="form-group input" value="${consumption.max || 150}" step="1">
                </div>
            </div>
            <button class="btn btn-primary" onclick="saveConsumptionConfig()">Save Consumption Config</button>
        </div>
    </div>
    `;
}

function buildMPPTSection(instance, mpptConfig, config) {
    const minVoltage = mpptConfig.min_voltage || 10.0;
    const maxVoltage = mpptConfig.max_voltage || 40.0;
    const manualParams = config.manual_mppt_params && config.manual_mppt_params[instance] ? config.manual_mppt_params[instance] : {};
    const currentPanelVoltage = manualParams.panel_voltage !== undefined ? manualParams.panel_voltage : maxVoltage;
    const isEnabled = manualParams.enabled !== undefined ? manualParams.enabled : true;
    
    return `
    <div class="device-box">
        <div class="device-header">
            <div class="device-title">MPPT ${instance} Configuration</div>
        </div>
        <div class="device-body">
            <div class="param-list">
                <h4>Configuration Parameters (from YAML)</h4>
                <div class="param-item">
                    <span class="param-label">Panel Voltage Min:</span>
                    <span class="param-value">${minVoltage.toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Panel Voltage Max:</span>
                    <span class="param-value">${maxVoltage.toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Voltage Max Power:</span>
                    <span class="param-value">${(mpptConfig.panel_voltage_max_power || 18.5).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Max Output Voltage:</span>
                    <span class="param-value">${(mpptConfig.max_output || 14.4).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Max Panel Power:</span>
                    <span class="param-value">${(mpptConfig.max_power || 300).toFixed(0)} W</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Min Voltage Delta:</span>
                    <span class="param-value">${(mpptConfig.min_voltage_delta || 0.5).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Voltage Factor:</span>
                    <span class="param-value">${(mpptConfig.voltage_factor || 0.1).toFixed(2)}</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Power Factor:</span>
                    <span class="param-value">${(mpptConfig.output_power_factor || 0.95).toFixed(2)}</span>
                </div>
            </div>
            
            <div class="config-section">
                <label>Panel Voltage Control</label>
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <button class="toggle-btn ${isEnabled ? 'toggle-btn-on' : 'toggle-btn-off'}" 
                            onclick="toggleMPPT(${instance})" 
                            id="mppt${instance}ToggleBtn">${isEnabled ? 'ON' : 'OFF'}</button>
                </div>
                <div class="slider-container">
                    <span class="slider-label">${minVoltage.toFixed(1)} V</span>
                    <input type="range" 
                           id="mppt${instance}PanelVoltageSlider" 
                           min="${minVoltage}" 
                           max="${maxVoltage}" 
                           step="0.1" 
                           value="${currentPanelVoltage}"
                           class="slider"
                           oninput="updateMPPTPanelVoltage(${instance})">
                    <span class="slider-value" id="mppt${instance}PanelVoltageValue">${currentPanelVoltage.toFixed(1)}</span>
                </div>
            </div>
            
            <div class="runtime-values">
                <h4>Runtime Values</h4>
                <div class="runtime-row">
                    <span>Panel Voltage:</span>
                    <span><strong id="mppt${instance}RuntimePanelVoltage">0.0</strong> V</span>
                </div>
                <div class="runtime-row">
                    <span>Panel Power:</span>
                    <span><strong id="mppt${instance}RuntimePanelPower">0.0</strong> W</span>
                </div>
                <div class="runtime-row">
                    <span>Output Current:</span>
                    <span><strong id="mppt${instance}RuntimeOutputCurrent">0.0</strong> A</span>
                </div>
            </div>
        </div>
    </div>
    `;
}

function buildChargerSection(instance, chargerConfig, config) {
    const minCurrent = chargerConfig.min_output_current || 0;
    const maxCurrent = chargerConfig.max_output_current || 20;
    const defaultCurrent = Math.min(maxCurrent, Math.max(minCurrent, 5.0));
    
    // Get current mode from manual params or default to absorption
    const manualParams = config.manual_charger_params && config.manual_charger_params[instance] ? config.manual_charger_params[instance] : {};
    const currentMode = manualParams.voltage_mode || 'absorption';
    const isEnabled = manualParams.enabled !== undefined ? manualParams.enabled : true;
    
    return `
    <div class="device-box">
        <div class="device-header">
            <div class="device-title">DC-DC Charger ${instance} Configuration</div>
        </div>
        <div class="device-body">
            <div class="param-list">
                <h4>Configuration Parameters (from YAML)</h4>
                <div class="param-item">
                    <span class="param-label">Efficiency:</span>
                    <span class="param-value">${(chargerConfig.efficiency || 0.92).toFixed(2)}</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Alternator Voltage:</span>
                    <span class="param-value">${(chargerConfig.alternator_voltage || 24.0).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Auxiliary Voltage:</span>
                    <span class="param-value">${(chargerConfig.aux_voltage || 24.0).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Absorption Voltage:</span>
                    <span class="param-value">${(chargerConfig.absorption_voltage || 14.2).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Float Voltage:</span>
                    <span class="param-value">${(chargerConfig.float_voltage || 13.5).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Storage Voltage:</span>
                    <span class="param-value">${(chargerConfig.storage_voltage || 13.0).toFixed(1)} V</span>
                </div>
                <div class="param-item">
                    <span class="param-label">Current Range:</span>
                    <span class="param-value">${minCurrent.toFixed(1)} - ${maxCurrent.toFixed(1)} A</span>
                </div>
            </div>
            
            <div class="config-section">
                <label>Charger Control</label>
                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                    <button class="toggle-btn ${isEnabled ? 'toggle-btn-on' : 'toggle-btn-off'}" 
                            onclick="toggleCharger(${instance})" 
                            id="charger${instance}ToggleBtn">${isEnabled ? 'ON' : 'OFF'}</button>
                </div>
                <div class="form-group" style="margin-bottom: 8px;">
                    <label>Output Voltage Mode:</label>
                    <select id="charger${instance}VoltageMode" 
                            onchange="setChargerVoltageMode(${instance})" 
                            class="form-group select">
                        <option value="absorption" ${currentMode === 'absorption' ? 'selected' : ''}>Absorption (${chargerConfig.absorption_voltage || 14.2} V)</option>
                        <option value="float" ${currentMode === 'float' ? 'selected' : ''}>Float (${chargerConfig.float_voltage || 13.5} V)</option>
                        <option value="storage" ${currentMode === 'storage' ? 'selected' : ''}>Storage (${chargerConfig.storage_voltage || 13.0} V)</option>
                    </select>
                </div>
                <div class="slider-container">
                    <span class="slider-label">${minCurrent.toFixed(1)} A</span>
                    <input type="range" 
                           id="charger${instance}OutputCurrentSlider" 
                           min="${minCurrent}" 
                           max="${maxCurrent}" 
                           step="0.1" 
                           value="${manualParams.output_current !== undefined ? manualParams.output_current : defaultCurrent}"
                           class="slider"
                           oninput="updateChargerCurrent(${instance})">
                    <span class="slider-value" id="charger${instance}OutputCurrentValue">${manualParams.output_current !== undefined ? manualParams.output_current.toFixed(1) : defaultCurrent.toFixed(1)}</span>
                </div>
            </div>
            
            <div class="runtime-values">
                <h4>Runtime Values</h4>
                <div class="runtime-row">
                    <span>Input Voltage:</span>
                    <span><strong id="charger${instance}RuntimeInputVoltage">0.0</strong> V</span>
                </div>
                <div class="runtime-row">
                    <span>Input Current:</span>
                    <span><strong id="charger${instance}RuntimeInputCurrent">0.0</strong> A</span>
                </div>
                <div class="runtime-row">
                    <span>Output Voltage:</span>
                    <span><strong id="charger${instance}RuntimeOutputVoltage">0.0</strong> V</span>
                </div>
                <div class="runtime-row">
                    <span>Output Current:</span>
                    <span><strong id="charger${instance}RuntimeOutputCurrent">0.0</strong> A</span>
                </div>
            </div>
        </div>
    </div>
    `;
}

/**
 * Helper Functions
 */
function formatSocValue(soc) {
    // Handle different scales: 0-1, 0-10, or 0-100
    // If value is between 0-1, multiply by 100
    // If value is between 0-10, multiply by 10
    // If value is between 0-100, use as-is
    if (soc <= 1) {
        return soc * 100;  // 0-1 scale to 0-100
    } else if (soc <= 10) {
        return soc * 10;   // 0-10 scale to 0-100
    } else {
        return soc;         // already 0-100 scale
    }
}

function formatSocDisplay(soc) {
    return formatSocValue(soc).toFixed(0);
}

/**
 * Initialization
 */
// Initial status check
updateStatus();

// Check if simulation is running on page load
setTimeout(() => {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            isRunning = data.is_running;
            updateStatusIndicator();
            if (isRunning) {
                startStatusUpdates();
            }
        });
}, 100);
