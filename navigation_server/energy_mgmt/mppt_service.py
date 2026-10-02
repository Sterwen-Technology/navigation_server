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

from collections import namedtuple, deque

from navigation_server.generated.energy_pb2 import (solar_output, energy_request, MPPT_device, solar_trend_response,
                                                    EnergySource, VE_MPPT, VE_Error)
from navigation_server.generated.energy_pb2_grpc import MPPTServiceServicer, add_MPPTServiceServicer_to_server
from navigation_server.router_common import (GrpcService, MessageServerGlobals, resolve_ref, copy_protobuf_data,
                                             NavGenericMsg, N2K_MSG, fill_protobuf_from_dict)
from navigation_server.router_core import NMEA0183Sentences

from navigation_server.generated.nmea2000_classes_gen import Pgn127751Class

from .energy_base_service import EnergyDevice

_logger = logging.getLogger("ShipDataServer." + __name__)


class MPPTData:
    def __init__(self, value_dict):
        self.current = float(value_dict['I']) * 0.001
        self.voltage = float(value_dict['V']) * 0.001
        self.panel_voltage = float(value_dict['VPV']) * 0.001
        self.panel_power = float(value_dict['PPV'])
        self.product_id = value_dict['PID']
        self.firmware = value_dict['FW']
        self.serial = value_dict['SER#']
        self.error = int(value_dict['ERR'])
        self.state = int(value_dict['CS'])
        self.mppt_state = int(value_dict['MPPT'])
        self.day_max_power = float(value_dict['H21'])
        self.day_power = float(value_dict['H20']) * 10.0

    def output_pb(self, output_pb_v):
        copy_protobuf_data(self, output_pb_v, ('current', 'voltage', 'panel_voltage','panel_power'))

    def output_info_pb(self, output_pb):
        copy_protobuf_data(self, output_pb, ('product_id', 'firmware', 'serial', 'error', 'state', 'mppt_state',
                                             'day_max_power', 'day_power'))

    state_dict = {0: 0, 2: 9, 3: 1, 4: 2, 5: 5, 7: 4, 247: 4}  # correspondence between Victron and NMEA2000 state

    def gen_pgn_127751(self, sid: int):
        # 12/05/2026 (2.8.1) - the PGN is currently wrongly encoded do not use it for now
        # 31/08/2026 (3.0.0) - PGN definition updated
        res = Pgn127751Class()
        res.sequence_id = sid % 256
        res.connection_number = 1
        res.voltage = self.voltage
        res.current = self.current
        return res


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

    def publish(self, msg):
        """Called by coupler when new data is available"""
        _logger.debug("VEDirect message:%s" % msg.msg)
        
        # Store the current data
        self._current_data = MPPTData(msg.msg)
        clock = time.monotonic()

        if self._current_data.mppt_state == VE_MPPT.MPPT_Off:
            _logger.debug("MPPT is off")
            if self._energy_controller is not None:
                self._energy_controller.set_off_state(self._instance, self.device_type, False, True)
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

        """Report MPPT data to the energy controller"""
        if self._energy_controller is not None and self._current_data is not None:
            _logger.debug("MPPT Service report to energy controller")
            clock = time.monotonic()
            self._energy_controller.source_update(
                self._instance, 
                self.device_type,
                clock,
                self._current_data.current, 
                self._output_power,
                self._current_data.voltage
            )

    def get_solar_output(self, output_values_pb):
        if self._current_data is not None:
            self._current_data.output_pb(output_values_pb)

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
        _logger.debug("GRPC request MPPTService.GetDeviceInfo")
        ret_data = MPPT_device()
        self._mppt_device.get_device_info(ret_data)
        if request.command:
            if request.command == 'parameters':
                self._mppt_device.get_device_parameters(ret_data.parameters)
        return ret_data

    def GetOutput(self, request, context):
        _logger.debug("GRPC request MPPTService.GetOutput")
        ret_val = solar_output()
        # object.__setattr__(ret_val, 'voltage', 12.6)
        self._mppt_device.get_solar_output(ret_val)
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
        return ret_values


class MPPTService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._mppt_device = VictronMPPT(opts, self)

    def finalize(self):
        super().finalize('MPPT', 'MPPTService')
        add_MPPTServiceServicer_to_server(MPPTServicer(self._mppt_device), self.grpc_server)
        self._mppt_device.start()
