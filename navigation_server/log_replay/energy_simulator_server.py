#-------------------------------------------------------------------------------
# Name:        energy_simulator_server.py
# Purpose:     Energy Simulator server - Top server for the Energy Simulator process
#              Implements a Web server with UI and simulation engine
#              Communicates with EnergyService via gRPC (EnergySimulator service)
#
# Author:      Vibe Code
#
# Created:     05/10/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from typing import Dict, List, Optional, Any

import grpc
from navigation_server.router_common import (
    MessageServerGlobals, GenericTopServer, NavThread, AgentClient,
    GrpcClient, resolve_ref, GrpcAccessException
)
from navigation_server.generated.energy_simulator_pb2 import ( battery_simulated_data,
    mppt_simulated_data, dc_dc_charger_simulated_data, simulator_parameter
)
from navigation_server.generated.energy_simulator_pb2_grpc import EnergySimulatorStub
from navigation_server.generated.energy_pb2 import EnergySource, BatteryBank, MPPT_device, DC_DC_Charger_Parameters, EnergyControllerParameters

# Import simulation models from energy_mgmt package
from navigation_server.energy_mgmt.energy_simulator_models import (
    EnergySystemSimulator, BatterySimulationConfig, ConsumptionSimulationConfig,
    MPPTSimulationConfig, DCDChargerSimulationConfig
)

from navigation_server.navigation_clients.energy_client import (
    EnergySimulatorClient, EnergyServiceClient, BatteryServiceClient, MPPT_Client, DC_DC_ServiceClient
)

# Set up module-level logger
_logger = logging.getLogger("ShipDataServer." + __name__)


class EnergySimulatorEngine:
    """
    Main simulation engine that runs in cycles
    
    Manages all device simulators and coordinates the simulation
    """
    
    def __init__(self, opts: Dict):
        self.opts = opts
        self.simulator = EnergySystemSimulator()
        self._is_running = False
        self._cycle_thread = None
        self._lock = threading.Lock()
        
        # FOR_AGENT: Simulation-specific parameters from YAML (only used if device is present)
        # These parameters fine-tune the simulation behavior and are not device characteristics
        self.cycle_period = opts.get('cycle_period', float, 2.0)
        
        # Consumption simulation parameters (simulation-specific, not from devices)
        self.consumption_config = ConsumptionSimulationConfig(
            consumption_type=opts.get('consumption_type', str, 'constant'),
            constant_consumption=opts.get('consumption_constant', float, 100.0),
            min_consumption=opts.get('consumption_min', float, 50.0),
            max_consumption=opts.get('consumption_max', float, 150.0),
            variation_interval=opts.get('consumption_variation', float, 30.0)
        )
        
        # Device instance lists from configuration
        self.mppt_instances = opts.getlist('mppt_instances', int, [])
        self.charger_instances = opts.getlist('charger_instances', int, [])
        _logger.info(f"Loaded device instances from config: MPPT={self.mppt_instances}, Chargers={self.charger_instances}")
        
        # Device configurations - initialized as None, populated only from running services
        # YAML contains no fallback device characteristics
        self.battery_config = None
        self.mppt_configs = {}  # Will be populated from MPPT service
        self.charger_configs = {}  # Will be populated from DC-DC service
        
        # Manual control parameters for simulation (editable via Web UI)
        # These override the hardcoded values in the simulation
        self._manual_mppt_params = {}  # instance -> {'panel_voltage': float}
        self._manual_charger_params = {}  # instance -> {'input_voltage': float, 'input_current': float, 'output_voltage': float}
        
        # Store last simulation results for Web UI display
        self._last_results = {
            'battery': None,
            'mppts': {},
            'chargers': {},
            'system_voltage': 0.0,
            'consumption_power': 0.0
        }
        
        # gRPC client for EnergySimulator service
        self._energy_client = None
        
        
        # Service clients to retrieve device information
        self._energy_service = None
        self._battery_service_client = None

        
    def set_energy_client(self, energy_client: GrpcClient):
        """Set the gRPC client for Energy and EnergySimulator service"""
        self._energy_client = energy_client
        self._simulator_service = EnergySimulatorClient()
        self._energy_client.add_service(self._simulator_service)
        self._energy_service = EnergyServiceClient()
        self._energy_client.add_service(self._energy_service)
        self._battery_service_client = BatteryServiceClient()
        self._energy_client.add_service(self._battery_service_client)
        
        # Initialize device configurations from YAML (manual control mode)
        # User can override these via Web UI
        self._initialize_device_configs_from_yaml()
        
    def _initialize_device_configs_from_yaml(self):
        """
        Initialize device configurations from YAML configuration.
        User can override these via Web UI for manual control of simulation parameters.
        
        Battery nominal_capacity and nominal_voltage are retrieved from the Battery Service.
        Other parameters (voltage_100pct, voltage_0pct, charging_efficiency, initial_soc) come from YAML.
        
        This is the preferred approach for manual simulation control rather than
        retrieving from running services.
        """
        try:
            _logger.info("Initializing device configurations from YAML")
            
            # Battery configuration from YAML
            # nominal_capacity and nominal_voltage come from Battery Service
            # Simulation-specific parameters (voltage_100pct, voltage_0pct, charging_efficiency, initial_soc) come from YAML
            battery_config = BatterySimulationConfig(
                nominal_voltage=12.0,  # Will be updated from Battery Service
                nominal_capacity=200.0,  # Will be updated from Battery Service
                voltage_100pct=self.opts.get('battery_voltage_100', float, 14.4),
                voltage_0pct=self.opts.get('battery_voltage_0', float, 10.0),
                initial_soc=self.opts.get('battery_initial_soc', float, 0.8),
                charging_efficiency=self.opts.get('battery_efficiency', float, 0.9)
            )
            self.battery_config = battery_config
            self.simulator.configure_battery(battery_config)
            _logger.info("Battery configuration loaded from YAML (nominal values will be updated from Battery Service)")
            
            # Try to retrieve nominal values from Battery Service (overrides YAML defaults)
            self._try_update_battery_from_service()
            
            # MPPT configurations from YAML
            if self.mppt_instances:
                for instance in self.mppt_instances:
                    mppt_config = MPPTSimulationConfig(
                        panel_voltage_min=self.opts.get(f'mppt_{instance}_voltage_min', float, 15.0),
                        panel_voltage_max=self.opts.get(f'mppt_{instance}_voltage_max', float, 20.0),
                        panel_voltage_max_power=self.opts.get(f'mppt_{instance}_voltage_max_power', float, 18.5),
                        max_output_voltage=self.opts.get(f'mppt_{instance}_max_output', float, 14.4),
                        max_panel_power=self.opts.get(f'mppt_{instance}_max_power', float, 300.0),
                        voltage_factor=self.opts.get(f'mppt_{instance}_voltage_factor', float, 0.1),
                        output_power_factor=self.opts.get(f'mppt_{instance}_power_factor', float, 0.95),
                        min_voltage_delta=self.opts.get(f'mppt_{instance}_min_delta', float, 0.5)
                    )
                    self.mppt_configs[instance] = mppt_config
                    self.simulator.add_mppt(instance, mppt_config)
                    _logger.info(f"MPPT {instance} configuration loaded from YAML")
            else:
                _logger.info("No MPPT instances configured in YAML")
            
            # DC-DC charger configurations from YAML
            if self.charger_instances:
                for instance in self.charger_instances:
                    charger_config = DCDChargerSimulationConfig(
                        charger_efficiency=self.opts.get(f'charger_{instance}_efficiency', float, 0.92),
                        alternator_voltage=self.opts.get(f'charger_{instance}_alternator_voltage', float, 24.0),
                        aux_voltage=self.opts.get(f'charger_{instance}_aux_voltage', float, 24.0),
                        absorption_voltage=self.opts.get(f'charger_{instance}_absorption_voltage', float, 14.2),
                        float_voltage=self.opts.get(f'charger_{instance}_float_voltage', float, 13.5),
                        storage_voltage=self.opts.get(f'charger_{instance}_storage_voltage', float, 13.0),
                        min_output_current=self.opts.get(f'charger_{instance}_min_current', float, 0.0),
                        max_output_current=self.opts.get(f'charger_{instance}_max_current', float, 20.0)
                    )
                    self.charger_configs[instance] = charger_config
                    self.simulator.add_charger(instance, charger_config)
                    _logger.info(f"DC-DC charger {instance} configuration loaded from YAML")
            else:
                _logger.info("No DC-DC charger instances configured in YAML")
            
            # Consumption configuration from YAML
            self.simulator.configure_consumption(self.consumption_config)
            _logger.info("Consumption configuration loaded from YAML")
            
            _logger.info("Device configurations initialized from YAML - ready for manual control")
            _logger.info(f"Initialized configs: MPPT={list(self.mppt_configs.keys())}, Chargers={list(self.charger_configs.keys())}, Battery={self.battery_config is not None}")
            
        except Exception as e:
            _logger.error(f"Error initializing device configurations from YAML: {e}")
        
    def _try_update_battery_from_service(self):
        """
        Try to retrieve battery nominal_capacity and nominal_voltage from Battery Service.
        These values should come from the Energy Controller/Battery Service, not simulation parameters.
        """
        try:
            if self._battery_service_client and self._energy_client and self._energy_client.connected:
                # Check if the service client has its server attached and stub created
                if hasattr(self._battery_service_client, '_server') and self._battery_service_client._server:
                    # Try to get battery information
                    battery_info = self._battery_service_client.GetInformation("parameters")
                    if battery_info and hasattr(battery_info, 'battery') and battery_info.battery:
                        battery_bank = battery_info.battery
                        _logger.info(f"Retrieved battery info from service: nominal_voltage={battery_bank.nominal_voltage}V, nominal_capacity={battery_bank.nominal_capacity}Ah")
                        
                        # Update battery config with nominal values from service
                        with self._lock:
                            if self.battery_config:
                                self.battery_config.nominal_voltage = battery_bank.nominal_voltage
                                self.battery_config.nominal_capacity = battery_bank.nominal_capacity
                                # Also update initial_soc from service if available
                                # Note: state_of_charge from BatteryBank is already a ratio (0-1), not percentage
                                if battery_bank.state_of_charge > 0:
                                    self.battery_config.initial_soc = battery_bank.state_of_charge
                                
                                # Reconfigure simulator with updated battery config
                                self.simulator.configure_battery(self.battery_config)
                                _logger.info(f"Battery simulation updated with nominal values from service")
                    else:
                        _logger.warning("No battery information available from Battery Service, using YAML defaults")
                else:
                    _logger.warning("Battery Service client not properly initialized, using YAML defaults")
            else:
                _logger.warning("Battery Service not available, using YAML defaults for nominal values")
        except Exception as e:
            _logger.warning(f"Failed to retrieve battery info from service: {e}, using YAML defaults")
        
    def _retrieve_device_information_from_services(self):
        """
        OLD METHOD - Retrieve device information from running Energy services.
        This is kept for backward compatibility but not used by default.
        
        Major parameters like names, capacity, and device characteristics
        must be retrieved from the running services using GetInformation method.
        """
        # This method is no longer used by default - we use YAML configuration
        _logger.info("Service retrieval method called but not used (YAML configuration mode active)")
        
    def _has_battery(self, energy_info) -> bool:
        """Check if battery is configured in the system"""
        return energy_info and energy_info.batteries and len(energy_info.batteries) > 0
        
    def _has_mppt(self, energy_info) -> bool:
        """Check if MPPT is configured in the system"""
        if not energy_info or not energy_info.sources:
            return False
        for source in energy_info.sources:
            if source.type == EnergySource.Solar_MPPT:
                return True
        return False
        
    def _has_charger(self, energy_info) -> bool:
        """Check if DC-DC charger is configured in the system"""
        if not energy_info or not energy_info.sources:
            return False
        for source in energy_info.sources:
            if source.type in [EnergySource.DC_DC_Charger, EnergySource.AC_DC_ChargerConverter]:
                return True
        return False
        
    def _update_config_from_energy_info(self, energy_info):
        """Update configuration from EnergyControllerParameters"""
        # This method now just serves as a placeholder for future system-wide updates
        # Device-specific configuration is handled in separate _update_config_from_* methods
        pass
        
    def _update_config_from_battery_info(self, battery_info: BatteryBank):
        """Update battery nominal values from BatteryBank information.
        
        Note: nominal_voltage and nominal_capacity come from the service.
        Simulation-specific parameters (voltage_100pct, voltage_0pct, charging_efficiency, initial_soc) 
        are kept from YAML configuration.
        """
        with self._lock:
            if not self.battery_config:
                _logger.warning("Cannot update battery config: no battery config initialized")
                return
            
            # Update nominal values from service
            old_config = self.battery_config
            self.battery_config = BatterySimulationConfig(
                nominal_voltage=battery_info.nominal_voltage,
                nominal_capacity=battery_info.nominal_capacity,
                voltage_100pct=old_config.voltage_100pct,
                voltage_0pct=old_config.voltage_0pct,
                # Note: state_of_charge from BatteryBank is already a ratio (0-1), not percentage
                initial_soc=battery_info.state_of_charge if battery_info.state_of_charge > 0 else old_config.initial_soc,
                charging_efficiency=old_config.charging_efficiency,
                max_charge_current=battery_info.max_charge_current
            )
            
            _logger.info(f"Updated battery nominal values from Battery service: voltage={battery_info.nominal_voltage}V, "
                        f"capacity={battery_info.nominal_capacity}Ah, SoC={battery_info.state_of_charge * 100:.1f}%")
            
            self.simulator.configure_battery(self.battery_config)
        
    def _update_config_from_mppt_info(self, instance: int, mppt_info):
        """Update MPPT configuration from MPPT device information"""
        with self._lock:
            # FOR_AGENT: Device characteristics come from service, simulation params from YAML
            # Map device parameters to simulation config
            params = mppt_info.parameters
            
            # MPPT_parameters provides:
            # - panel_max_power: Maximum panel power (W)
            # - panel_max_voltage: Maximum panel voltage (V)
            # - max_voltage: Maximum voltage (V)
            # Derive simulation-specific parameters from device characteristics
            # panel_voltage_min: use reasonable lower bound (e.g., 80% of nominal)
            # panel_voltage_max_power: same as panel_max_voltage for now
            nominal_voltage = params.panel_max_voltage * 0.8  # Estimate
            
            self.mppt_configs[instance] = MPPTSimulationConfig(
                # Device characteristics mapped from service data
                panel_voltage_min=nominal_voltage,
                panel_voltage_max=params.panel_max_voltage,
                panel_voltage_max_power=params.panel_max_voltage,
                max_output_voltage=params.max_voltage,
                max_panel_power=params.panel_max_power,
                # Simulation-specific parameters from YAML
                voltage_factor=self.opts.get(f'mppt_{instance}_voltage_factor', float, 0.1),
                output_power_factor=self.opts.get(f'mppt_{instance}_power_factor', float, 0.95),
                min_voltage_delta=self.opts.get(f'mppt_{instance}_min_delta', float, 0.5)
            )
            self.simulator.add_mppt(instance, self.mppt_configs[instance])
            
            _logger.info(f"Updated MPPT {instance} config from device info: {mppt_info.device_model}, "
                        f"max_power={params.panel_max_power}W, max_voltage={params.panel_max_voltage}V")
        
    def _update_config_from_dc_dc_info(self, instance: int, charger_info: DC_DC_Charger_Parameters):
        """Update DC-DC charger configuration from device information"""
        with self._lock:
            # FOR_AGENT: Device characteristics from service, simulation params from YAML
            self.charger_configs[instance] = DCDChargerSimulationConfig(
                # Simulation-specific parameter from YAML
                charger_efficiency=self.opts.get(f'charger_{instance}_efficiency', float, 0.92)
            )
            self.simulator.add_charger(instance, self.charger_configs[instance])
            
            _logger.info(f"Updated DC-DC charger {instance} config from device info: "
                        f"input_voltage_range={charger_info.input_voltage_range}V, "
                        f"output_voltage_range={charger_info.output_voltage_range}V, "
                        f"max_power={charger_info.max_power}W")

    def start(self):
        """Start the simulation engine"""
        with self._lock:
            if self._is_running:
                _logger.warning("Simulation engine already running")
                return
            
            self._is_running = True
            self.simulator.set_cycle_period(self.cycle_period)
            
            # FOR_AGENT: Only configure devices that are present in the system
            if self.battery_config:
                self.simulator.configure_battery(self.battery_config)
                _logger.info("Battery simulation configured")
            else:
                _logger.info("No battery configuration - battery simulation disabled")
            
            self.simulator.configure_consumption(self.consumption_config)
            _logger.info("Consumption simulation configured")
            
            # Log configured devices
            _logger.info(f"Simulator configured with: Battery={len([k for k in [self.battery_config] if k]) > 0}, "
                        f"MPPTs={len(self.mppt_configs)}, Chargers={len(self.charger_configs)}")
            
            self._cycle_thread = threading.Thread(target=self._run_cycles, daemon=True)
            self._cycle_thread.start()
            _logger.info("Energy Simulator engine started")
        
    def stop(self):
        """Stop the simulation engine"""
        with self._lock:
            self._is_running = False
            if self._cycle_thread:
                self._cycle_thread.join(timeout=5.0)
                self._cycle_thread = None
            _logger.info("Energy Simulator engine stopped")
        
    def _run_cycles(self):
        """Main cycle loop"""
        _logger.info(f"Starting simulation cycles with period {self.cycle_period}s")
        
        cycle_count = 0
        while self._is_running:
            start_time = time.monotonic()
            cycle_count += 1
            
            try:
                # FOR_AGENT: Trace simulation cycle start
                _logger.debug(f"=== Simulation Cycle #{cycle_count} START ===")
                _logger.debug(f"System voltage: {self.simulator.system_voltage:.2f}V")
                
                results = self.simulator.run_cycle()
                
                # FOR_AGENT: Trace results before publishing
                self._trace_cycle_results(cycle_count, results)
                
                self._publish_results(results)
                
                # FOR_AGENT: Trace successful cycle
                _logger.debug(f"=== Simulation Cycle #{cycle_count} COMPLETE ===")
                
            except Exception as e:
                _logger.error(f"Error in simulation cycle #{cycle_count}: {e}")
                import traceback
                _logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Calculate sleep time to maintain cycle period
            cycle_time = time.monotonic() - start_time
            sleep_time = max(0.0, self.cycle_period - cycle_time)
            
            # FOR_AGENT: Trace cycle timing
            if cycle_time > self.cycle_period * 0.9:
                _logger.warning(f"Cycle #{cycle_count} took {cycle_time:.3f}s (expected < {self.cycle_period * 0.9:.3f}s)")
            else:
                _logger.debug(f"Cycle #{cycle_count} completed in {cycle_time:.3f}s, sleeping {sleep_time:.3f}s")
            
            time.sleep(sleep_time)
        
    def _trace_cycle_results(self, cycle_num: int, results: Dict):
        """
        FOR_AGENT: Trace simulation cycle results for debugging and verification
        """
        try:
            system_voltage = results.get('system_voltage', 0.0)
            consumption = results.get('consumption_power', 0.0)
            
            _logger.debug(f"Cycle #{cycle_num} - System: {system_voltage:.2f}V, Consumption: {consumption:.2f}W")
            
            # Trace battery state
            battery = results.get('battery', {})
            if battery:
                _logger.debug(f"  Battery: Voltage={battery.get('voltage', 0):.2f}V, "
                            f"Current={battery.get('current', 0):.2f}A, "
                            f"SoC={battery.get('state_of_charge', 0) * 100:.1f}%, "
                            f"Power={battery.get('power', 0):.2f}W")
            
            # Trace MPPT states
            mppts = results.get('mppts', {})
            for instance, mppt in mppts.items():
                if mppt.get('mppt_on', False):
                    _logger.debug(f"  MPPT {instance}: ON - Panel={mppt.get('panel_voltage', 0):.2f}V, "
                                f"Power={mppt.get('panel_power', 0):.2f}W, "
                                f"Output={mppt.get('output_current', 0):.2f}A @ {mppt.get('output_voltage', 0):.2f}V")
                else:
                    _logger.debug(f"  MPPT {instance}: OFF")
            
            # Trace charger states
            chargers = results.get('chargers', {})
            for instance, charger in chargers.items():
                _logger.debug(f"  Charger {instance}: Input={charger.get('input_voltage', 0):.2f}V, "
                            f"Output={charger.get('output_voltage', 0):.2f}V @ {charger.get('output_current', 0):.2f}A")
            
        except Exception as e:
            _logger.warning(f"Error tracing cycle results: {e}")
        
    def _publish_results(self, results: Dict):
        """
        Publish simulation results to EnergySimulator service via gRPC
        
        FOR_AGENT: Detailed tracing of published data for verification
        """
        # Store last results for Web UI display
        with self._lock:
            self._last_results = {
                'battery': results.get('battery', {}),
                'mppts': results.get('mppts', {}),
                'chargers': results.get('chargers', {}),
                'system_voltage': results.get('system_voltage', 0.0),
                'consumption_power': results.get('consumption_power', 0.0)
            }
        
        if self._simulator_service is None:
            _logger.warning("No simulator service configured, cannot publish results")
            return
        
        try:
            publish_count = 0
            
            # Publish battery data
            battery_data = results.get('battery', {})
            if battery_data:
                battery_msg = battery_simulated_data()
                battery_msg.voltage = battery_data.get('voltage', 0.0)
                battery_msg.current = battery_data.get('current', 0.0)
                battery_msg.state_of_charge = battery_data.get('state_of_charge', 0.0)
                battery_msg.power = battery_data.get('power', 0.0)
                self._simulator_service.SimulateBattery(battery_msg)
                publish_count += 1
                _logger.debug(f"[PUBLISH] Battery: {battery_msg.voltage:.2f}V, {battery_msg.current:.2f}A, "
                            f"SoC={battery_msg.state_of_charge*100:.1f}%, Power={battery_msg.power:.2f}W")
            else:
                _logger.debug("[PUBLISH] No battery data to publish")
            
            # Publish MPPT data
            for instance, mppt_data in results.get('mppts', {}).items():
                mppt_msg = mppt_simulated_data()
                mppt_msg.instance = int(instance)
                mppt_msg.panel_voltage = mppt_data.get('panel_voltage', 0.0)
                mppt_msg.panel_power = mppt_data.get('panel_power', 0.0)
                mppt_msg.output_voltage = mppt_data.get('output_voltage', 0.0)
                mppt_msg.output_current = mppt_data.get('output_current', 0.0)
                self._simulator_service.SimulateMPPT(mppt_msg)
                publish_count += 1
                _logger.debug(f"[PUBLISH] MPPT {instance}: Panel={mppt_msg.panel_voltage:.2f}V, "
                            f"Power={mppt_msg.panel_power:.2f}W, Output={mppt_msg.output_current:.2f}A")
            
            # Publish DC-DC charger data
            for instance, charger_data in results.get('chargers', {}).items():
                charger_msg = dc_dc_charger_simulated_data()
                charger_msg.instance = int(instance)
                charger_msg.input_voltage = charger_data.get('input_voltage', 0.0)
                charger_msg.input_current = charger_data.get('input_current', 0.0)
                charger_msg.output_voltage = charger_data.get('output_voltage', 0.0)
                charger_msg.output_current = charger_data.get('output_current', 0.0)
                self._simulator_service.SimulateDcDc(charger_msg)
                publish_count += 1
                _logger.debug(f"[PUBLISH] Charger {instance}: In={charger_msg.input_voltage:.2f}V @ {charger_msg.input_current:.2f}A, "
                            f"Out={charger_msg.output_voltage:.2f}V @ {charger_msg.output_current:.2f}A")
            
            if publish_count > 0:
                _logger.debug(f"[PUBLISH] Successfully published {publish_count} device updates")
            else:
                _logger.warning("[PUBLISH] No device data published in this cycle")
                
        except Exception as e:
            _logger.error(f"Error publishing simulation results: {e}")
            import traceback
            _logger.error(f"Publish traceback: {traceback.format_exc()}")
                
        except Exception as e:
            _logger.error(f"Error publishing simulation results: {e}")
    
    def set_battery_config(self, config: Dict):
        """Update battery configuration from UI"""
        with self._lock:
            if not self.battery_config:
                _logger.warning("Cannot update battery config: no battery present in system")
                return
            
            if 'voltage_100pct' in config:
                self.battery_config.voltage_100pct = float(config['voltage_100pct'])
            if 'voltage_0pct' in config:
                self.battery_config.voltage_0pct = float(config['voltage_0pct'])
            if 'charging_efficiency' in config:
                self.battery_config.charging_efficiency = float(config['charging_efficiency'])
            if 'initial_soc' in config:
                self.battery_config.initial_soc = float(config['initial_soc'])
            if 'nominal_capacity' in config:
                self.battery_config.nominal_capacity = float(config['nominal_capacity'])
            if 'nominal_voltage' in config:
                self.battery_config.nominal_voltage = float(config['nominal_voltage'])
            
            self.simulator.configure_battery(self.battery_config)
        
    def set_consumption_config(self, config: Dict):
        """Update consumption configuration from UI"""
        with self._lock:
            if 'consumption_type' in config:
                self.consumption_config.consumption_type = str(config['consumption_type'])
            if 'constant_consumption' in config:
                self.consumption_config.constant_consumption = float(config['constant_consumption'])
            if 'min_consumption' in config:
                self.consumption_config.min_consumption = float(config['min_consumption'])
            if 'max_consumption' in config:
                self.consumption_config.max_consumption = float(config['max_consumption'])
            if 'variation_interval' in config:
                self.consumption_config.variation_interval = float(config['variation_interval'])
            
            self.simulator.configure_consumption(self.consumption_config)
        
    def set_mppt_config(self, instance: int, config: Dict):
        """Update MPPT configuration from UI"""
        with self._lock:
            if instance not in self.mppt_configs:
                self.mppt_configs[instance] = MPPTSimulationConfig()
                self.simulator.add_mppt(instance, self.mppt_configs[instance])
            
            mppt_config = self.mppt_configs[instance]
            if 'panel_voltage_min' in config:
                mppt_config.panel_voltage_min = float(config['panel_voltage_min'])
            if 'panel_voltage_max' in config:
                mppt_config.panel_voltage_max = float(config['panel_voltage_max'])
            if 'panel_voltage_max_power' in config:
                mppt_config.panel_voltage_max_power = float(config['panel_voltage_max_power'])
            if 'max_output_voltage' in config:
                mppt_config.max_output_voltage = float(config['max_output_voltage'])
            if 'max_panel_power' in config:
                mppt_config.max_panel_power = float(config['max_panel_power'])
            if 'voltage_factor' in config:
                mppt_config.voltage_factor = float(config['voltage_factor'])
            if 'output_power_factor' in config:
                mppt_config.output_power_factor = float(config['output_power_factor'])
            if 'min_voltage_delta' in config:
                mppt_config.min_voltage_delta = float(config['min_voltage_delta'])
            
            # Check for manual simulation parameters
            manual_params = {}
            if 'panel_voltage' in config:
                manual_params['panel_voltage'] = float(config['panel_voltage'])
            if manual_params:
                self.simulator.set_mppt_manual_params(instance, manual_params)
                self._manual_mppt_params[instance] = manual_params
        
    def set_charger_config(self, instance: int, config: Dict):
        """Update DC-DC charger configuration from UI"""
        with self._lock:
            if instance not in self.charger_configs:
                self.charger_configs[instance] = DCDChargerSimulationConfig()
                self.simulator.add_charger(instance, self.charger_configs[instance])
            
            charger_config = self.charger_configs[instance]
            if 'charger_efficiency' in config:
                charger_config.charger_efficiency = float(config['charger_efficiency'])
            
            # Check for manual simulation parameters
            manual_params = {}
            if 'input_voltage' in config:
                manual_params['input_voltage'] = float(config['input_voltage'])
            if 'input_current' in config:
                manual_params['input_current'] = float(config['input_current'])
            if 'output_voltage' in config:
                manual_params['output_voltage'] = float(config['output_voltage'])
            if manual_params:
                self.simulator.set_charger_manual_params(instance, manual_params)
                self._manual_charger_params[instance] = manual_params
    
    def set_mppt_manual_params(self, instance: int, params: Dict):
        """Set manual MPPT parameters for simulation (editable via Web UI)"""
        with self._lock:
            if instance not in self._manual_mppt_params:
                self._manual_mppt_params[instance] = {}
            if 'panel_voltage' in params:
                self._manual_mppt_params[instance]['panel_voltage'] = float(params['panel_voltage'])
            # Update simulator
            self.simulator.set_mppt_manual_params(instance, self._manual_mppt_params[instance])
    
    def set_mppt_enabled(self, instance: int, enabled: bool):
        """Set MPPT enabled/disabled state"""
        with self._lock:
            if instance not in self._manual_mppt_params:
                self._manual_mppt_params[instance] = {}
            self._manual_mppt_params[instance]['enabled'] = enabled
            # Update simulator
            self.simulator.set_mppt_enabled(instance, enabled)
    
    def set_charger_enabled(self, instance: int, enabled: bool):
        """Set charger enabled/disabled state"""
        with self._lock:
            if instance not in self._manual_charger_params:
                self._manual_charger_params[instance] = {}
            self._manual_charger_params[instance]['enabled'] = enabled
            # Update simulator
            self.simulator.set_charger_enabled(instance, enabled)
    
    def set_charger_voltage_mode(self, instance: int, mode: str):
        """Set charger output voltage mode (absorption, float, storage)"""
        with self._lock:
            if instance not in self._manual_charger_params:
                self._manual_charger_params[instance] = {}
            self._manual_charger_params[instance]['voltage_mode'] = mode
            # Update simulator
            self.simulator.set_charger_output_voltage_mode(instance, mode)
    
    def set_charger_output_current(self, instance: int, current: float):
        """Set charger output current"""
        with self._lock:
            if instance not in self._manual_charger_params:
                self._manual_charger_params[instance] = {}
            self._manual_charger_params[instance]['output_current'] = float(current)
            # Update simulator
            self.simulator.set_charger_output_current(instance, current)
    
    def set_charger_manual_params(self, instance: int, params: Dict):
        """Set manual DC-DC charger parameters for simulation (editable via Web UI)"""
        with self._lock:
            if instance not in self._manual_charger_params:
                self._manual_charger_params[instance] = {}
            if 'input_voltage' in params:
                self._manual_charger_params[instance]['input_voltage'] = float(params['input_voltage'])
            if 'input_current' in params:
                self._manual_charger_params[instance]['input_current'] = float(params['input_current'])
            if 'output_voltage' in params:
                self._manual_charger_params[instance]['output_voltage'] = float(params['output_voltage'])
            # Update simulator
            self.simulator.set_charger_manual_params(instance, self._manual_charger_params[instance])
    
    def get_mppt_manual_params(self, instance: int) -> Dict:
        """Get manual MPPT parameters"""
        with self._lock:
            return self._manual_mppt_params.get(instance, {})
    
    def get_charger_manual_params(self, instance: int) -> Dict:
        """Get manual DC-DC charger parameters"""
        with self._lock:
            return self._manual_charger_params.get(instance, {})
        
    def set_cycle_period(self, period: float):
        """Update simulation cycle period"""
        with self._lock:
            self.cycle_period = max(1.0, min(10.0, period))
            self.simulator.set_cycle_period(self.cycle_period)
        
    def get_status(self) -> Dict:
        """Get current simulation status including configuration and runtime values"""
        with self._lock:
            _logger.debug(f"get_status: mppt_configs={list(self.mppt_configs.keys())}, charger_configs={list(self.charger_configs.keys())}")
            status = {
                'is_running': self._is_running,
                'cycle_period': self.cycle_period,
                'consumption': {
                    'type': self.consumption_config.consumption_type,
                    'constant': self.consumption_config.constant_consumption,
                    'min': self.consumption_config.min_consumption,
                    'max': self.consumption_config.max_consumption,
                    'variation_interval': self.consumption_config.variation_interval
                },
                # Configuration for each device type
                'mppt_configs': {str(k): {
                    'panel_voltage_min': v.panel_voltage_min,
                    'panel_voltage_max': v.panel_voltage_max,
                    'panel_voltage_max_power': v.panel_voltage_max_power,
                    'max_output': v.max_output_voltage,
                    'max_power': v.max_panel_power,
                    'voltage_factor': v.voltage_factor,
                    'output_power_factor': v.output_power_factor,
                    'min_voltage_delta': v.min_voltage_delta
                } for k, v in self.mppt_configs.items()},
                'charger_configs': {str(k): {
                    'efficiency': v.charger_efficiency,
                    'alternator_voltage': v.alternator_voltage,
                    'aux_voltage': v.aux_voltage,
                    'absorption_voltage': v.absorption_voltage,
                    'float_voltage': v.float_voltage,
                    'storage_voltage': v.storage_voltage,
                    'min_output_current': v.min_output_current,
                    'max_output_current': v.max_output_current
                } for k, v in self.charger_configs.items()},
                # Manual parameters
                'manual_mppt_params': {str(k): v for k, v in self._manual_mppt_params.items()},
                'manual_charger_params': {str(k): v for k, v in self._manual_charger_params.items()},
                # Runtime values from last simulation cycle
                'runtime': self._last_results
            }
            
            # Add battery configuration
            if self.battery_config:
                status['battery_config'] = {
                    'voltage_100pct': self.battery_config.voltage_100pct,
                    'voltage_0pct': self.battery_config.voltage_0pct,
                    'charging_efficiency': self.battery_config.charging_efficiency,
                    'initial_soc': self.battery_config.initial_soc,
                    'nominal_capacity': self.battery_config.nominal_capacity,
                    'nominal_voltage': self.battery_config.nominal_voltage
                }
            else:
                status['battery_config'] = None
            
            return status


class EnergySimulatorHTTPHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for Energy Simulator Web UI
    
    Provides REST API for:
    - Starting/stopping simulation
    - Getting/setting configuration
    - Getting simulation status
    """
    
    # Reference to the simulator engine (set after server creation)
    simulator_engine = None
    
    @classmethod
    def set_engine(cls, engine):
        """Set the simulator engine reference"""
        cls.simulator_engine = engine
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        _logger.debug("%s - %s" % (self.address_string(), format % args))
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            if self.path == '/api/status':
                self._handle_status()
            elif self.path == '/api/config':
                self._handle_config()
            elif self.path.startswith('/api/start'):
                self._handle_start()
            elif self.path.startswith('/api/stop'):
                self._handle_stop()
            else:
                self._serve_static()
        except Exception as e:
            self._send_error(500, str(e))
    
    def do_POST(self):
        """Handle POST requests"""
        try:
            if self.path == '/api/battery':
                self._handle_battery_config()
            elif self.path == '/api/consumption':
                self._handle_consumption_config()
            elif self.path.startswith('/api/mppt/'):
                self._handle_mppt_config()
            elif self.path.startswith('/api/charger/'):
                self._handle_charger_config()
            elif self.path.startswith('/api/mppt_manual/'):
                self._handle_mppt_manual_config()
            elif self.path.startswith('/api/mppt_enabled/'):
                self._handle_mppt_enabled_config()
            elif self.path.startswith('/api/charger_manual/'):
                self._handle_charger_manual_config()
            elif self.path.startswith('/api/charger_enabled/'):
                self._handle_charger_enabled_config()
            elif self.path.startswith('/api/charger_mode/'):
                self._handle_charger_mode_config()
            elif self.path.startswith('/api/charger_current/'):
                self._handle_charger_current_config()
            elif self.path == '/api/cycle_period':
                self._handle_cycle_period()
            elif self.path == '/api/start':
                self._handle_start()
            elif self.path == '/api/stop':
                self._handle_stop()
            else:
                self._send_error(404, "Not Found")
        except Exception as e:
            self._send_error(500, str(e))
    
    def _send_json(self, data: Dict, status: int = 200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))
    
    def _send_error(self, status: int, message: str):
        """Send error response"""
        self._send_json({'error': message}, status)
    
    def _serve_static(self):
        """Serve static files from the web_server/static directory"""
        import os
        
        # Map paths to static directory
        static_dir = '/mnt/meaban/Sterwen-Tech-SW/navigation_server/navigation_server/web_server/static'
        
        if self.path == '/':
            self.path = '/energy_simulator.html'
        
        file_path = os.path.join(static_dir, self.path.lstrip('/'))
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                # Guess content type
                if file_path.endswith('.html'):
                    content_type = 'text/html'
                elif file_path.endswith('.css'):
                    content_type = 'text/css'
                elif file_path.endswith('.js'):
                    content_type = 'application/javascript'
                elif file_path.endswith('.json'):
                    content_type = 'application/json'
                else:
                    content_type = 'application/octet-stream'
                
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self._send_error(500, str(e))
        else:
            self._send_error(404, "Not Found")
    
    def _handle_status(self):
        """Handle /api/status request"""
        if self.simulator_engine:
            status = self.simulator_engine.get_status()
            self._send_json(status)
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_config(self):
        """Handle /api/config request"""
        # For now, return the status which includes config
        self._handle_status()
    
    def _handle_start(self):
        """Handle /api/start request"""
        if self.simulator_engine:
            self.simulator_engine.start()
            self._send_json({'status': 'started', 'is_running': True})
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_stop(self):
        """Handle /api/stop request"""
        if self.simulator_engine:
            self.simulator_engine.stop()
            self._send_json({'status': 'stopped', 'is_running': False})
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _read_json_body(self) -> Dict:
        """Read JSON body from request"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))
    
    def _handle_battery_config(self):
        """Handle /api/battery POST request"""
        if self.simulator_engine:
            data = self._read_json_body()
            self.simulator_engine.set_battery_config(data)
            self._send_json({'status': 'ok', 'config': data})
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_consumption_config(self):
        """Handle /api/consumption POST request"""
        if self.simulator_engine:
            data = self._read_json_body()
            self.simulator_engine.set_consumption_config(data)
            self._send_json({'status': 'ok', 'config': data})
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_mppt_config(self):
        """Handle /api/mppt/{instance} POST request"""
        if self.simulator_engine:
            # Extract instance from path
            parts = self.path.split('/')
            if len(parts) >= 3:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    self.simulator_engine.set_mppt_config(instance, data)
                    self._send_json({'status': 'ok', 'instance': instance, 'config': data})
                except ValueError:
                    self._send_error(400, "Invalid instance ID")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_charger_config(self):
        """Handle /api/charger/{instance} POST request"""
        if self.simulator_engine:
            # Extract instance from path
            parts = self.path.split('/')
            if len(parts) >= 3:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    self.simulator_engine.set_charger_config(instance, data)
                    self._send_json({'status': 'ok', 'instance': instance, 'config': data})
                except ValueError:
                    self._send_error(400, "Invalid instance ID")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_cycle_period(self):
        """Handle /api/cycle_period POST request"""
        if self.simulator_engine:
            data = self._read_json_body()
            period = data.get('period', 2.0)
            try:
                period = float(period)
                self.simulator_engine.set_cycle_period(period)
                self._send_json({'status': 'ok', 'cycle_period': period})
            except (ValueError, TypeError):
                self._send_error(400, "Invalid cycle period")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_mppt_manual_config(self):
        """Handle /api/mppt_manual/{instance} POST request"""
        if self.simulator_engine:
            parts = self.path.split('/')
            if len(parts) >= 4:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    self.simulator_engine.set_mppt_manual_params(instance, data)
                    self._send_json({'status': 'ok', 'instance': instance, 'params': data})
                except ValueError:
                    self._send_error(400, "Invalid instance ID")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_mppt_enabled_config(self):
        """Handle /api/mppt_enabled/{instance} POST request"""
        if self.simulator_engine:
            parts = self.path.split('/')
            if len(parts) >= 4:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    self.simulator_engine.set_mppt_enabled(instance, bool(data.get('enabled', True)))
                    self._send_json({'status': 'ok', 'instance': instance, 'enabled': data.get('enabled', True)})
                except ValueError:
                    self._send_error(400, "Invalid instance ID")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_charger_enabled_config(self):
        """Handle /api/charger_enabled/{instance} POST request"""
        if self.simulator_engine:
            parts = self.path.split('/')
            if len(parts) >= 4:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    self.simulator_engine.set_charger_enabled(instance, bool(data.get('enabled', True)))
                    self._send_json({'status': 'ok', 'instance': instance, 'enabled': data.get('enabled', True)})
                except ValueError:
                    self._send_error(400, "Invalid instance ID")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_charger_mode_config(self):
        """Handle /api/charger_mode/{instance} POST request"""
        if self.simulator_engine:
            parts = self.path.split('/')
            if len(parts) >= 4:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    mode = data.get('mode', 'absorption')
                    self.simulator_engine.set_charger_voltage_mode(instance, mode)
                    self._send_json({'status': 'ok', 'instance': instance, 'mode': mode})
                except ValueError:
                    self._send_error(400, "Invalid instance ID")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_charger_current_config(self):
        """Handle /api/charger_current/{instance} POST request"""
        if self.simulator_engine:
            parts = self.path.split('/')
            if len(parts) >= 4:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    current = float(data.get('current', 0.0))
                    self.simulator_engine.set_charger_output_current(instance, current)
                    self._send_json({'status': 'ok', 'instance': instance, 'current': current})
                except ValueError:
                    self._send_error(400, "Invalid instance ID or current value")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")
    
    def _handle_charger_manual_config(self):
        """Handle /api/charger_manual/{instance} POST request"""
        if self.simulator_engine:
            parts = self.path.split('/')
            if len(parts) >= 4:
                try:
                    instance = int(parts[3])
                    data = self._read_json_body()
                    self.simulator_engine.set_charger_manual_params(instance, data)
                    self._send_json({'status': 'ok', 'instance': instance, 'params': data})
                except ValueError:
                    self._send_error(400, "Invalid instance ID")
            else:
                self._send_error(400, "Instance ID required")
        else:
            self._send_error(500, "Simulator engine not initialized")


class EnergySimulatorTopServer(GenericTopServer, NavThread):
    """
    Top-level server for the Energy Simulator process
    
    This is the main server that is instantiated by server_main.py
    It extends GenericTopServer and runs in a NavThread
    """
    
    def __init__(self, opts):
        """
        Initialize the Energy Simulator top server
        
        Args:
            opts: Configuration options dictionary
        """
        GenericTopServer.__init__(self, opts)
        NavThread.__init__(self, name="energy_simulator_server", daemon=False)
        
        MessageServerGlobals.main_server = self
        
        # Extract configuration from opts
        self._web_port = opts.get('port', int, 8081)
        self._web_host = opts.get('host', str, "0.0.0.0")
        self._agent_host = opts.get('agent_host', str, None)
        self._grpc_port = opts.get('agent_port', int, 4545)
        self._energy_process = opts.get('energy_process', str, "Energy")
        self._energy_host = opts.get('energy_host', str, None)
        self._energy_port = opts.get('energy_port', int, 4505)

        # The secure flag is inherited from the global configuration so the
        # web server connects to the agent with the same TLS policy as the
        # rest of the deployment.
        config = MessageServerGlobals.configuration
        self._secure = config.client_secure_communications
        self._agent_client = GrpcClient.get_client(f"{self._agent_host}:{self._grpc_port}", use_request_id=False,
                                                   secure=self._secure)
        self._agent = AgentClient()
        self._agent_client.add_service(self._agent)
        # Create the simulation engine
        self._engine = EnergySimulatorEngine(opts)
        
        # Set up HTTP server
        self._http_server = None
        self._energy_client = None
        self._simulator_service = None

        
    def start(self) -> bool:
        """Start the Energy Simulator server"""
        # Set up GenericTopServer state (handled by GenericTopServer)

        # Set up HTTP handler
        EnergySimulatorHTTPHandler.set_engine(self._engine)
        
        # Create HTTP server
        self._http_server = HTTPServer(
            (self._web_host, self._web_port),
            EnergySimulatorHTTPHandler
        )
        

        # connect to agent
        if self._agent_host is not None:
            self._agent_client.connect()
            self._agent_client.wait_connect(5.0)
            try:
                energy_port = self._agent.get_port(self._energy_process)
                energy_address = f"{self._agent_host}:{energy_port}"
            except GrpcAccessException:
                energy_port = 0
            if energy_port == 0:
                _logger.error(f"Failed to retrieve {self._energy_process} port => STOP")
                return False
        elif self._energy_host is not None:
            energy_address = f"{self._energy_host}:{self._energy_port}"
        else:
            _logger.error(f"Failed to retrieve {self._energy_process} port => STOP")
            return False

        # Connect to energy service and initialize engine before starting HTTP server
        self._energy_client = GrpcClient.get_client(energy_address, use_request_id=False, secure=self._secure)
        self._energy_client.connect()
        self._energy_client.wait_connect(5.0)
        if not self._energy_client.connected:
            _logger.error(f"Failed to connect to {self._energy_process} => STOP")
            return False
        self._engine.set_energy_client(self._energy_client)

        # Start simulation engine
        self._engine.start()
        
        _logger.info(f"Energy Simulator server starting on http://{self._web_host}:{self._web_port}")
        NavThread.start(self)
        
        _logger.info("Energy Simulator server started")
        return True
    
    def nrun(self):
        """Run the HTTP server in the NavThread"""
        self._http_server.serve_forever()

    def wait(self):
        """Wait for the server to stop"""
        # Blocks the main thread until the NavThread stops (SIGINT or explicit stop).
        self.join()
        _logger.info("Energy Simulator main loop ended")
        self._is_running = False

    def stop_server(self):
        """Stop the server"""
        _logger.info("Stopping Energy Simulator server")
        
        self._engine.stop()
        
        if self._http_server:
            self._http_server.shutdown()
            self._http_server = None
        
        if self._energy_client:
            self._energy_client.close()
            self._energy_client = None
        
        _logger.info("Energy Simulator server stopped")

    @property
    def console_present(self):
        """No console service for a pure web server process"""
        return False

    def is_agent(self):
        """This is not the agent"""
        return False
