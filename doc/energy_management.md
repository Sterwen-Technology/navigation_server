# Energy Management

The energy management subsystem from the navigation server is a key feature of the ship's overall management and control.
The energy management system is designed to optimize the energy consumption of the ship by monitoring and controlling various energy sources and loads. It is a critical component of the ship's overall energy management strategy, and it plays a vital role in ensuring the efficient and sustainable operation of the ship.

**Energy management** data and controls are available via the navigation web server.

## Supported hardware

Currently, only Victron hardware with a VEDirect interface is supported. That is covering most of the systems present on small and medium size yachts.


## Software

The software includes a set of Couplers and services to connect energy control hardware (Victron), and provide supervision and visualization tools.

The current version (part of release 3.0.4) provides only basic and realtime features. History and storage are planned in upcoming releases.

Energy functions can be integrated in any process, but we recommend having a dedicated one. 

### Couplers and services

#### VEDirectCoupler(Coupler)

This class manages Victron VEDirect serial interface or a VEDirect log file as simulation. As VEDirect is not NMEA, they have a specific internal format by default. If the coupler mode is set to NMEA0183, then a XDR sentence is generated with the current, voltage and power from the panel.
This coupler is intended to be used by an energy device service (see below), rather than the global messaging router-server. However, if only some measurements are needed for display, it can be integrated like any other coupler but only in NMEA mode (protocol => nmea0183)

| Name       | Type               | Default  | Signification                                          |
|------------|--------------------|----------|--------------------------------------------------------|
| device     | string             | None     | name of the serial device with the VEDirect connection |
| alt_device | string             | None     | name of an alternative device to be used               |
| interface  | serial, simulation | serial   | type of input: direct serial or simulation             |
| logfile    | string             | None     | name of the file to be used for VEDirect simulation    |
| protocol   | string             | non_mmea | Use VEdirect specific messages                         |

#### Energy management service

Service class is **EnergyController**

The service provides a global control for several services linked to energy management. The interface is described in **energy.proto**.

It needs to be referenced by all the device-specific services that are documented here below.

##### MPPTService

This service receives the MPPT info via a VEDirectCoupler and keeps track of data and trends from the solar panel and MPPT output.
The service can also be used to forward NMEA0183 or NMEA2000 messages via a **GrpcPublisher** towards another server.
Interface is part of **energy.proto**

Additional parameters

| Name              | Type               | Default  | Signification                                                                                   |
|-------------------|--------------------|----------|-------------------------------------------------------------------------------------------------|
| coupler           | string             | None     | VEDirectCoupler required for data input. This is a mandatory parameter                          |
| server            | string             | None     | the gRPC server to which the service is attached                                                |
| energy_controller | string             | None     | referenn                                                                                        |
| publisher         | string             | None     | Optional publisher used to forward energy messages (see below)                                  |
| protocol          | nmea0183, nmea2000 | nmea0183 | XDR sentence for NMEA0183, PGN 127507, 127751 for NMEA2000 that will be pushed on the publisher |
| trend_depth       | int                | 30       | number of values in the trend table                                                             |
| trend_period      | float              | 10       | period of the trend bucket in seconds (min 1 sec)                                               |

#### BatteryService

Manages the battery, it is expected to be connected to a VEDirect shunt.
Configuration is similar to MPPTService

#### DC_DCService

Manages a DC-DC converter
Configuration is similar to MPPTService

### Configuration file example

```yaml
#-------------------------------------------------------------------------------
# Name:        energy management.yml
# Purpose:     Settings file for the local agent
#
# Author:      Laurent Carré
#
# Created:     08/07/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
#
#
function: Energy management server
server_name: Energy
log_level: INFO
trace_dir: /data/navigation/traces
data_dir: /data/navigation/data
enable_secure_grpc: false
force_secure_grpc: false
connect_agent: true
log_module:
    energy_mgmt.mppt_service: INFO
    energy_mgmt.energy_controller_service: DEBUG
    energy_mgmt.energy_simulator_service: DEBUG
    nmea2000.nmea2k_publisher: INFO
    router_common.grpc_server_service: INFO
    

features:
    - router_core
    - energy_mgmt
    - nmea2000
    - couplers:
          VEDirectCoupler

servers:

- Main:
      class: NavigationMainServer

- gRPCMain:
    class: GrpcServer
    port: 4505

couplers:

- SmartShunt1_VEDirect:
    class: VEDirectCoupler
    device: /dev/ttyUSB1        # RS232 port #1
    # alt_device: /dev/ttyUSB8
    interface: serial
    protocol: non_nmea
    max_attempt: 1

- MPPTVEDirect:
    class: VEDirectCoupler
    device: /dev/ttyUSB4
    alt_device: /dev/ttyUSB8
    interface: serial
    protocol: non_nmea
    max_attempt: 1

- DCDCVEDirect:
    class: VEDirectCoupler
    device: /dev/ttyUSB5
    alt_device: /dev/ttyUSB9
    interface: serial
    protocol: non_nmea
    max_attempt: 1


services:

- MPPTService:
    class: MPPTService
    coupler: MPPTVEDirect
    mode: coupler
    server: gRPCMain
    # publisher: NMEAPush
    protocol: nmea2000
    energy_controller: EnergyController
      # device parameters
    device_label: MPPT1
    device_model: Victron MPPT Blue Solar 70-15
    panel_max_power: 180
    panel_max_voltage: 40
    max_voltage: 15

- MainBattery:
    class: BatteryService
    coupler: SmartShunt1_VEDirect
    server: gRPCMain
    mode: coupler
    energy_controller: EnergyController
    # parameters
    nominal_voltage: 12.8
    nominal_capacity: 12.0
    chemistry: LFP
    max_charge_current: 10.0

- DCDCCharger:
    class: DC_DCService
    coupler: DCDCVEDirect
    server: gRPCMain
    mode: coupler
    energy_controller: EnergyController
    # device parameters
    device_label: DCDC1
    device_model: Victron Orion XS 70
    max_power: 1000


- EnergyController:
    class: EnergyService
    server: gRPCMain
    # all parameters as default

- EnergySimulator:
    class: EnergySimulatorService
    server: gRPCMain
    battery_service: MainBattery
    mppt_services: [MPPTService]
    dc_dc_services: [DCDCCharger]
    energy_controller: EnergyController
    # all other parameters as default

- Console:
    class: Console
    server: gRPCMain

publishers:

- NMEAPush:
    class: N2KForwarderToServer
    active: true
    service: EnergyService
    address: 127.0.0.1
    port: 4512
    device: MPPT
```


