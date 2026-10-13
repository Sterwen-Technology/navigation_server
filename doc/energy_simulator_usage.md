# Energy Simulator Usage Guide

## Overview

The Energy Simulator emulates the operation of the boat's energy system to provide simulated values for testing the Navigation Server Energy Management System. It consists of two main components:

1. **EnergySimulator Service** - A gRPC service added to the EnergyService process that receives simulated values and injects them into the energy devices
2. **EnergySimulator Server** - A separate process with a Web UI that generates and sends simulated values

## Architecture

### EnergySimulator Service (in EnergyService process)

This service implements the gRPC interface defined in `protobuf/energy_simulator.proto`:
- `GetConfiguration` - Returns the energy system configuration (all registered devices)
- `SimulateBattery` - Receives battery simulated data and injects it into BatteryService
- `SimulateMPPT` - Receives MPPT simulated data and injects it into MPPTService
- `SimulateDcDc` - Receives DC-DC charger simulated data and injects it into DC-DC Service

### EnergySimulator Server (separate process)

This is a standalone process that:
- Runs a Web server on port 8081 (configurable)
- Provides a Web UI for configuring and controlling the simulation
- Runs a simulation engine in cycles (1-10 seconds, configurable)
- Connects to the EnergySimulator service via gRPC to send simulated values

## Quick Start

### 1. Regenerate Protobuf Files

After any changes to `protobuf/energy_simulator.proto`, regenerate the Python gRPC files:

```bash
./gen_code.py
```

This will regenerate the files in `navigation_server/generated/`:
- `energy_simulator_pb2.py` - Protocol buffer definitions
- `energy_simulator_pb2_grpc.py` - gRPC service definitions

### 2. Add EnergySimulator Service to EnergyService

Update your EnergyService configuration (typically in `conf/settings.yml` or similar) to include the EnergySimulator service:

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

### 3. Run the Energy Simulator Server

```bash
./run_energy_simulator
```

Or manually:

```bash
cd /mnt/meaban/Sterwen-Tech-SW/navigation_server
poetry run python3 navigation_server/log_replay/energy_simulator_server.py \
    --settings conf/energy_simulator.yml \
    --working_dir .
```

The server will start with:
- Web UI available at: http://localhost:8081/energy_simulator.html
- gRPC connection to EnergySimulator service at: localhost:50051

## Configuration

### Energy Simulator Server Configuration (`conf/energy_simulator.yml`)

```yaml
EnergySimulator:
  # HTTP Web server configuration
  host: 0.0.0.0
  port: 8081
  
  # gRPC client configuration
  grpc_host: 127.0.0.1
  grpc_port: 50051
  secure: false
  
  # Simulation cycle period (1-10 seconds)
  cycle_period: 2.0
  
  # Battery configuration
  battery_voltage_100: 14.4      # Voltage at 100% SoC
  battery_voltage_0: 10.0        # Voltage at 0% SoC
  battery_efficiency: 0.9        # Charging efficiency
  battery_initial_soc: 0.8       # Initial State of Charge (0-1)
  battery_capacity: 200.0       # Nominal capacity in Ah
  battery_voltage: 12.0         # Nominal voltage
  
  # Consumption configuration
  consumption_type: variable    # 'constant' or 'variable'
  consumption_constant: 100.0    # Constant consumption in W (for constant mode)
  consumption_min: 50.0         # Minimum consumption in W (for variable mode)
  consumption_max: 150.0        # Maximum consumption in W (for variable mode)
  consumption_variation: 30.0   # Variation interval in seconds
  
  # MPPT instances to simulate
  mppt_instances: [0, 1]
  
  # MPPT configuration (per instance)
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
  
  # DC-DC charger configuration
  charger_0_efficiency: 0.92
```

## Web UI

Access the Web UI at: http://localhost:8081/energy_simulator.html

The UI provides:

1. **System Status Panel**
   - Start/Stop simulation buttons
   - Current system status
   - System voltage, consumption power, battery SoC and voltage

2. **Battery Configuration**
   - Voltage at 100% and 0% SoC
   - Charging efficiency
   - Initial State of Charge
   - Nominal capacity and voltage

3. **Consumption Configuration**
   - Consumption type (constant or variable)
   - Constant consumption value
   - Min/Max consumption for variable mode
   - Variation interval

4. **MPPT Configuration**
   - Per-instance configuration
   - Panel voltage range
   - Voltage for maximum power
   - Maximum output voltage
   - Maximum panel power
   - Voltage and power factors
   - Minimum voltage delta

5. **DC-DC Charger Configuration**
   - Per-instance configuration
   - Charger efficiency

## REST API

The Energy Simulator server provides a REST API for programmatic control:

### GET Endpoints

- `/api/status` - Get current simulation status and configuration
- `/api/config` - Get current configuration (alias for /api/status)
- `/api/system_config` - Get energy system configuration from EnergySimulator service

### POST Endpoints

- `/api/start` - Start the simulation
- `/api/stop` - Stop the simulation
- `/api/cycle_period` - Set simulation cycle period
  ```json
  { "period": 2.0 }
  ```
- `/api/battery` - Update battery configuration
  ```json
  {
    "voltage_100pct": 14.4,
    "voltage_0pct": 10.0,
    "charging_efficiency": 0.9,
    "initial_soc": 0.8,
    "nominal_capacity": 200.0,
    "nominal_voltage": 12.0
  }
  ```
- `/api/consumption` - Update consumption configuration
  ```json
  {
    "consumption_type": "variable",
    "constant_consumption": 100.0,
    "min_consumption": 50.0,
    "max_consumption": 150.0,
    "variation_interval": 30.0
  }
  ```
- `/api/mppt/{instance}` - Update MPPT configuration
  ```json
  {
    "panel_voltage_min": 15.0,
    "panel_voltage_max": 20.0,
    "panel_voltage_max_power": 18.5,
    "max_output_voltage": 14.4,
    "max_panel_power": 300.0,
    "voltage_factor": 0.1,
    "output_power_factor": 0.95,
    "min_voltage_delta": 0.5
  }
  ```
- `/api/charger/{instance}` - Update DC-DC charger configuration
  ```json
  {
    "charger_efficiency": 0.92
  }
  ```

## Simulation Algorithms

### Battery Simulation

- **Voltage**: Linear interpolation between `voltage_0pct` and `voltage_100pct` based on SoC
- **Energy**: `SoC * nominal_capacity * nominal_voltage` (in Wh)
- **Current**: Updates SoC based on current flow and charging efficiency

### Consumption Simulation

- **Constant Mode**: Fixed consumption value
- **Variable Mode**: Random consumption between min and max, changing at specified interval

### MPPT Simulation

1. If `panel_voltage < system_voltage + min_voltage_delta` => MPPT is off
2. Compute theoretical production based on panel voltage
3. Compute output voltage using voltage_factor
4. If `output_voltage < system_voltage` => MPPT is off
5. Compute output current/power using power_factor

### DC-DC Charger Simulation

- **Output Voltage**: System voltage
- **Output Current**: Computed using charger efficiency
- **Input Power**: Output power / efficiency

### Global Energy Equilibrium

1. **System Voltage**: Maximum of all device voltages and battery voltage
2. **Battery Current**: Calculated based on equilibrium between production and consumption
   - No sources: `Battery current = Consumption current`
   - Sources <= consumption: `Battery current = Consumption current - sum of sources`
   - Production > consumption: `Battery current = sum of sources - consumption current`

## File Structure

```
navigation_server/
├── navigation_server/
│   ├── energy_mgmt/
│   │   ├── __init__.py
│   │   ├── energy_simulator_service.py    # gRPC service for EnergyService
│   │   └── energy_simulator_models.py     # Simulation algorithms
│   └── log_replay/
│       ├── __init__.py
│       └── energy_simulator_server.py     # Energy Simulator server process
├── conf/
│   └── energy_simulator.yml              # Configuration file
├── protobuf/
│   └── energy_simulator.proto             # gRPC service definition
├── run_energy_simulator                  # Run script
└── doc/
    └── energy_simulator_usage.md          # This file
```

## Troubleshooting

### Common Issues

1. **gRPC Connection Failed**
   - Ensure EnergyService is running with EnergySimulatorService enabled
   - Check that the gRPC host and port match between server and service
   - Verify firewall allows connections on the gRPC port

2. **Web UI Not Loading**
   - Check that the web server port (default 8081) is available
   - Verify the file `web_server/static/energy_simulator.html` exists
   - Check browser console for JavaScript errors

3. **Simulation Not Starting**
   - Check that all required services (BatteryService, MPPTService, etc.) are running
   - Verify the configuration file has correct service names
   - Check logs for errors during service initialization

### Debugging

Enable debug logging by modifying the logger configuration or adding `--log_level debug` to the command line.

Check the logs for:
- gRPC connection errors
- Service initialization errors
- Configuration parsing errors
- Simulation cycle errors

## Future Enhancements

- Add support for more device types (Alternator, AC Charger, etc.)
- Implement historical data logging for simulation sessions
- Add scenario playback/recording functionality
- Support for multiple battery banks
- Advanced consumption patterns (time-based, device-specific)
- Integration with real-time data for hybrid simulation
