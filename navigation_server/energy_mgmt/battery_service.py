#-------------------------------------------------------------------------------
# Name:        battery_service
# Purpose:     server connected to Victron SmartShunt devices via VEDirect (serial 19200baud)
#   Text protocol is handled for SmartShunt battery monitors
#
# Author:      Laurent Carré
#
# Created:     15/09/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
import traceback

from collections import namedtuple, deque

from navigation_server.generated.energy_pb2 import (battery_in_out, energy_request, BatteryBank, battery_response,
                                                  battery_trend_response, battery_trend_bucket,
                                                  EnergySource)
from navigation_server.generated.energy_pb2_grpc import BatteryServiceServicer, add_BatteryServiceServicer_to_server
from navigation_server.router_common import (GrpcService, MessageServerGlobals, resolve_ref, copy_protobuf_data,
                                             NavGenericMsg, N2K_MSG, fill_protobuf_from_dict)
from navigation_server.router_core import NMEA0183Sentences

from navigation_server.generated.nmea2000_classes_gen import Pgn127751Class

from .energy_base_service import EnergyDevice

_logger = logging.getLogger("ShipDataServer." + __name__)


class BatteryData:
    """
    Data structure for Victron SmartShunt battery monitor data
    Attribute names match protobuf field names for compatibility with copy_protobuf_data
    
    The device sends data in 2 consecutive messages:
    - Message 1: Static data (PID, V, VS, I, P, CE, SOC, TTG, Alarm, etc.) + some dynamic
    - Message 2: Historical/dynamic data (H1, H2, H3, H4, H5, H6, H7, H8, H9, H10, etc.)
    
    This class handles both messages and only marks data as complete when both are received.
    """
    def __init__(self):
        # Initialization flag
        self._initialized = False
        
        # Default values for all fields
        # Battery voltage in Volts
        self.voltage = 0.0
        # Battery current in Amps (positive = charge, negative = discharge)
        self.current = 0.0
        # Instantaneous power in Watts
        self.power = 0.0
        # State of Charge in percent
        self.state_of_charge = 0.0
        # Energy variation in Wh
        self.energy_variation = 0.0
        # Auxiliary voltage
        self.auxiliary_voltage = 0.0
        
        # Additional battery information (for BatteryBank protobuf)
        self.min_voltage = 0.0
        self.max_voltage = 0.0
        self.charge_voltage = 0.0
        
        # Other fields
        self.consumed_ah = 0.0
        self.time_to_go = 0.0
        self.product_id = 'Unknown'
        self.firmware = 'Unknown'
        self.model = 'Unknown'
        self.alarm = None
        self.last_discharge_voltage = 0.0
        self.total_ah = 0.0
        self.charge_cycles = 0
        self.deepest_discharge = 0.0
        self.last_discharge = 0.0
        # Track which message types have been received
        self._has_message1 = False
        # Timestamp
        self.timestamp = time.monotonic()

    def _process_static(self, value_dict):

        try:
            self.product_id = value_dict['PID']
            self.firmware = value_dict['FW']
            self.model = value_dict['BMV']
        except KeyError:
            _logger.warning(f'Missing static data in battery message {value_dict}')
            raise

    def _process_msg1(self, value_dict):

        try:
            self.alarm = value_dict['Alarm']
            # Dynamic data from message1
            self.voltage = float(value_dict['V']) * 0.001
            self.current = float(value_dict['I']) * 0.001
            self.power = float(value_dict['P'])
            self.state_of_charge = float(value_dict['SOC']) * 0.01
            self.consumed_ah = float(value_dict['CE']) *0.001
            self.time_to_go = float(value_dict['TTG'])
            self.auxiliary_voltage = float(value_dict['VS']) * 0.001
        except KeyError:
            _logger.warning(f'Missing data in battery message 1 {value_dict}')
            raise

    def _process_msg2(self, value_dict):
        try:
            self.min_voltage = float(value_dict['H7']) * 0.001
            self.max_voltage = float(value_dict['H8']) * 0.001
            self.charge_voltage = float(value_dict['H10']) * 0.001
            self.last_discharge_voltage = float(value_dict['H9']) * 0.001
            self.total_ah = float(value_dict['H6']) * 0.001
            self.charge_cycles = int(value_dict['H4'])
            self.deepest_discharge = float(value_dict['H1']) * 0.001
            self.last_discharge = float(value_dict['H2']) * 0.001
        except KeyError:
            _logger.warning(f'Missing data in battery message 2 {value_dict}')
            raise

    
    def process_msg(self, value_dict) -> bool:
        """Process a message and return True if all data is complete.
        
        Message 1 contains: PID, V, VS, I, P, CE, SOC, TTG, Alarm, FW, SER#, etc.
        Message 2 contains: H1, H2, H3, H4, H5, H6, H7, H8, H9, H10, etc.
        
        Returns True only after both message types have been processed.
        If not initialized and first message is message2, it's ignored.
        """
        if not self._initialized:
            if 'PID' in value_dict:
                try:
                    self._process_static(value_dict)
                    self._process_msg1(value_dict)
                except KeyError:
                    return False
                self._initialized = True
                self._has_message1 = True
                return True
            else:
                return False

        if self._has_message1:
            # we have the message1, so let's go for the 2
            _logger.debug("BatteryService Processing message2")
            if not 'H1' in value_dict:
                _logger.warning("BatteryService Missing H1 in message wrong sequence")
                return False
            else:
                try:
                    self._process_msg2(value_dict)
                except KeyError:
                    return False
                self._has_message1 = False
                self.timestamp = time.monotonic()
                return True
        else:
            _logger.debug("BatteryService processing  message1")
            try:
                self._process_msg1(value_dict)
                self._has_message1 = True
            except KeyError:
                return False
            return False

    def output_pb(self, output_pb):
        """Fill battery_in_out protobuf with current values using copy_protobuf_data"""
        # battery_in_out has: voltage, current, energy_variation, auxiliary_voltage
        copy_protobuf_data(self, output_pb, ('voltage', 'current', 'energy_variation', 'auxiliary_voltage'))

    def output_info_pb(self, output_pb):
        """Fill BatteryBank protobuf with device information using copy_protobuf_data"""
        # BatteryBank fields that we have: voltage, state_of_charge, min_voltage, max_voltage, charge_voltage
        copy_protobuf_data(self, output_pb, ('voltage', 'state_of_charge', 'min_voltage', 'max_voltage', 'charge_voltage'))


BatteryBucket = namedtuple('BatteryBucket', ['timestamp', 'voltage', 'current', 'power', 'state_of_charge', 'energy_variation'])


class BatteryOnVictronSmartShunt(EnergyDevice):
    """
    Service class for Victron SmartShunt battery monitor
    Extends EnergyDevice with battery-specific functionality
    """
    
    # Battery energy source type - batteries are not energy sources but consumers/providers
    # They are managed separately in the EnergyController

    def __init__(self, opts, service):
        # Initialize base class
        super().__init__(opts, service)
        
        # Battery-specific parameters
        self._parameters = {
            'instance': self._instance,
            'nominal_voltage': opts.get('nominal_voltage', float, 12.0),
            'nominal_capacity': opts.get('nominal_capacity', float, 100.0),  # Ah
            'chemistry': opts.get('chemistry', str, 'Lead Acid'),
            'max_voltage': opts.get('max_voltage', float, 15.0),
            'min_voltage': opts.get('min_voltage', float, 10.0),
            'charge_voltage': opts.get('charge_voltage', float, 14.4),
            'max_charge_current': opts.get('max_charge_current', float, 50.0),
            'trend_duration': opts.get('trend_duration', int, 5),
            'trend_interval': self._trend_period,
            'reporting_interval': opts.get('reporting_interval', float, 1.0)
        }
        
        # Battery-specific tracking
        self._current_data = BatteryData()
        self._mean_v = 0.0
        self._mean_a = 0.0
        self._mean_p = 0.0
        self._mean_soc = 0.0
        self._mean_energy = 0.0
        self._nb_sample = 0
        self._last_voltage = 0.0
        self._last_ah = 0.0

    @property
    def device_type(self):
        return EnergySource.Battery

    def start(self):
        """Start the battery device"""
        # Call parent start
        super().start()

    def publish(self, msg):
        """Called by coupler when new data is available"""
        _logger.debug("VEDirect message:%s" % msg.msg)
        clock = time.monotonic()
        # Process the message and check if we have complete data
        if not self._current_data.process_msg(msg.msg):
            # Data not complete yet (waiting for both message1 and message2)
            return
        # we take into account only valid messages
        self._last_msg_ts = clock
        # Battery-specific processing - only after complete data is received
        if not self._communication_ok:
            # Communication restored, reset calculations
            self._mean_v = 0.0
            self._mean_a = 0.0
            self._mean_p = 0.0
            self._mean_soc = 0.0
            self._mean_energy = 0.0
            self._nb_sample = 0
            self._trend_buckets.clear()
            self._start_period = clock
            self._communication_ok = True

        # Accumulate samples for trend calculation
        self._mean_v += self._current_data.voltage
        self._mean_a += self._current_data.current
        self._mean_p += self._current_data.power
        self._mean_soc += self._current_data.state_of_charge
        
        # Calculate energy variation (Ah * voltage = Wh)
        # For SmartShunt, CE is consumed Ah, we track changes
        if self._last_ah != 0:
            # Energy variation in Wh (delta Ah * nominal voltage)
            delta_ah = self._last_ah - self._current_data.consumed_ah
            energy_variation = delta_ah * self._parameters.get('nominal_voltage', 12.0)
            self._mean_energy += energy_variation
        
        self._nb_sample += 1
        self._last_msg_ts = clock
        self._last_ah = self._current_data.consumed_ah
        self._last_voltage = self._current_data.voltage

        # Periodic trend bucket creation
        if clock - self._start_period >= self._trend_period and self._nb_sample > 0:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock))
            bucket = BatteryBucket(
                timestamp=timestamp,
                voltage=self._mean_v / self._nb_sample,
                current=self._mean_a / self._nb_sample,
                power=self._mean_p / self._nb_sample,
                state_of_charge=self._mean_soc / self._nb_sample,
                energy_variation=self._mean_energy if self._nb_sample > 0 else 0.0
            )
            self._trend_buckets.append(bucket)
            
            # Reset accumulators
            self._start_period = clock
            self._mean_v = 0.0
            self._mean_a = 0.0
            self._mean_p = 0.0
            self._mean_soc = 0.0
            self._mean_energy = 0.0
            self._nb_sample = 0

        # forward information through publisher
        if self._publish_function is not None:
            self._publish_function()

        # Report battery data to the energy controller
        if self._energy_controller is not None and self._current_data is not None:
            # Calculate power from voltage and current
            power = self._current_data.voltage * self._current_data.current
            # For batteries, positive current = charging
            self._energy_controller.battery_update(
                self._instance,
                self._current_data.current,
                power,
                self._current_data.state_of_charge,
                # Energy estimate: SoC * nominal_capacity * nominal_voltage (in Wh)
                (self._current_data.state_of_charge / 100.0) * 
                    self._parameters.get('nominal_capacity', 100.0) * 
                    self._parameters.get('nominal_voltage', 12.0),
                clock,
                self._current_data.voltage
            )

    def get_battery_values(self, output_pb):
        """Get current battery values"""
        if self._current_data is not None:
            self._current_data.output_pb(output_pb)


    def get_device_parameters(self, device_parameters):
        """Get device parameters"""
        fill_protobuf_from_dict(device_parameters, self._parameters)

    def publish0183(self):
        """Publish data in NMEA0183 format"""
        _logger.debug("Battery Service publish NMEA0183")
        # TODO: Implement NMEA0183 publishing for battery data
        # For now, just log the data
        if self._current_data:
            _logger.info(f"Battery: V={self._current_data.voltage:.2f}V, I={self._current_data.current:.2f}A, SOC={self._current_data.state_of_charge:.1f}%")

    def publish2000(self):
        """Publish data in NMEA2000 format"""
        _logger.debug("Battery Service publish NMEA2000")
        # Generate PGN 127751 (Battery Status)
        msg = Pgn127751Class()
        msg.sequence_id = self._sid % 256
        msg.connection_number = 1
        msg.voltage = self._current_data.voltage if self._current_data else 0.0
        msg.current = self._current_data.current if self._current_data else 0.0
        msg_sent = NavGenericMsg(N2K_MSG, msg=msg.message())
        self._publisher.publish(msg_sent)
        self._sid += 1

    def object_name(self):
        """For debug only"""
        traceback.print_stack()


class BatteryServicer(BatteryServiceServicer):
    """
    gRPC servicer for BatteryService
    """
    def __init__(self, battery_device):
        self._battery_device = battery_device

    def GetInformation(self, request, context):
        """Get battery bank information"""
        _logger.debug("GRPC request BatteryService.GetInformation")
        ret_data = battery_response()
        self._battery_device.get_device_info(ret_data.battery)
        if request.command:
            if request.command == 'parameters':
                self._battery_device.get_device_parameters(ret_data.battery)
        ret_data.response = 'OK'
        return ret_data

    def GetValues(self, request, context):
        """Get current battery values"""
        _logger.debug("GRPC request BatteryService.GetValues")
        ret_val = battery_in_out()
        self._battery_device.get_battery_values(ret_val)
        return ret_val

    def GetTrend(self, request, context):
        """Get battery trend data"""
        _logger.debug("GRPC request BatteryService.GetTrend")
        ret_values = battery_trend_response()
        ret_values.instance = self._battery_device.instance
        ret_values.nb_values = 0
        ret_values.interval = self._battery_device.trend_interval

        energy_var = []
        for bucket in self._battery_device.get_trend_buckets():
            ret_values.nb_values += 1
            val = battery_trend_bucket()
            val.timestamp = bucket.timestamp
            val.voltage = bucket.voltage
            val.energy_variation = bucket.energy_variation
            val.state_of_charge = bucket.state_of_charge
            val.power = bucket.power
            ret_values.samples.append(val)
            energy_var.append(bucket.power)

        _logger.info(f"Battery trend energy_var: {energy_var}")
        return ret_values


class BatteryService(GrpcService):
    """
    gRPC service for Victron SmartShunt battery monitors
    """

    def __init__(self, opts):
        super().__init__(opts)
        self._battery_device = BatteryOnVictronSmartShunt(opts, self)

    def finalize(self):
        super().finalize('Battery', 'BatteryService')
        add_BatteryServiceServicer_to_server(BatteryServicer(self._battery_device), self.grpc_server)
        self._battery_device.start()
