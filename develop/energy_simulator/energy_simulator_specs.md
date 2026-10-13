# Energy Simulator

The goal of the Energy Simulator is to emulate the operation (simplified) of the boat energy system to feed the various energy devices (Battery, MPPT, CHargers) with simulated values in order to test the Navigation Server Energy Management System.

## Architecture

The simulator includes a back_end process generating a set of simulated values using 3 sources:
- Static parameters from configuration files
- User inputs data
- Calculated values

These input values are given by the front_end Web UI communicating to the back end process that is acting as web_server.

The calculated simulated values are then sent over to the EnergyService process using a gRPC service: EnergySimulator.
The EnergySimulator service shall be added to the EnergyService process and will serve simulated values to the EnergyService process.
The devices (Battery, MPPT, Chargers) in the Energy process shall be configured in simulation mode.

## Simulator initialization

The simulator will get initial values from a) the configuration file and b) user inputs and then by quering the agent to get EnergySimulator service address.
Then from the EnergySimulator service itself, it will get the configuration from the service and thus the configuration to be used for the simulation.


