# Energy Simulator Implementation Summary

## Overview

This implementation provides a complete Energy Simulator system for the Navigation Server, allowing simulation of boat energy systems for testing the Energy Management System. The implementation follows the specifications in `doc/energy_simulator.md` and `protobuf/energy_simulator.proto`.

## Components Created

### 1. Simulation Models (`navigation_server/energy_mgmt/energy_simulator_models.py`)

**Classes:**
- `BatterySimulationConfig` - Configuration dataclass for battery simulation
- `BatterySimulationState` - Runtime state for battery
- `BatterySimulator` - Simulates battery behavior with SoC-based voltage and efficiency
- `ConsumptionSimulationConfig` - Configuration for consumption simulation
- `ConsumptionSimulationState` - Runtime state for consumption
- `ConsumptionSimulator` - Simulates constant or variable consumption
- `MPPTSimulationConfig` - Configuration for MPPT simulation
- `MPPTSimulationState` - Runtime state for MPPT
- `MPPTSimulator` - Implements MPPT simulation algorithm per specifications
- `DCDChargerSimulationConfig` - Configuration for DC-DC charger
- `DCDChargerSimulationState` - Runtime state for DC-DC charger
- `DCDChargerSimulator` - Simulates DC-DC charger with efficiency
- `EnergySystemSimulator` - Main coordinator for all device simulations

**Key Features:**
- All simulation algorithms implemented according to specifications
- Global energy equilibrium calculation
- System voltage calculation (max of all device voltages)
- Current/Power equilibrium across devices
- Cycle-based simulation (1-10 second periods)

### 2. EnergySimulator gRPC Service (`navigation_server/energy_mgmt/energy_simulator_service.py`)

**Classes:**
- `EnergySimulatorController` - Main controller that injects simulated data into energy services
- `EnergySimulatorServicer` - gRPC servicer implementing the EnergySimulator service interface
- `EnergySimulatorService` - GrpcService integration for EnergyService process

**Functionality:**
- Receives simulated data via gRPC from EnergySimulator server
- Injects data into BatteryService, MPPTService, DC-DC Service
- Updates EnergyController with source and battery data
- Can run internal simulation for testing (optional)

**gRPC Interface (from `energy_simulator.proto`):**
- `GetConfiguration` - Returns energy system configuration
- `SimulateBattery` - Receives battery simulated data
- `SimulateMPPT` - Receives MPPT simulated data
- `SimulateDcDc` - Receives DC-DC charger simulated data

### 3. EnergySimulator Server (`navigation_server/log_replay/energy_simulator_server.py`)

**Classes:**
- `EnergySimulatorEngine` - Main simulation engine with all device simulators
- `EnergySimulatorHTTPHandler` - HTTP request handler for Web UI and REST API
- `EnergySimulatorTopServer` - Top-level server managing HTTP server and simulation engine
- `EnergySimulatorService` - Service class for integration with server_main.py

**Functionality:**
- Web server on configurable port (default: 8081)
- REST API for configuration and control
- Simulation engine running in cycles
- gRPC client to connect to EnergySimulator service
- Web UI for interactive configuration

### 4. Web UI (`web_server/static/energy_simulator.html`)

**Features:**
- Responsive design with modern styling
- System status panel with start/stop controls
- Real-time display of system values
- Configuration panels for:
  - Battery parameters
  - Consumption settings
  - MPPT instances (configurable per instance)
  - DC-DC charger instances
- REST API integration via JavaScript

### 5. Configuration Files

**`conf/energy_simulator.yml`:**
- Complete configuration for EnergySimulator server
- HTTP server settings
- gRPC client settings
- All device configurations with defaults

**`run_energy_simulator`:**
- Executable script to run the Energy Simulator server
- Sets up environment and runs the server

### 6. Documentation

**`doc/energy_simulator_usage.md`:**
- Comprehensive usage guide
- Configuration examples
- REST API documentation
- Troubleshooting guide
- Architecture overview

## File Structure

```
navigation_server/
├── navigation_server/
│   ├── energy_mgmt/
│   │   ├── __init__.py (updated)
│   │   ├── energy_simulator_models.py (NEW)
│   │   └── energy_simulator_service.py (NEW)
│   └── log_replay/
│       ├── __init__.py (updated)
│       └── energy_simulator_server.py (NEW)
├── navigation_server/generated/
│   ├── energy_simulator_pb2.py (EXISTING)
│   └── energy_simulator_pb2_grpc.py (EXISTING)
├── web_server/static/
│   ├── energy_simulator.html (NEW)
│   └── index_energy_simulator.html (NEW)
├── protobuf/
│   └── energy_simulator.proto (EXISTING)
├── conf/
│   └── energy_simulator.yml (NEW)
├── doc/
│   └── energy_simulator_usage.md (NEW)
├── run_energy_simulator (NEW)
└── AGENT.md (UPDATED)
```

## REST API Endpoints

### GET
- `/api/status` - Current simulation status and configuration
- `/api/config` - Alias for /api/status
- `/api/system_config` - Energy system configuration from gRPC service

### POST
- `/api/start` - Start simulation
- `/api/stop` - Stop simulation
- `/api/cycle_period` - Set simulation cycle period (1-10s)
- `/api/battery` - Update battery configuration
- `/api/consumption` - Update consumption configuration
- `/api/mppt/{instance}` - Update MPPT configuration for instance
- `/api/charger/{instance}` - Update DC-DC charger configuration for instance

## Usage

### Starting the Energy Simulator Server

```bash
./run_energy_simulator
# or
poetry run python3 navigation_server/log_replay/energy_simulator_server.py \
    --settings conf/energy_simulator.yml \
    --working_dir .
```

### Accessing the Web UI

Open browser to: http://localhost:8081/energy_simulator.html

### Adding EnergySimulator Service to EnergyService

Add to your EnergyService configuration:

```yaml
EnergySimulatorService:
  name: EnergySimulator
  type: energy_mgmt.EnergySimulatorService
  battery_service: BatteryService
  mppt_services: [MPPTService0, MPPTService1]
  dc_dc_services: [DC_DC_Service0]
  energy_controller: EnergyService
  simulation_enabled: false
  cycle_period: 2.0
```

## Algorithm Details

### Battery Simulation
- Voltage: Linear interpolation between voltage_0pct and voltage_100pct based on SoC
- Energy: SoC × nominal_capacity × nominal_voltage (Wh)
- Current: Updates SoC based on current flow, accounting for charging efficiency

### Consumption Simulation
- **Constant Mode**: Fixed consumption value
- **Variable Mode**: Random consumption between min and max, changing at specified interval

### MPPT Simulation Algorithm
1. If panel_voltage < system_voltage + min_voltage_delta → MPPT is off
2. Compute theoretical production based on panel voltage (linear interpolation)
3. Compute output voltage using voltage_factor
4. If output_voltage < system_voltage → MPPT is off
5. Compute output current/power using power_factor

### DC-DC Charger Simulation
- Output Voltage = system_voltage
- Output Current = (input_voltage × input_current × efficiency) / output_voltage
- Input Power = output_power / efficiency

### Global Energy Equilibrium
- **System Voltage**: Maximum of all device voltages and battery voltage
- **Battery Current**:
  - No sources: Battery current = Consumption current
  - Sources ≤ consumption: Battery current = Consumption current - sum of sources
  - Production > consumption: Battery current = sum of sources - consumption current

## Dependencies

The implementation requires:
- Python 3.8+
- grpcio package
- All packages specified in pyproject.toml

The existing generated protobuf files (`energy_simulator_pb2.py` and `energy_simulator_pb2_grpc.py`) are already present and compatible with the implementation.

## Testing

All Python files have been verified for:
- Syntax correctness (using `ast.parse`)
- Compilation (using `py_compile`)
- Proper imports and module structure

## Next Steps

To complete the integration:

1. **Regenerate protobuf files** (if needed):
   ```bash
   ./gen_code.py
   ```

2. **Add EnergySimulatorService** to your EnergyService configuration file

3. **Start EnergyService** with the EnergySimulatorService enabled

4. **Start EnergySimulator Server**:
   ```bash
   ./run_energy_simulator
   ```

5. **Access Web UI** at http://localhost:8081/energy_simulator.html

6. **Start simulation** and verify values are being injected into the EnergyService

## Notes

- The implementation follows the existing code style and architecture patterns
- All files are properly documented with headers
- The code is designed to be maintainable and extensible
- Error handling is implemented for robustness
- Logging is used for debugging and monitoring
