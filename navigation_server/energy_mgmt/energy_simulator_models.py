#-------------------------------------------------------------------------------
# Name:        energy_simulator_models.py
# Purpose:     Simulation models for Energy Simulator devices
#              Implements algorithms for Battery, MPPT, DC-DC Charger, and Consumption simulation
#
# Author:      Vibe Code
#
# Created:     05/10/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_logger = logging.getLogger("ShipDataServer." + __name__)


@dataclass
class BatterySimulationConfig:
    """Configuration for battery simulation"""
    voltage_100pct: float = 14.4  # Voltage at 100% SoC
    voltage_0pct: float = 10.0    # Voltage at 0% SoC
    charging_efficiency: float = 0.9  # Efficiency (0-1)
    initial_soc: float = 0.8      # Initial State of Charge (0-1)
    nominal_capacity: float = 200.0  # Ah capacity
    nominal_voltage: float = 12.0  # Nominal voltage
    max_charge_current: float = 50.  # max charging current (A)


@dataclass
class BatterySimulationState:
    """Runtime state for battery simulation"""
    soc: float = 0.8  # Current State of Charge (0-1)
    last_update: float = 0.0
    energy_wh: float = 0.0  # Current energy in Wh


class BatterySimulator:
    """
    Simulates a battery bank with configurable parameters
    
    Algorithm:
    - Voltage is computed based on SoC with linear interpolation between voltage_100pct and voltage_0pct
    - Current input updates the SoC based on energy variation
    - Energy = SoC * nominal_capacity * nominal_voltage (in Wh)
    """
    
    def __init__(self, config: BatterySimulationConfig):
        self.config = config
        self.state = BatterySimulationState(soc=config.initial_soc)
        self.state.energy_wh = self._calculate_energy()
        self.state.last_update = time.monotonic()
        
    def _calculate_energy(self) -> float:
        """Calculate current energy in Wh"""
        return self.state.soc * self.config.nominal_capacity * self.config.nominal_voltage
    
    def _calculate_voltage(self) -> float:
        """Calculate voltage based on SoC with linear interpolation"""
        return self.config.voltage_0pct + \
               (self.config.voltage_100pct - self.config.voltage_0pct) * self.state.soc
    
    def update(self, current: float, delta_time: float) -> Dict:
        """
        Update battery state based on current flow
        
        Args:
            current: Current in amperes (positive = charging)
            delta_time: Time since last update in seconds
            
        Returns:
            Dictionary with voltage, current, power, soc
        """
        # Calculate energy variation in Wh (accounting for charging efficiency)
        if current > 0:  # Charging
            # here we need to limit the current to the max charging current and the max versus SoC
            if self.state.soc >= 1.0:
                current = 0.0
                self.state.soc = 1.0
                energy_variation_wh = 0.0
            else:
                current = min(current, self.config.max_charge_current)
                if self.state.soc >= 0.9:
                    # we need to limit the current
                    current = self.config.max_charge_current * (1.0 - self.state.soc)
                    current = min(current, self.config.max_charge_current / 10.)
                energy_variation_wh = current * self.config.nominal_voltage * (delta_time / 3600.0) * self.config.charging_efficiency
        else:  # Discharging
            energy_variation_wh = current * self.config.nominal_voltage * (delta_time / 3600.0)
        
        # Update SoC
        energy_capacity_wh = self.config.nominal_capacity * self.config.nominal_voltage
        self.state.soc = max(0.0, min(1.0, self.state.soc + energy_variation_wh / energy_capacity_wh))
        self.state.energy_wh = self._calculate_energy()
        self.state.last_update = time.monotonic()
        
        voltage = self._calculate_voltage()
        power = voltage * current
        
        return {
            'voltage': voltage,
            'current': current,
            'power': power,
            'state_of_charge': self.state.soc,
            'energy': self.state.energy_wh
        }
    
    def get_state(self) -> Dict:
        """Get current battery state"""
        return {
            'voltage': self._calculate_voltage(),
            'current': 0.0,
            'power': 0.0,
            'state_of_charge': self.state.soc,
            'energy': self.state.energy_wh
        }


@dataclass
class ConsumptionSimulationConfig:
    """Configuration for consumption simulation"""
    consumption_type: str = 'constant'  # 'constant' or 'variable'
    constant_consumption: float = 100.0  # Watts (for constant mode)
    min_consumption: float = 50.0  # Watts (for variable mode)
    max_consumption: float = 150.0  # Watts (for variable mode)
    variation_interval: float = 30.0  # Seconds between variations (for variable mode)
    random_seed: Optional[int] = None  # Random seed for reproducibility


@dataclass
class ConsumptionSimulationState:
    """Runtime state for consumption simulation"""
    current_consumption: float = 0.0
    last_variation: float = 0.0
    rng: Optional[random.Random] = None


class ConsumptionSimulator:
    """
    Simulates power consumption with constant or variable modes
    """
    
    def __init__(self, config: ConsumptionSimulationConfig):
        self.config = config
        self.state = ConsumptionSimulationState()
        self.state.current_consumption = config.constant_consumption if config.consumption_type == 'constant' else config.min_consumption
        
        if config.random_seed is not None:
            self.state.rng = random.Random(config.random_seed)
        else:
            self.state.rng = random.Random()
        
        self.state.last_variation = time.monotonic()
        
    def update(self) -> float:
        """
        Update consumption value
        
        Returns:
            Current consumption in watts (positive value)
        """
        now = time.monotonic()
        
        if self.config.consumption_type == 'variable':
            if now - self.state.last_variation >= self.config.variation_interval:
                # Generate new random consumption between min and max
                self.state.current_consumption = self.state.rng.uniform(
                    self.config.min_consumption, 
                    self.config.max_consumption
                )
                self.state.last_variation = now
        
        return self.state.current_consumption


@dataclass
class MPPTSimulationConfig:
    """Configuration for MPPT simulation"""
    panel_voltage_min: float = 15.0  # Minimum panel voltage (V)
    panel_voltage_max: float = 20.0  # Maximum panel voltage (V)
    panel_voltage_max_power: float = 18.5  # Panel voltage for max production (V)
    max_output_voltage: float = 14.4  # Maximum output voltage (V)
    max_panel_power: float = 300.0  # Maximum panel power (W)
    voltage_factor: float = 0.1  # Volt decrease per W of missed production
    output_power_factor: float = 0.95  # Power decrease factor based on voltage delta
    min_voltage_delta: float = 0.5  # Minimum voltage delta for production (V)


@dataclass
class MPPTSimulationState:
    """Runtime state for MPPT simulation"""
    panel_voltage: float = 0.0  # Current panel voltage from UI
    last_update: float = 0.0


class MPPTSimulator:
    """
    Simulates an MPPT solar charger
    
    Algorithm (from spec):
    1) If panel_voltage < system_voltage + min_voltage_delta => MPPT is off
    2) Compute theoretical production (W)
    3) Compute output voltage using voltage_factor
    4) If output_voltage < system_voltage, MPPT is off
    5) Compute output current/power using power_factor
    """
    
    def __init__(self, config: MPPTSimulationConfig):
        self.config = config
        self.state = MPPTSimulationState()
        # Initialize panel_voltage to midpoint between min and max to match slider default
        self.state.panel_voltage = (config.panel_voltage_min + config.panel_voltage_max) / 2
        self.state.last_update = time.monotonic()
        
    def update(self, system_voltage: float, panel_voltage: Optional[float] = None, current_adjustment: float = 1.0) -> Dict:
        """
        Update MPPT state based on system voltage
        
        Args:
            system_voltage: Current system voltage (V)
            panel_voltage: Override panel voltage (V), uses state if None
            current_adjustment: Adjustment factor for output current/power
            
        Returns:
            Dictionary with panel_voltage, panel_power, output_voltage, output_current
        """
        if panel_voltage is not None:
            self.state.panel_voltage = panel_voltage
        
        # Step 1: Check if panel voltage is high enough
        if self.state.panel_voltage < system_voltage + self.config.min_voltage_delta:
            _logger.debug("MPPT: Panel voltage too low, MPPT is off")
            return {
                'panel_voltage': self.state.panel_voltage,
                'panel_power': 0.0,
                'output_voltage': system_voltage,
                'output_current': 0.0,
                'output_power': 0.0,
                'mppt_on': False
            }
        
        # Step 2: Compute theoretical production
        # Normalize panel voltage to 0-1 range between min and max_power voltage
        if self.state.panel_voltage <= self.config.panel_voltage_min:
            theoretical_power = 0.0
        elif self.state.panel_voltage >= self.config.panel_voltage_max_power:
            theoretical_power = self.config.max_panel_power
        else:
            # Linear interpolation up to max_power voltage
            normalized = (self.state.panel_voltage - self.config.panel_voltage_min) / \
                        (self.config.panel_voltage_max_power - self.config.panel_voltage_min)
            theoretical_power = normalized * self.config.max_panel_power
        
        # Step 3: Compute output voltage using voltage_factor
        # Voltage decrease is proportional to missed power relative to max power
        power_missed = self.config.max_panel_power - theoretical_power
        voltage_decrease = (power_missed / self.config.max_panel_power) * self.config.max_output_voltage * self.config.voltage_factor
        theoretical_output_voltage = self.config.max_output_voltage - voltage_decrease
        
        # Step 4: Check if output voltage is positive
        if theoretical_output_voltage <= 0:
            _logger.debug("MPPT: Output voltage non-positive, MPPT is off")
            return {
                'panel_voltage': self.state.panel_voltage,
                'panel_power': theoretical_power,
                'output_voltage': system_voltage,
                'output_current': 0.0,
                'output_power': 0.0,
                'mppt_on': False
            }
        
        # Step 5: Compute output current/power using power_factor
        voltage_delta = theoretical_output_voltage - system_voltage
        # Clamp output power to [0, theoretical_power] and avoid negative delta issues
        output_power = max(0, min(theoretical_power, theoretical_power * (1.0 - voltage_delta * self.config.output_power_factor)))
        # apply limitation factor
        output_power *= current_adjustment
        output_current = output_power / system_voltage if system_voltage > 0 else 0.0
        
        return {
            'panel_voltage': self.state.panel_voltage,
            'panel_power': theoretical_power,
            'output_voltage': system_voltage,
            'output_current': output_current,
            'output_power': output_power,
            'mppt_on': True
        }


@dataclass
class DCDChargerSimulationConfig:
    """Configuration for DC-DC charger simulation"""
    charger_efficiency: float = 0.92  # Charger efficiency (0-1)
    # Voltage sources
    alternator_voltage: float = 24.0  # Input voltage when ON (from alternator)
    aux_voltage: float = 24.0  # Input voltage when OFF (from auxiliary)
    # Output voltage modes
    absorption_voltage: float = 14.2  # Absorption mode voltage (V)
    float_voltage: float = 13.5  # Float mode voltage (V)
    storage_voltage: float = 13.0  # Storage mode voltage (V)
    # Output current limits
    min_output_current: float = 0.0  # Minimum output current (A)
    max_output_current: float = 20.0  # Maximum output current (A)


@dataclass
class DCDChargerSimulationState:
    """Runtime state for DC-DC charger simulation"""
    input_voltage: float = 0.0
    input_current: float = 0.0
    output_voltage: float = 0.0
    output_current: float = 0.0
    last_update: float = 0.0


class DCDChargerSimulator:
    """
    Simulates a DC-DC charger
    
    Algorithm:
    - ON/OFF state controlled via enabled parameter
    - When ON: output_voltage is selected from mode, output_current from slider
    - When ON: input_voltage = alternator_voltage, input_power = output_power / efficiency
    - When OFF: input_voltage = aux_voltage, output is 0
    - Input current = input_power / input_voltage
    """
    
    def __init__(self, config: DCDChargerSimulationConfig):
        self.config = config
        self.state = DCDChargerSimulationState()
        self.state.last_update = time.monotonic()
        # Default mode
        self.output_voltage_mode = 'absorption'  # Default to absorption mode
        
    def set_output_voltage_mode(self, mode: str):
        """Set the output voltage mode (absorption, float, storage)"""
        if mode in ['absorption', 'float', 'storage']:
            self.output_voltage_mode = mode
        
    def get_voltage_for_mode(self, mode: str) -> float:
        """Get the output voltage for a given mode"""
        if mode == 'absorption':
            return self.config.absorption_voltage
        elif mode == 'float':
            return self.config.float_voltage
        elif mode == 'storage':
            return self.config.storage_voltage
        else:
            return self.config.absorption_voltage  # Default
        
    def update(self, input_voltage: Optional[float] = None, input_current: Optional[float] = None, 
               output_voltage: Optional[float] = None, output_current: Optional[float] = None,
               system_voltage: float = 0.0, enabled: bool = True, battery_voltage: float = 0.0) -> Dict:
        """
        Update DC-DC charger state
        
        Args:
            input_voltage: Input voltage override (V), uses alternator_voltage if ON and None
            input_current: Input current override (A), computed if None
            output_voltage: Desired output voltage override (V), uses mode voltage if ON and None
            output_current: Desired output current override (A), uses slider value if ON and None
            system_voltage: Current system voltage (V) - for reference
            enabled: Whether the charger is enabled (ON/OFF state)
            battery_voltage: Current battery voltage (V) - for reference
            
        Returns:
            Dictionary with input_voltage, input_current, output_voltage, output_current, charger_on
        """
        # If disabled (OFF button clicked), return OFF state
        if not enabled:
            # When OFF: input_voltage = aux_voltage
            input_voltage = input_voltage if input_voltage is not None else self.config.aux_voltage
            return {
                'input_voltage': input_voltage,
                'input_current': 0.0,
                'output_voltage': system_voltage,
                'output_current': 0.0,
                'charger_on': False
            }
        
        # ON state: compute values
        # Get output voltage from mode or override
        if output_voltage is None:
            output_voltage = self.get_voltage_for_mode(self.output_voltage_mode)

        
        # Get output current from parameter or override (clamped to min/max)
        if output_current is None:
            output_current = 0.0
        else:
            # Clamp to min/max
            output_current = max(self.config.min_output_current, 
                                min(self.config.max_output_current, output_current))

        
        # Compute output power
        output_power = output_voltage * output_current
        
        # Compute input power (accounting for efficiency loss)
        input_power = output_power / self.config.charger_efficiency if self.config.charger_efficiency > 0 else 0.0
        
        # Get input voltage from parameter or config
        if input_voltage is None:
            input_voltage = self.config.alternator_voltage
        
        # Compute input current
        if input_voltage > 0:
            input_current = input_power / input_voltage
        else:
            input_current = 0.0
        
        # Store state
        self.state.input_voltage = input_voltage
        self.state.input_current = input_current
        self.state.output_voltage = output_voltage
        self.state.output_current = output_current
        self.state.last_update = time.monotonic()
        
        return {
            'input_voltage': input_voltage,
            'input_current': input_current,
            'output_voltage': output_voltage,
            'output_current': output_current,
            'charger_on': True
        }


class EnergySystemSimulator:
    """
    Main energy system simulator that coordinates all device simulations
    
    Implements the global energy equilibrium and system voltage calculation:
    - System voltage == Battery voltage if no current source is on
    - If one or more current sources are on, system voltage is max across all sources and battery
    - Current/Power equilibrium across devices
    """
    
    def __init__(self):
        self.battery = BatterySimulator(BatterySimulationConfig())
        self.consumption = ConsumptionSimulator(ConsumptionSimulationConfig())
        self.mpp_ts = {}  # instance -> MPPTSimulator
        self.chargers = {}  # instance -> DCDChargerSimulator
        
        # Manual override parameters (set via Web UI)
        self.manual_mppt_params = {}  # instance -> {'panel_voltage': float}
        self.manual_charger_params = {}  # instance -> {'input_voltage': float, 'input_current': float, 'output_voltage': float}
        
        self.system_voltage = 12.8  # Default system voltage
        self._battery_voltage = 12.8  # default battery voltage
        self.last_cycle_time = time.monotonic()
        self.cycle_period = 1.0  # Seconds between cycles
        
    def add_mppt(self, instance: int, config: MPPTSimulationConfig):
        """Add an MPPT simulator"""
        self.mpp_ts[instance] = MPPTSimulator(config)
        
    def add_charger(self, instance: int, config: DCDChargerSimulationConfig):
        """Add a DC-DC charger simulator"""
        self.chargers[instance] = DCDChargerSimulator(config)
    
    def set_mppt_manual_params(self, instance: int, params: Dict):
        """Set manual MPPT parameters (editable via Web UI)"""
        if instance not in self.manual_mppt_params:
            self.manual_mppt_params[instance] = {}
        self.manual_mppt_params[instance].update(params)
    
    def set_charger_manual_params(self, instance: int, params: Dict):
        """Set manual DC-DC charger parameters (editable via Web UI)"""
        if instance not in self.manual_charger_params:
            self.manual_charger_params[instance] = {}
        self.manual_charger_params[instance].update(params)
    
    def set_mppt_enabled(self, instance: int, enabled: bool):
        """Set MPPT enabled/disabled state"""
        if instance not in self.manual_mppt_params:
            self.manual_mppt_params[instance] = {}
        self.manual_mppt_params[instance]['enabled'] = enabled
    
    def set_charger_enabled(self, instance: int, enabled: bool):
        """Set charger enabled/disabled state"""
        if instance not in self.manual_charger_params:
            self.manual_charger_params[instance] = {}
        self.manual_charger_params[instance]['enabled'] = enabled
    
    def set_charger_output_voltage_mode(self, instance: int, mode: str):
        """Set charger output voltage mode (absorption, float, storage)"""
        if instance in self.chargers:
            self.chargers[instance].set_output_voltage_mode(mode)
        if instance not in self.manual_charger_params:
            self.manual_charger_params[instance] = {}
        self.manual_charger_params[instance]['voltage_mode'] = mode
    
    def set_charger_output_current(self, instance: int, current: float):
        """Set charger output current"""
        if instance not in self.manual_charger_params:
            self.manual_charger_params[instance] = {}
        self.manual_charger_params[instance]['output_current'] = current
    
    def configure_battery(self, config: BatterySimulationConfig):
        """Configure the battery simulator"""
        self.battery = BatterySimulator(config)
        
    def configure_consumption(self, config: ConsumptionSimulationConfig):
        """Configure the consumption simulator"""
        self.consumption = ConsumptionSimulator(config)
        
    def set_cycle_period(self, period: float):
        """Set the simulation cycle period in seconds"""
        self.cycle_period = max(1.0, min(10.0, period))  # Clamp to 1-10 seconds
        
    def run_cycle(self) -> Dict:
        """
        Run one simulation cycle
        
        Returns:
            Dictionary with all simulated values for all devices
        """
        now = time.monotonic()
        delta_time = now - self.last_cycle_time
        self.last_cycle_time = now
        
        results = {}
        
        # Update consumption
        consumption_power = self.consumption.update()
        
        # Collect all device currents and voltages
        device_voltages = []
        device_currents = []  # Positive = source (providing current), negative = sink
        
        # Battery always provides voltage reference
        battery_state = self.battery.get_state()
        self._battery_voltage = battery_state['voltage']
        device_voltages.append(self._battery_voltage)
        
        # Process MPPTs
        mppt_results = {}
        for instance, mppt in self.mpp_ts.items():
            # Check if MPPT is explicitly disabled via manual control
            manual_params = self.manual_mppt_params.get(instance, {})
            is_enabled = manual_params.get('enabled', None)  # None = automatic mode, False = disabled
            
            # If explicitly disabled (OFF button clicked), force OFF
            if is_enabled is False:
                mppt_result = {
                    'panel_voltage': mppt.state.panel_voltage,
                    'panel_power': 0.0,
                    'output_voltage': self._battery_voltage,
                    'output_current': 0.0,
                    'output_power': 0.0,
                    'mppt_on': False
                }
            else:
                # Automatic mode or enabled: use normal voltage checks
                # Manual panel_voltage is still respected
                if 'panel_voltage' in manual_params:
                    mppt_result = mppt.update(self._battery_voltage, panel_voltage=manual_params['panel_voltage'])
                else:
                    mppt_result = mppt.update(self._battery_voltage)
            mppt_results[instance] = mppt_result
            
            if mppt_result['mppt_on']:
                device_voltages.append(mppt_result['output_voltage'])
                device_currents.append(mppt_result['output_current'])  # Positive = source
            else:
                device_currents.append(0.0)
        
        # Process DC-DC chargers
        charger_results = {}
        for instance, charger in self.chargers.items():
            # Use manual parameters if set, otherwise use defaults
            manual_params = self.manual_charger_params.get(instance, {})
            
            # Check if charger is enabled (ON/OFF state)
            is_enabled = manual_params.get('enabled', True)  # Default to enabled
            
            # Get output current from manual params if set
            output_current = manual_params.get('output_current', None)
            
            # Get output voltage from manual params or mode
            output_voltage = manual_params.get('output_voltage', None)
            
            charger_result = charger.update(
                input_voltage=manual_params.get('input_voltage', None),
                input_current=None,  # Will be computed from output
                output_voltage=output_voltage,
                output_current=output_current,
                system_voltage=self._battery_voltage,
                enabled=is_enabled,
                battery_voltage=self._battery_voltage
            )
            charger_results[instance] = charger_result
            
            # Only add to device voltages/currents if charger is ON
            if charger_result.get('charger_on', False):
                device_voltages.append(charger_result['output_voltage'])
                device_currents.append(charger_result['output_current'])  # Positive = source
            else:
                device_currents.append(0.0)
        
        # Calculate system voltage (max of all device voltages)
        self.system_voltage = max(device_voltages) if device_voltages else self._battery_voltage
        
        # Calculate total source current (from MPPTs and chargers)
        total_source_current = sum(c for c in device_currents if c > 0)

        consumption_current = consumption_power / self.system_voltage
        # Calculate battery current based on equilibrium
        # Case 1: No current source is on
        if total_source_current == 0:
            battery_current = -consumption_current if self.system_voltage > 0 else 0.0
            
        # Case 2: Sources are on but sum <= consumption
        elif total_source_current <= consumption_current:
            battery_current = total_source_current - consumption_current
            
        # Case 3: Production current > consumption current
        else:
            battery_current = total_source_current - consumption_current


        # Update battery with calculated current
        battery_result = self.battery.update(battery_current, delta_time)
        _logger.debug(f"Production:{total_source_current:.2f} Consumption current {consumption_current:.2f} battery current: {battery_current:.2f}, battery result current: {battery_result['current']:.2f}")
        # now we need to check that the battery absorbed current is equal to the calculated current
        current_adjustment = 1.0
        if battery_current > 0.0 and battery_result['current'] < battery_current:
            _logger.debug(f"Battery is limiting the current to {battery_result['current']}, but calculated current is {battery_current}")
            # here we need to distribute the current constraints on all sources
            # let's do it proportionally
            if total_source_current > 0.0:
                adjusted_source_current = total_source_current - (battery_current - battery_result['current'])
                current_adjustment = adjusted_source_current / total_source_current
                _logger.debug(f"Adjusting source current by {current_adjustment} on total {total_source_current}")

        # Update all MPPTs with correct system voltage
        for instance, mppt in self.mpp_ts.items():
            # Check if MPPT is explicitly disabled via manual control
            manual_params = self.manual_mppt_params.get(instance, {})
            is_enabled = manual_params.get('enabled', None)  # None = automatic mode, False = disabled
            
            # If explicitly disabled (OFF button clicked), force OFF
            if is_enabled is False:
                mppt_result = {
                    'panel_voltage': mppt.state.panel_voltage,
                    'panel_power': 0.0,
                    'output_voltage': self.system_voltage,
                    'output_current': 0.0,
                    'output_power': 0.0,
                    'mppt_on': False
                }
            else:
                # Automatic mode or enabled: use normal voltage checks
                # Manual panel_voltage is still respected
                if 'panel_voltage' in manual_params:
                    mppt_result = mppt.update(self.system_voltage, panel_voltage=manual_params['panel_voltage'],
                                              current_adjustment=current_adjustment)
                else:
                    mppt_result = mppt.update(self.system_voltage, current_adjustment=current_adjustment)

            mppt_results[instance] = mppt_result
        
        # Update all chargers with correct system voltage
        for instance, charger in self.chargers.items():
            # Use manual parameters if set, otherwise use defaults
            manual_params = self.manual_charger_params.get(instance, {})
            
            # Check if charger is enabled (ON/OFF state)
            is_enabled = manual_params.get('enabled', True)  # Default to enabled
            
            # Get output current from manual params if set
            output_current = manual_params.get('output_current', None)
            if output_current is not None:
                output_current *= current_adjustment
            
            # Get output voltage from manual params or mode
            output_voltage = manual_params.get('output_voltage', None)
            
            charger_result = charger.update(
                input_voltage=manual_params.get('input_voltage', None),
                input_current=None,  # Will be computed from output
                output_voltage=output_voltage,
                output_current=output_current,
                system_voltage=self.system_voltage,
                enabled=is_enabled,
                battery_voltage=self._battery_voltage
            )
            charger_results[instance] = charger_result
        
        results = {
            'system_voltage': self.system_voltage,
            'consumption_power': consumption_power,
            'battery': battery_result,
            'mppts': mppt_results,
            'chargers': charger_results
        }
        
        return results
