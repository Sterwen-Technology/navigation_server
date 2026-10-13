# Energy Simulator - Changes Summary

## Overview
This document summarizes the changes made to fix issues with the Energy Simulator and enable manual parameter control via the Web UI.

## Issues Fixed

### 1. DC-DC Charger Message Format
**File:** `navigation_server/energy_mgmt/energy_simulator_service.py`

**Problem:** The SimulateDcDc method was using incorrect scaling for VE.Direct fields.

**Fix:** Corrected the scaling to match Victron Orion XS VE.Direct protocol:
- `DC_IN_V`: Now correctly uses 0.01 V units (centivolts) by multiplying input_voltage by 100
- `DC_IN_I`: Now correctly uses 0.1 A units (deciamps) by multiplying input_current by 10
- `V`: Uses 0.001 V units (millivolts) by multiplying output_voltage by 1000
- `I`: Uses 0.001 A units (milliamps) by multiplying output_current by 1000
- `FWE`: Changed from `FW` to `FWE` to match DC_DCData.process_msg expectations

### 2. Battery Message Format
**File:** `navigation_server/energy_mgmt/energy_simulator_service.py`

**Status:** Already correct - SimulateBattery sends two messages in sequence with H1 field in the second message as required by BatteryService.

### 3. MPPT Instance Mismatch
**File:** `navigation_server/web_server/static/energy_simulator.html`

**Problem:** The HTML had hardcoded MPPT 0 and MPPT 1 sections, but only MPPT instance 0 was configured in energy_simulator.yml.

**Fix:** Created a new dynamic HTML UI (energy_simulator.html) that:
- Loads device configuration from the `/api/status` endpoint
- Only displays devices that are actually configured
- Removes hardcoded device instances

### 4. Manual Parameter Control
**Files:** 
- `navigation_server/log_replay/energy_simulator_server.py`
- `navigation_server/energy_mgmt/energy_simulator_models.py`
- `navigation_server/web_server/static/energy_simulator.html`

**Changes:**

#### EnergySimulatorEngine (energy_simulator_server.py):
- Added `_manual_mppt_params` dictionary to store manual MPPT parameters
- Added `_manual_charger_params` dictionary to store manual DC-DC charger parameters
- Added methods: `set_mppt_manual_params()`, `set_charger_manual_params()`
- Added methods: `get_mppt_manual_params()`, `get_charger_manual_params()`
- Updated `set_mppt_config()` and `set_charger_config()` to also handle manual simulation parameters
- Updated `get_status()` to include manual parameters in the response

#### EnergySystemSimulator (energy_simulator_models.py):
- Added `manual_mppt_params` dictionary to store manual MPPT parameters
- Added `manual_charger_params` dictionary to store manual DC-DC charger parameters
- Added methods: `set_mppt_manual_params()`, `set_charger_manual_params()`
- Updated `run_cycle()` to use manual parameters when available:
  - For MPPT: Uses manual `panel_voltage` if set
  - For DC-DC: Uses manual `input_voltage`, `input_current`, `output_voltage` if set

#### REST API Endpoints (energy_simulator_server.py):
- Added `/api/mppt_manual/{instance}` POST endpoint to set manual MPPT parameters
- Added `/api/charger_manual/{instance}` POST endpoint to set manual DC-DC charger parameters

#### HTML UI (energy_simulator.html):
- Complete rewrite with dynamic device loading
- Shows only configured devices (from `/api/status`)
- Added input fields for manual parameters:
  - MPPT: Panel Voltage
  - DC-DC: Input Voltage, Input Current, Output Voltage
- Added runtime value display for each device
- Added "Save Manual Params" buttons for each device

## New REST API Endpoints

### POST /api/mppt_manual/{instance}
Sets manual MPPT parameters for simulation.

**Request Body:**
```json
{
  "panel_voltage": 24.0
}
```

**Response:**
```json
{
  "status": "ok",
  "instance": 0,
  "params": {...}
}
```

### POST /api/charger_manual/{instance}
Sets manual DC-DC charger parameters for simulation.

**Request Body:**
```json
{
  "input_voltage": 24.0,
  "input_current": 5.0,
  "output_voltage": 14.4
}
```

**Response:**
```json
{
  "status": "ok",
  "instance": 0,
  "params": {...}
}
```

## Configuration

The energy_simulator.yml file should configure the devices to be simulated:

```yaml
# MPPT instances to simulate
mppt_instances: [0]

# MPPT 0 configuration
mppt_0_voltage_min: 15.0
mppt_0_voltage_max: 20.0
mppt_0_voltage_max_power: 18.5
mppt_0_max_output: 14.4
mppt_0_max_power: 300.0
mppt_0_voltage_factor: 0.1
mppt_0_power_factor: 0.95
mppt_0_min_delta: 0.5

# DC-DC charger instances to simulate
charger_instances: [0]

# DC-DC charger 0 configuration
charger_0_efficiency: 0.92
```

Only the devices listed in `mppt_instances` and `charger_instances` will be created and shown in the Web UI.

## Testing

To test the changes:

1. Start the Energy process with the energy_management_simulation.yml configuration
2. Start the Energy Simulator process with the energy_simulator.yml configuration
3. Open the Web UI at http://localhost:8081
4. Verify that:
   - Only configured devices (MPPT 0, DC-DC 0) are shown
   - Battery, MPPT, and DC-DC parameters can be configured
   - Manual parameters can be set for MPPT and DC-DC
   - Runtime values are displayed and update in real-time
   - No errors appear in the logs

## Known Issues

1. The HTML UI will need to be cleared from browser cache. Use Ctrl+F5 or open in incognito mode.
2. The simulation must be restarted after changing manual parameters for them to take effect.
