#-------------------------------------------------------------------------------
# Name:        mppt_reader
# Purpose:     server connected to Victron devices via VEDirect (serial 19200baud)
#   Both HEX protocol and Text protocol are handled
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time

from collections import namedtuple, deque

from generated.energy_pb2 import solar_output, request, MPPT_device
from generated.energy_pb2_grpc import solar_mpptServicer, add_solar_mpptServicer_to_server
from router_common import GrpcService, MessageServerGlobals, resolve_ref, copy_protobuf_data


_logger = logging.getLogger("ShipDataServer." + __name__)


class MPPTData:
    def __init__(self, value_dict):
        self.current = float(value_dict['I']) * 0.001
        self.voltage = float(value_dict['V']) * 0.001
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
        copy_protobuf_data(self, output_pb_v, ('current', 'voltage', 'panel_power'))
        # output_pb_v.current = self.current
        # output_pb_v.voltage = self.voltage
        # object.__setattr__(output_pb_v, 'panel_power', self.panel_power)

    def output_info_pb(self, output_pb):
        copy_protobuf_data(self, output_pb, ('product_id', 'firmware', 'serial', 'error', 'state', 'mppt_state',
                                             'day_max_power', 'day_power'))


class VictronMPPT:

    def __init__(self, opts, service):
        self._name = opts.get('name', str, 'VictronMPPT')
        self._coupler_name = opts.get('coupler', str, None)
        if self._coupler_name is None:
            _logger.error("The MPPT device must be linked with a coupler")
            raise ValueError
        self._coupler = None
        self._service = service
        self._current_data = None
        self._current_data_dict = None
        self._trend_depth = opts.get('trend_depth', int, 30)
        self._trend_period = opts.get('trend_period', float, 10.)
        self._trend_buckets = deque(maxlen=self._trend_depth)
        self._start_period = 0.0

    def stop_service(self):
        _logger.info(f"MPPT Victron {self._name} request to stop service")
        self._service.stop_service()

    def start(self):
        #
        try:
            self._coupler = resolve_ref(self._coupler_name)
        except KeyError:
            _logger.error("Victron MPPT missing coupler:%s" % self._coupler_name)
            self.stop_service()
        self._coupler.register(self)
        self._start_period = time.monotonic()

    def publish(self, msg):
        _logger.debug("VEDirect message:%s" % msg.msg)
        self._current_data_dict = msg.msg  # that is the dictionary  with all current values
        self._current_data = MPPTData(msg.msg)

    def get_solar_output(self, output_values_pb):
        if self._current_data is not None:
            self._current_data.output_pb(output_values_pb)

    def get_device_info(self, device_info):
        if self._current_data is not None:
            self._current_data.output_info_pb(device_info)


class MPPT_Servicer(solar_mpptServicer):

    def __init__(self, mppt_device):
        self._mppt_device = mppt_device

    def GetDeviceInfo(self, request, context):
        _logger.debug("GRPC request GetDevice")
        ret_data = MPPT_device()
        self._mppt_device.get_device_info(ret_data)
        return ret_data

    def GetOutput(self, request, context):
        _logger.debug("GRPC request GetOutput")
        ret_val = solar_output()
        # object.__setattr__(ret_val, 'voltage', 12.6)
        self._mppt_device.get_solar_output(ret_val)
        return ret_val


class MPPTService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._mppt_device = VictronMPPT(opts, self)

    def finalize(self):
        super().finalize()
        add_solar_mpptServicer_to_server(MPPT_Servicer(self._mppt_device), self.grpc_server)
        self._mppt_device.start()
