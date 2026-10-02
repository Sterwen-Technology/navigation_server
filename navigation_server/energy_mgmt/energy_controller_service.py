#-------------------------------------------------------------------------------
# Name:        energy_controller_service
# Purpose:     Energy Controller service - manages global view of electrical energy
#              Aggregates data from multiple energy sources and battery banks
#
# Author:      Laurent Carré
#
# Created:     23/09/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
import threading
from collections import deque, namedtuple


from navigation_server.generated.energy_pb2 import (
    EnergyControllerParameters, EnergyControllerData, EnergyControllerTrend,
    EnergySourceDevice, BatteryUnit, EnergySourceData, BatteryUnitData,
    energy_request, energy_command_response, EnergySource,
)
from navigation_server.generated.energy_pb2_grpc import (
    EnergyServiceServicer, add_EnergyServiceServicer_to_server
)
from navigation_server.router_common import GrpcService, copy_protobuf_data, fill_protobuf_from_dict
from navigation_server.energy_mgmt.energy_base_service import EnergyDevice

_logger = logging.getLogger("ShipDataServer." + __name__)


# NamedTuple to store device and its corresponding record (EnergySourceDevice or BatteryUnit)
device_record = namedtuple('device_record', ['device', 'record'])

def _get_source_type(source: EnergySource) -> str:
    return EnergySource.Name(source)

class EnergyController:
    """
    Energy Controller - manages the global view and summary of electrical energy
    Aggregates data from multiple energy sources (MPPT, DC-DC chargers, etc.)
    and battery banks to provide a consolidated view
    """

    def __init__(self, opts, service):
        """
        Initialize the energy controller
        
        Args:
            opts: Configuration options dictionary
            service: The parent EnergyService instance
        """
        self._name = opts.get('name', str, 'EnergyController')
        self._service = service
        
        # Configuration parameters
        self._nominal_main_voltage = opts.get('nominal_main_voltage', float, 12.0)
        self._nominal_auxiliary_voltage = opts.get('nominal_auxiliary_voltage', float, 12.0)
        self._maximum_main_voltage = opts.get('maximum_main_voltage', float, 15.0)
        self._minimum_main_voltage = opts.get('minimum_main_voltage', float, 10.0)
        
        # Trend tracking
        trend_duration = opts.get('trend_duration', int, 5)  # minutes
        self._trend_period = opts.get('trend_interval', float, 10.0)  # seconds
        self._trend_depth = int((trend_duration * 60.) / self._trend_period)
        self._trend_buckets = deque(maxlen=self._trend_depth)
        
        # Registered energy sources and battery units
        self._sources = {}  # instance_id -> EnergySourceDevice
        self._batteries = {}  # instance_id -> BatteryUnit
        self._source_data = {}  # instance_id -> {'current': float, 'power': float, 'timestamp': float}
        self._battery_data = {}  # instance_id -> {'current': float, 'power': float, 'soc': float, 'energy': float, 'timestamp': float}
        
        # Aggregated values
        self._main_voltage = 0.0
        self._auxiliary_voltage = 0.0
        self._production_power = 0.0
        self._consumption_power = 0.0
        self._energy_stock = 0.0
        self._battery_balance = 0.0

        # Aggregated values computing cycle control

        self._cycle_lock = threading.Lock()
        self._cycle_timer = None
        self._cycle_start_ts = None
        self._cycle_period = opts.get('cycle_period', float, 2.0)
        
        # Tracking
        self._start_period = 0.0
        self._last_update_ts = time.monotonic()
        self._communication_ok = True
        
        # Initialize from configuration if provided
        self._parameters = {
            'nominal_main_voltage': self._nominal_main_voltage,
            'nominal_auxiliary_voltage': self._nominal_auxiliary_voltage,
            'maximum_main_voltage': self._maximum_main_voltage,
            'minimum_main_voltage': self._minimum_main_voltage,
            'trend_duration': trend_duration,
            'trend_interval': self._trend_period
        }

    def stop_service(self):
        """Request to stop the service"""
        _logger.info(f"{self._name} request to stop service")
        self._service.stop_service()

    @property
    def trend_interval(self):
        """Get the trend interval in seconds"""
        return self._trend_period

    def get_trend_buckets(self):
        """Generator to yield trend buckets"""
        for b in self._trend_buckets:
            yield b

    def start(self):
        """Start the energy controller"""
        self._start_period = time.monotonic()
        self._start_cycle()
        _logger.info(f"{self._name} started")

    def _start_cycle(self):
        """Start the cycle timer"""
        self._cycle_timer = threading.Timer(self._cycle_period, self._process_cycle)
        self._cycle_timer.start()
        self._cycle_start_ts = time.monotonic()

    def _process_cycle(self):
        if self._cycle_lock.acquire(blocking=True, timeout=self._cycle_period):
            self._compute_aggregates()
            self._lock_errors = 0
            self._cycle_lock.release()
            self._start_cycle()
        else:
            _logger.warning(f"{self._name} cycle lock timeout")
            self._lock_errors += 1
            if self._lock_errors > 10:
                _logger.error(f"{self._name} cycle lock timeout exceeded 10 times, stopping cycle")
                self._cycle_timer.cancel()
                self._cycle_timer = None


    def register(self, device: EnergyDevice):
        """
        Register an energy source or battery unit
        
        Args:
            device: The device to register (MPPT, Battery, etc.)
        """
        _logger.info(f"{self._name} start registering device: {device.device_label} instance: {device.instance}, type: {_get_source_type(device.device_type)}")
        
        # For now, we assume the device has _instance and _device_label
        # The actual energy source type and data will be provided via source_update
        # Just track the device
        # first check if we have a battery
        if device.device_type == EnergySource.Battery:
            _logger.info(f"Existing batteries: {self._batteries}")
            if device.instance not in self._batteries:
                self._batteries[device.instance] = device_record(
                    device,BatteryUnit(instance_id=device.instance, label= device.device_label))
                _logger.info(f"{self._name} registered battery: {device.device_label}")
            else:
                _logger.warning(f"{self._name} battery already registered: {device.device_label}")
        elif (device.instance, device.device_type) not in self._sources:
            self._sources[(device.instance, device.device_type)] = device_record( device,
                                                                                  EnergySourceDevice (
                instance_id=device.instance,
                label=device.device_label,
                type=device.device_type
            ))
            _logger.info(f"{self._name} registered source: {device.device_label} instance: {device.instance}, type: {_get_source_type(device.device_type)}")
        else:
            _logger.warning(f"{self._name} source already registered: {device.device_label}")

    def source_update(self, instance: int, source_type: EnergySource, timestamp: float,
                     current: float, power: float, voltage: float):
        """
        Update energy source data
        
        Args:
            instance: The source instance ID
            source_type: The EnergySource enum value
            timestamp: The timestamp of the data
            current: Current in amps
            power: Power in watts
            voltage: Voltage in volts
        """
        if (instance, source_type) not in self._sources:
            _logger.error(f"Source update for unknown source instance {instance} and type {source_type}")
            return
        # Store the source data
        if self._cycle_lock.acquire(blocking=True, timeout=self._cycle_period):
            self._source_data[(instance, source_type)] = {
                'device_on': True,
                'communication_ok': True,
                'current': current,
                'power': power,
                'voltage': voltage,
                'timestamp': timestamp,
                'type': source_type
            }
            self._cycle_lock.release()
        else:
            _logger.error(f"Source update lock failed for {_get_source_type(source_type)}:{instance}")

    def set_off_state(self, instance: int, source_type: int, communication_ok: bool, device_on: bool):
        if (instance, source_type) not in self._sources:
            _logger.error(f"Source update for unknown source instance {instance} and type {_get_source_type(source_type)}")
            return
        self._source_data[(instance, source_type)] = {
            'communication_ok': communication_ok,
            'device_on': device_on,
            'current': 0.0,
            'power': 0.0,
            'voltage': 0.0,
            'timestamp': 0.0,
            'type': source_type
        }


    def battery_update(self, instance: int, current: float, power: float, 
                      state_of_charge: float, energy: float, timestamp: float, voltage: float):
        """
        Update battery unit data
        
        Args:
            instance: The battery instance ID
            current: Current in amps (positive = charging)
            power: Power in watts (positive = charging)
            state_of_charge: State of charge in percent
            energy: Energy in Wh
            timestamp: The timestamp of the data
            voltage: Voltage in volts
        """
        if instance not in self._batteries:
            _logger.warning(f"Battery instance {instance} not found")
            return
        # Store the battery data
        self._battery_data[instance] = {
            'current': current,
            'power': power,
            'state_of_charge': state_of_charge,
            'energy': energy,
            'timestamp': timestamp,
            'voltage': voltage
        }
        # Update the battery definition if not already set
        if instance not in self._batteries:
            self._batteries[instance] = BatteryUnit(
                instance_id=instance,
                label=f"Battery_{instance}"
            )
        
        # Mark that we have new data
        self._compute_aggregates()

    def _compute_aggregates(self):
        """
        Compute aggregated energy values from all registered sources and batteries
        """
        _logger.debug("EnergyController start computing energy aggregates")
        clock = time.monotonic()
        
        # Reset aggregates
        total_production = 0.0
        total_source_consumption = 0.0
        total_battery_power = 0.0
        total_energy_stock = 0.0
        main_voltage = 0.0

        
        # Process energy sources
        # _logger.debug(f"EnergyController processing energy sources #{len(self._source_data)}")
        for key, data in self._source_data.items():
            # Positive power = production, negative = consumption
            _logger.debug(f"EnergyController processing energy source {_get_source_type(key[1])}:{key[0]} with power {data['power']}")
            if not(data['device_on'] and data['communication_ok']):
                _logger.debug(f"EnergyController skipping source {_get_source_type(key[1])}:{key[0]} due to communication issues")
                continue
            if clock - data['timestamp'] > self._cycle_period:
                _logger.debug(f"EnergyController skipping source {_get_source_type(key[1])}:{key[0]} due to timeout")
                if clock - data['timestamp'] > self._cycle_period * 10:
                    _logger.warning(f"EnergyController skipping source {_get_source_type(key[1])}:{key[0]} is going off-line")
                    self.set_off_state(key[0], key[1], False, False)
                continue
            if data['power'] > 0:
                total_production += data['power']
            else:
                total_source_consumption += abs(data['power'])
            main_voltage = data['voltage']

        
        # Process battery units
        # _logger.debug(f"Energy Controller processing batteries #{len(self._battery_data)} ")
        for instance, data in self._battery_data.items():
            # Battery power: positive = charging (power into battery)
            total_battery_power += data['power']
            total_energy_stock += data['energy']
            main_voltage = data['voltage']
        
        # Battery balance: positive = net charging, negative = net discharging
        # This represents the net power flow to/from all batteries
        self._battery_balance = total_battery_power
        
        # Production power (from sources)
        self._production_power = total_production
        
        # Consumption power (from loads, excluding battery charging/discharging)
        self._consumption_power = total_source_consumption - total_battery_power + total_production
        
        # Energy stock (total available energy in all batteries)
        self._energy_stock = total_energy_stock
        
        # For now, main and auxiliary voltages are set to nominal values
        # These would be updated from actual measurements if available
        self._main_voltage = main_voltage
        self._auxiliary_voltage = 0.0
        
        # Create trend bucket if period has elapsed
        if clock - self._start_period >= self._trend_period:
            self._create_trend_bucket(clock)
            self._start_period = clock
        
        self._last_update_ts = clock
        self._communication_ok = True
        # _logger.debug("EnergyController finished computing energy aggregates")

    def _create_trend_bucket(self, timestamp: float):
        """
        Create a trend bucket with current aggregated values
        
        Args:
            timestamp: The timestamp for the bucket
        """
        bucket_data = EnergyControllerData()
        bucket_data.main_voltage = self._main_voltage
        bucket_data.auxiliary_voltage = self._auxiliary_voltage
        bucket_data.production_power = self._production_power
        bucket_data.consumption_power = self._consumption_power
        bucket_data.energy_stock = self._energy_stock
        bucket_data.battery_balance = self._battery_balance
        
        # Add source data
        for instance, data in self._source_data.items():
            source_data = EnergySourceData()
            source_data.instance = instance[0]
            source_data.current = data['current']
            source_data.power = data['power']
            source_data.communication_ok = data.get('communication_ok', True)
            source_data.device_on = data.get('device_on', True)
            bucket_data.sources_data.append(source_data)
        
        # Add battery data
        for instance, data in self._battery_data.items():
            battery_data = BatteryUnitData()
            battery_data.instance = instance
            battery_data.current = data['current']
            battery_data.power = data['power']
            battery_data.state_of_charge = data['state_of_charge']
            battery_data.energy = data['energy']
            bucket_data.batteries_data.append(battery_data)
        
        self._trend_buckets.append(bucket_data)

    def get_information(self,  response):
        """
        Get energy controller information and parameters
        
        Args:
            response: The EnergyControllerParameters to fill
        """
        fill_protobuf_from_dict(response, self._parameters)
        
        # Add registered sources
        for source in self._sources.values():
            _logger.debug(f"get_information source={source.device.device_label}; {source.record}")
            response.sources.append(source.record)
        
        # Add registered batteries
        for battery in self._batteries.values():
            response.batteries.append(battery.record)

    def get_values(self, response):
        """
        Get current energy controller values
        
        Args:
            response: The EnergyControllerData to fill
        """
        response.main_voltage = self._main_voltage
        response.auxiliary_voltage = self._auxiliary_voltage
        response.production_power = self._production_power
        response.consumption_power = self._consumption_power
        response.energy_stock = self._energy_stock
        response.battery_balance = self._battery_balance
        
        # Add source data
        for instance, data in self._source_data.items():
            source_data = EnergySourceData()
            source_data.instance = instance[0]
            source_data.current = data['current']
            source_data.power = data['power']
            source_data.communication_ok = data.get('communication_ok', True)
            source_data.device_on = data.get('device_on', True)
            response.sources_data.append(source_data)
        
        # Add battery data
        for instance, data in self._battery_data.items():
            battery_data = BatteryUnitData()
            battery_data.instance = instance
            battery_data.current = data['current']
            battery_data.power = data['power']
            battery_data.state_of_charge = data['state_of_charge']
            battery_data.energy = data['energy']
            response.batteries_data.append(battery_data)

    def get_trend(self, request, response):
        """
        Get energy controller trend data
        
        Args:
            request: The energy_request
            response: The EnergyControllerTrend to fill
        """
        response.nb_values = len(self._trend_buckets)
        response.interval = self._trend_period
        
        for bucket in self._trend_buckets:
            response.samples.append(bucket)

    def get_parameters(self, parameters_pb):
        fill_protobuf_from_dict(parameters_pb, self._parameters)

    def object_name(self):
        """For debug only"""
        return self._name


class EnergyServicer(EnergyServiceServicer):
    """
    gRPC servicer for EnergyService
    """
    
    def __init__(self, energy_controller):
        self._energy_controller = energy_controller

    def GetInformation(self, request, context):
        """Get energy controller information"""
        _logger.debug("gRPC request EnergyServicer.GetInformation")
        ret_data = EnergyControllerParameters()
        self._energy_controller.get_information(ret_data)
        _logger.debug(f"GetInformation ret_data={ret_data}")
        return ret_data

    def GetValues(self, request, context):
        """Get current energy controller values"""
        _logger.debug("gRPC request EnergyServicer.GetValues")
        ret_data = EnergyControllerData()
        self._energy_controller.get_values(ret_data)
        _logger.debug(f"GetValues ret_data={ret_data}")
        return ret_data

    def GetTrend(self, request, context):
        """Get energy controller trend data"""
        _logger.debug("gRPC request EnergyService.GetTrend")
        ret_data = EnergyControllerTrend()
        self._energy_controller.get_trend(request, ret_data)
        return ret_data


class EnergyService(GrpcService):
    """
    gRPC service for EnergyController
    Provides a consolidated view of all energy sources and battery banks
    """

    def __init__(self, opts):
        super().__init__(opts)
        self._energy_controller = EnergyController(opts, self)

    def finalize(self):
        super().finalize('Energy', 'EnergyService')
        add_EnergyServiceServicer_to_server(
            EnergyServicer(self._energy_controller), 
            self.grpc_server
        )
        self._energy_controller.start()

    def controller(self):
        return self._energy_controller
