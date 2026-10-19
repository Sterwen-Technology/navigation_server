#-------------------------------------------------------------------------------
# Name:        mppt_reader
# Purpose:     server connected to Victron devices via VEDirect (serial 19200baud)
#   Both HEX protocol and Text protocol are handled
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
import traceback

from collections import namedtuple

from navigation_server.generated.energy_pb2 import (solar_output, energy_request, MPPT_device, solar_trend_response,
                                                    EnergySource, VE_MPPT, VE_Error, energy_command_response)
from navigation_server.generated.energy_pb2_grpc import MPPTServiceServicer, add_MPPTServiceServicer_to_server
from navigation_server.router_common import (GrpcService, MessageServerGlobals, resolve_ref, copy_protobuf_data,
                                             NavGenericMsg, N2K_MSG, fill_protobuf_from_dict)

from navigation_server.couplers import VEDirectMsg

from .energy_base_service import EnergyDevice
from .victron_interface import VictronMPPTData

_logger = logging.getLogger("ShipDataServer." + __name__)


MPPTBucket = namedtuple('MPPTBucket', ['voltage', 'panel_voltage', 'current', 'power'])


class VictronMPPT(EnergyDevice):
    """
    Victron MPPT device implementation
    Extends EnergyDevice with MPPT-specific functionality
    """
    
    # MPPT energy source type
    energy_source_type = EnergySource.Solar_MPPT

    def __init__(self, opts, service):
        # Initialize base class
        super().__init__(opts, service)
        
        # MPPT-specific parameters
        self._parameters = {
            'instance': opts.get('instance', int, 1),
            'battery': opts.get('battery', int, 1),
            'panel_max_power': opts.get('panel_max_power', float, 0.0),
            'panel_max_voltage': opts.get('panel_max_voltage', float, 0.0),
            'max_voltage': opts.get('max_voltage', float, 0.0),
            'trend_duration': opts.get('trend_duration', int, 5),
            'trend_interval': self._trend_period
        }
        
        # MPPT-specific tracking
        self._current_data = VictronMPPTData()
        self._output_power = 0.0
        self._mean_v = 0.0
        self._mean_a = 0.0
        self._mean_p = 0.0
        self._mean_pv = 0.0
        self._nb_sample = 0

    @property
    def device_type(self):
        """
        Get the energy source type for this device

        Returns the EnergySource enum value
        """
        return EnergySource.Solar_MPPT

    def start(self):
        """Start the MPPT device"""
        # Call parent start
        super().start()
        
        # MPPT-specific initialization
        # Note: _publish_function is already set in base class start()
        # but we need to ensure _sid is initialized for NMEA2000
        if self._publisher is not None and self._protocol == 'nmea2000':
            self._sid = 0

    def publish(self, msg: VEDirectMsg):
        """Called by coupler when new data is available"""
        _logger.debug("VEDirect message:%s" % msg.printable())
        # Store the current data

        clock = time.monotonic()
        if not self._current_data.process_msg(msg):
            self._last_msg_ts = clock
            return


        
        # MPPT-specific processing
        if not self._communication_ok:
            # communication is back so we need to reset all calculation
            self._mean_v = 0.0
            self._mean_a = 0.0
            self._mean_p = 0.0
            self._mean_pv = 0.0
            self._nb_sample = 0
            self._trend_buckets.clear()
            self._start_period = clock
            self._communication_ok = True

        # Process the trend data
        self._mean_v += self._current_data.voltage
        self._mean_a += self._current_data.current
        self._mean_pv += self._current_data.panel_voltage
        self._mean_p += self._current_data.panel_power
        self._output_power = self._current_data.voltage * self._current_data.current
        self._nb_sample += 1

        self._last_msg_ts = clock
        
        # Create trend buckets periodically
        if clock - self._start_period >= self._trend_period and self._nb_sample > 0:
            self._trend_buckets.append(MPPTBucket(
                self._mean_v/self._nb_sample, 
                self._mean_a/self._nb_sample,
                self._mean_pv/self._nb_sample,
                self._mean_p/self._nb_sample))
            self._start_period = clock
            self._mean_v = 0.0
            self._mean_a = 0.0
            self._mean_p = 0.0
            self._mean_pv = 0.0
            self._nb_sample = 0
        
        # forward information through publisher
        if self._publish_function is not None:
            self._publish_function()

        if self._current_data.mppt_state == VE_MPPT.MPPT_Off:
            _logger.debug("MPPT is off")
            if self._energy_controller is not None:
                self._energy_controller.set_off_state(self._instance, self.device_type, True, False)

        #Report MPPT data to the energy controller
        elif self._energy_controller is not None and self._current_data is not None:
            _logger.debug("MPPT Service report to energy controller")
            clock = time.monotonic()
            self._energy_controller.source_update(
                self._instance, 
                self.device_type,
                clock,
                self._current_data.current, 
                self._output_power,
                self._current_data.voltage,
                self._current_data.state
            )

    def get_solar_output(self, output_values_pb):
        if self._current_data is not None:
            self._current_data.output_pb(output_values_pb)

    def send_command(self, command):
        """Send a command to the DC-DC device

        Args:
            command: Command to send
        """
        if command == 'charger_on':
            self._current_data.set_charger_on(self._coupler)
        elif command == 'charger_off':
            self._current_data.set_charger_off(self._coupler)
        else:
            _logger.error("Unknown command %s", command)

    def publish0183(self):
        _logger.debug("MPPT Service publish NMEA0183")
        from navigation_server.couplers import mppt_nmea0183
        msg = mppt_nmea0183(self._current_data_dict)
        self._publisher.publish(msg)

    def publish2000(self):
        _logger.debug("MPPT Service publish NMEA2000")
        '''
        PGN127507 is currently not supported (encoding error) 12/05/206 2.8.1
        msg = self._current_data.gen_pgn_127507()
        msg_sent = NavGenericMsg(N2K_MSG, msg=msg.message())
        self._publisher.publish(msg_sent)
        '''
        msg = self._current_data.gen_pgn_127751(self._sid)
        msg_sent = NavGenericMsg(N2K_MSG, msg=msg.message())
        self._sid += 1
        self._publisher.publish(msg_sent)

    def object_name(self):
        # for debug only
        traceback.print_stack()


class MPPTServicer(MPPTServiceServicer):
    """

    """
    def __init__(self, mppt_device):
        self._mppt_device = mppt_device

    def GetDeviceInfo(self, request, context):
        _logger.debug(f"GRPC request MPPTService.GetDeviceInfo command={request.command}")
        ret_data = MPPT_device()
        self._mppt_device.get_device_info(ret_data)
        if request.command:
            if request.command == 'parameters':
                self._mppt_device.get_device_parameters(ret_data.parameters)
        _logger.debug(f"MPPTService.GetDeviceInfo OK")
        return ret_data

    def GetOutput(self, request, context):
        _logger.debug("GRPC request MPPTService.GetOutput")
        ret_val = solar_output()
        # object.__setattr__(ret_val, 'voltage', 12.6)
        self._mppt_device.get_solar_output(ret_val)
        _logger.debug(f"MPPTService.GetOutput OK")
        return ret_val

    def GetTrend(self, request, context):
        _logger.debug("GRPC request MPPTService.GetTrend")
        ret_values = solar_trend_response()
        ret_values.id = request.id
        ret_values.nb_values = 0
        ret_values.interval = self._mppt_device.trend_interval
        for bucket in self._mppt_device.get_trend_buckets():
            ret_values.nb_values += 1
            val = solar_output()
            val.voltage = bucket.voltage
            val.current = bucket.current
            val.panel_power = bucket.power
            ret_values.values.append(val)
        _logger.debug(f"MPPTService.GetTrend OK")
        return ret_values

    def DeviceCommand(self, request, context):
        """
        Handle sending a command to the device
        Current the following commands are supported:
        - "charger_on"
        - "charger_off"

        :param request:
        :type request:
        :param context:
        :type context:
        :return:
        :rtype:
        """
        _logger.debug("gRPC request DC_DC_Service.DeviceCommand %s", request.command)
        response = energy_command_response()
        response.id = request.instance
        response.command = request.command
        if request.command in ["charger_on", "charger_off"]:
            self._mppt_device.send_command(request.command)
            response.response = "OK"
        else:
            response.response = "ERROR - Unknown command"
        return response

class MPPTService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._mppt_device = VictronMPPT(opts, self)

    def finalize(self):
        super().finalize('MPPT', 'MPPTService')
        add_MPPTServiceServicer_to_server(MPPTServicer(self._mppt_device), self.grpc_server)
        self._mppt_device.start()

    @property
    def device(self):
        return self._mppt_device