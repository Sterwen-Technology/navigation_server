#-------------------------------------------------------------------------------
# Name:        dc_dc_service
# Purpose:     server connected to Victron devices via VEDirect (serial 19200baud)
#              Text protocol for Orion XS (SmartBuckboost compatible)
#
# Author:      Vibe Code
#
# Created:     10/10/2026
# Copyright:   (c) Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
import traceback

from collections import namedtuple, deque

from navigation_server.generated.energy_pb2 import (DC_DC_Charger_running_values, energy_request,
                                                    DC_DC_Charger_Parameters, DC_DC_Charger_trend,
                                                    EnergySource, VE_state, VE_Error, VE_Off_Reason,
                                                    energy_command_response)
from navigation_server.generated.energy_pb2_grpc import DC_DC_ServiceServicer, add_DC_DC_ServiceServicer_to_server
from navigation_server.router_common import (GrpcService, MessageServerGlobals, resolve_ref, copy_protobuf_data,
                                             NavGenericMsg, N2K_MSG, fill_protobuf_from_dict)
from navigation_server.router_core import NMEA0183Sentences
from navigation_server.couplers import VED_TEXT, VED_ASYNC_HEX, VED_RESP_HEX, VEDirectMsg

from .energy_base_service import EnergyDevice

_logger = logging.getLogger("ShipDataServer." + __name__)


class DC_DCData:
    """
    Data structure for Victron Orion XS DC-DC charger
    Based on VE.Direct protocol - SmartBuckboost column
    
    Initialize with default values and update via process_msg method
    """
    
    def __init__(self):
        """
        Initialize with default values
        """
        # Input side (from alternate battery/alternator)
        self.input_voltage = 0.0  # Input voltage in V
        self.input_current = 0.0  # Input current in A
        self.input_power = 0.0  # Calculated in W
        
        # Output side (to service battery)
        self.output_voltage = 0.0  # Output voltage in V
        self.output_current = 0.0  # Output current in A
        self.output_power = 0.0  # Calculated in W
        
        # Device information
        self.product_id = 'Unknown'
        self.firmware = 'Unknown'
        self.serial = 'Unknown'
        
        # State and error
        self.state = VE_state.Off  # VE_state
        self.error = VE_Error.no_error  # VE_Error
        self.off_reason = VE_Off_Reason.no_reason  # VE_Off_Reason
        
        # Additional Orion XS specific fields
        self.temperature = 0.0  # Temperature in °C
        self.mode = 0  # Operating mode

    def process_msg(self, msg: VEDirectMsg ):
        """
        Process a VE.Direct message and update data
        
        Args:
            msg: VEDirectMsg issued by the Coupler can be either Txt mode or HEX
            
        Returns:
            True when data has been updated
        """
        if msg.msg_type == VED_TEXT:
            value_dict = msg.msg
        else:
            # right now we don't support HEX mode
            return False

        try:
            self.state = int(value_dict['CS'])
            self.input_voltage = float(value_dict['DC_IN_V']) * 0.01  # 0.01 V units to V (Victron Orion XS format)
            if self.state != VE_state.Off:
            # Input side (from alternate battery/alternator)

                self.input_current = float(value_dict['DC_IN_I']) * 0.1  # 0.1 A units to A (Victron Orion XS format)
                self.input_power =   float(value_dict['DC_IN_P'])# Calculated in W
            else:
                self.input_current = 0.0
                self.input_power = 0.0
        except KeyError as err:
            _logger.error(f"VEDirect DCDC charger decode error: {err} on msg:{msg.printable()}")
            return False

        # Output side (to service battery)

        self.output_voltage = float(value_dict['V']) * 0.001  # 0.001 V units (mV) to V (Victron VE.Direct format)
        self.output_current = float(value_dict['I']) * 0.001  # 0.001 A units (mA) to A (Victron VE.Direct format)
        self.output_power =  float(value_dict['P']) # Calculated in W
        
        # Device information
        if 'PID' in value_dict:
            self.product_id = value_dict['PID']
        if 'FWE' in value_dict:
            self.firmware = value_dict['FWE']
        if 'SER#' in value_dict:
            self.serial = value_dict['SER#']
        
        # State and error
        if 'CS' in value_dict:
            self.state = int(value_dict['CS'])  # VE_state
        if 'ERR' in value_dict:
            self.error = int(value_dict['ERR'])  # VE_Error
        if 'OR' in value_dict:
            self.off_reason = int(value_dict['OR'], 16)  # VE_Off_Reason

        return True

    def running_values_pb(self, running_values_pb):
        """
        Fill protobuf DC_DC_Charger_running_values message with current data
        
        Args:
            running_values_pb: DC_DC_Charger_running_values protobuf message to fill
        """
        running_values_pb.state = self.state
        running_values_pb.error = self.error
        running_values_pb.off_reason = self.off_reason
        running_values_pb.communication_ok = True
        running_values_pb.input_voltage = self.input_voltage
        running_values_pb.input_current = self.input_current
        running_values_pb.input_power = self.input_power
        running_values_pb.output_voltage = self.output_voltage
        running_values_pb.output_current = self.output_current
        running_values_pb.output_power = self.output_power

    def parameters_pb(self, parameters_pb):
        """
        Fill protobuf DC_DC_Charger_Parameters message with device information
        
        Args:
            parameters_pb: DC_DC_Charger_Parameters protobuf message to fill
        """
        parameters_pb.device_label = f"Orion XS {self.serial}" if self.serial else "Orion XS"
        parameters_pb.device_model = self.product_id if self.product_id else "Unknown"
        parameters_pb.state = self.state
        parameters_pb.error = self.error
        parameters_pb.off_reason = self.off_reason
        parameters_pb.communication_ok = True


DC_DCBucket = namedtuple('DC_DCBucket', ['input_voltage', 'input_current', 'input_power',
                                         'output_voltage', 'output_current', 'output_power'])


class VictronDC_DC(EnergyDevice):
    """
    Victron Orion XS DC-DC charger device implementation
    Extends EnergyDevice with DC-DC charger-specific functionality
    """
    
    # DC-DC charger energy source type
    energy_source_type = EnergySource.DC_DC_Charger

    def __init__(self, opts, service):
        """
        Initialize DC-DC charger device
        
        Args:
            opts: Configuration options dictionary
            service: Parent service instance
        """
        # Initialize base class
        super().__init__(opts, service)
        
        # Initialize current data with default values
        self._current_data = DC_DCData()
        
        # DC-DC specific parameters
        self._parameters = {
            'instance': opts.get('instance', int, 0),
            'nominal_input_voltage': opts.get('nominal_input_voltage', float, 12.0),
            'nominal_output_voltage': opts.get('nominal_output_voltage', float, 12.0),
            'input_voltage_range': opts.get('input_voltage_range', float, 10.0),
            'output_voltage_range': opts.get('output_voltage_range', float, 15.0),
            'max_power': opts.get('max_power', float, 30.0),  # Typical for Orion XS
            'trend_duration': opts.get('trend_duration', int, 5),
            'trend_interval': self._trend_period
        }
        
        # DC-DC specific tracking
        self._input_power = 0.0
        self._output_power = 0.0
        self._mean_in_v = 0.0
        self._mean_in_a = 0.0
        self._mean_in_p = 0.0
        self._mean_out_v = 0.0
        self._mean_out_a = 0.0
        self._mean_out_p = 0.0
        self._nb_sample = 0

    @property
    def device_type(self):
        """
        Get the energy source type for this device

        Returns:
            EnergySource.DC_DC_Charger
        """
        return EnergySource.DC_DC_Charger

    def start(self):
        """Start the DC-DC charger device"""
        # Call parent start
        super().start()
        
        # DC-DC specific initialization
        if self._publisher is not None and self._protocol == 'nmea2000':
            self._sid = 0

    def publish(self, msg):
        """
        Called by coupler when new data is available
        
        Args:
            msg: NavGenericMsg with VE.Direct data in msg.msg
        """
        _logger.debug("VE.Direct message:%s" % msg.printable())
        
        # Store the current data dictionary

        
        # Update current data via process_msg
        self._current_data.process_msg(msg)
        
        clock = time.monotonic()

        # Check if charger is off
        if self._current_data.state == VE_state.Off:
            _logger.debug("DC-DC charger is off")
            if self._energy_controller is not None:
                self._energy_controller.set_off_state(self._instance, self.device_type, False, True)
            return
        
        # DC-DC specific processing
        if not self._communication_ok:
            # communication is back so we need to reset all calculation
            self._mean_in_v = 0.0
            self._mean_in_a = 0.0
            self._mean_in_p = 0.0
            self._mean_out_v = 0.0
            self._mean_out_a = 0.0
            self._mean_out_p = 0.0
            self._nb_sample = 0
            self._trend_buckets.clear()
            self._start_period = clock
            self._communication_ok = True

        # Process the trend data
        self._mean_in_v += self._current_data.input_voltage
        self._mean_in_a += self._current_data.input_current
        self._mean_in_p += self._current_data.input_power
        self._mean_out_v += self._current_data.output_voltage
        self._mean_out_a += self._current_data.output_current
        self._mean_out_p += self._current_data.output_power
        self._nb_sample += 1

        self._last_msg_ts = clock
        
        # Create trend buckets periodically
        if clock - self._start_period >= self._trend_period and self._nb_sample > 0:
            self._trend_buckets.append(DC_DCBucket(
                self._mean_in_v / self._nb_sample,
                self._mean_in_a / self._nb_sample,
                self._mean_in_p / self._nb_sample,
                self._mean_out_v / self._nb_sample,
                self._mean_out_a / self._nb_sample,
                self._mean_out_p / self._nb_sample
            ))
            self._start_period = clock
            self._mean_in_v = 0.0
            self._mean_in_a = 0.0
            self._mean_in_p = 0.0
            self._mean_out_v = 0.0
            self._mean_out_a = 0.0
            self._mean_out_p = 0.0
            self._nb_sample = 0
        
        # forward information through publisher
        if self._publish_function is not None:
            self._publish_function()

        # Report DC-DC data to the energy controller
        if self._energy_controller is not None and self._current_data is not None:
            _logger.debug("DC-DC Service report to energy controller")
            self._energy_controller.source_update(
                self._instance,
                self.device_type,
                clock,
                self._current_data.output_current,
                self._current_data.output_power,
                self._current_data.output_voltage
            )

    def get_device_info(self, device_info):
        """
        Fill device information protobuf
        
        Args:
            device_info: DC_DC_Charger_Parameters protobuf message to fill
        """
        # Call parent implementation to set common fields
        # super().get_device_info(device_info)
        fill_protobuf_from_dict(device_info, self._parameters)
        # Add DC-DC specific information
        if self._current_data is not None:
            self._current_data.parameters_pb(device_info)

    def get_running_values(self, running_values_pb):
        """
        Fill protobuf with current running values
        
        Args:
            running_values_pb: DC_DC_Charger_running_values protobuf message to fill
        """
        if self._current_data is not None:
            self._current_data.running_values_pb(running_values_pb)
            running_values_pb.instance = self._instance

    def publish0183(self):
        """Publish data in NMEA0183 format"""
        _logger.debug("DC-DC Service publish NMEA0183")
        # TODO: Implement NMEA0183 publishing for DC-DC
        # from navigation_server.couplers import dc_dc_nmea0183
        # msg = dc_dc_nmea0183(self._current_data_dict)
        # self._publisher.publish(msg)

    def publish2000(self):
        """Publish data in NMEA2000 format"""
        _logger.debug("DC-DC Service publish NMEA2000")
        # TODO: Implement NMEA2000 publishing for DC-DC
        # from navigation_server.generated.nmea2000_classes_gen import Pgn127751Class
        # msg = self._current_data.gen_pgn_xxxxx()
        # msg_sent = NavGenericMsg(N2K_MSG, msg=msg.message())
        # self._sid += 1
        # self._publisher.publish(msg_sent)


class DC_DCServicer(DC_DC_ServiceServicer):
    """
    gRPC servicer for DC-DC Service
    Handles gRPC requests and delegates to the DC-DC device
    """
    
    def __init__(self, dc_dc_device):
        """
        Initialize the servicer with a DC-DC device
        
        Args:
            dc_dc_device: VictronDC_DC device instance
        """
        self._dc_dc_device = dc_dc_device

    def GetInformation(self, request, context):
        """
        Handle GetInformation gRPC request
        Returns device parameters and optionally configuration parameters
        
        Args:
            request: energy_request protobuf message
            context: gRPC context
            
        Returns:
            DC_DC_Charger_Parameters protobuf message
        """
        _logger.debug("gRPC request DC_DC_Service.GetInformation")
        ret_data = DC_DC_Charger_Parameters()
        self._dc_dc_device.get_device_info(ret_data)
        if request.command:
            if request.command == 'parameters':
                self._dc_dc_device.get_device_parameters(ret_data)
        return ret_data

    def GetValues(self, request, context):
        """
        Handle GetValues gRPC request
        Returns current running values of the DC-DC charger
        
        Args:
            request: energy_request protobuf message
            context: gRPC context
            
        Returns:
            DC_DC_Charger_running_values protobuf message
        """
        _logger.debug("gRPC request DC_DC_Service.GetValues")
        ret_val = DC_DC_Charger_running_values()
        self._dc_dc_device.get_running_values(ret_val)
        return ret_val

    def GetTrend(self, request, context):
        """
        Handle GetTrend gRPC request
        Returns historical trend data
        
        Args:
            request: energy_request protobuf message
            context: gRPC context
            
        Returns:
            DC_DC_Charger_trend protobuf message
        """
        _logger.debug("gRPC request DC_DC_Service.GetTrend")
        ret_values = DC_DC_Charger_trend()
        ret_values.instance = self._dc_dc_device.instance
        ret_values.nb_values = 0
        ret_values.interval = self._dc_dc_device.trend_interval
        for bucket in self._dc_dc_device.get_trend_buckets():
            ret_values.nb_values += 1
            val = DC_DC_Charger_running_values()
            val.input_voltage = bucket.input_voltage
            val.input_current = bucket.input_current
            val.input_power = bucket.input_power
            val.output_voltage = bucket.output_voltage
            val.output_current = bucket.output_current
            val.output_power = bucket.output_power
            ret_values.samples.append(val)
        return ret_values

    def SetConfiguration(self, request, context):
        """
        Handle SetConfiguration gRPC request
        Sets configuration parameters for the DC-DC charger
        
        Args:
            request: DC_DC_Charger_configuration protobuf message
            context: gRPC context
            
        Returns:
            energy_command_response protobuf message
        """
        _logger.debug("gRPC request DC_DC_Service.SetConfiguration")
        # TODO: Implement configuration setting for DC-DC charger
        response = energy_command_response()
        response.id = request.instance
        response.command = "SetConfiguration"
        response.response = "OK"
        return response


class DC_DCService(GrpcService):
    """
    gRPC service for Victron Orion XS DC-DC charger
    
    This service connects to a Victron Orion XS DC-DC charger via VE.Direct protocol
    and provides gRPC interface for accessing charger data and configuration
    """

    def __init__(self, opts):
        """
        Initialize the DC-DC service
        
        Args:
            opts: Configuration options dictionary
        """
        super().__init__(opts)
        self._dc_dc_device = VictronDC_DC(opts, self)

    def finalize(self):
        """
        Finalize the service - register gRPC servicer and start device
        """
        super().finalize('DC_DC', 'DC_DC_Service')
        add_DC_DC_ServiceServicer_to_server(DC_DCServicer(self._dc_dc_device), self.grpc_server)
        self._dc_dc_device.start()

    @property
    def device(self):
        return self._dc_dc_device
