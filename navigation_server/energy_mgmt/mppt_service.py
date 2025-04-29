#-------------------------------------------------------------------------------
# Name:        mppt_reader
# Purpose:     server connected to Victron devices via VEDirect (serial 19200baud)
#   Both HEX protocol and Text protocol are handled
#
# Author:      Laurent Carré
#
# Created:     31/03/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time
import traceback

from collections import namedtuple, deque

from navigation_server.generated.energy_pb2 import solar_output, request, MPPT_device, trend_response
from navigation_server.generated.energy_pb2_grpc import solar_mpptServicer, add_solar_mpptServicer_to_server
from navigation_server.router_common import GrpcService, MessageServerGlobals, resolve_ref, copy_protobuf_data
from navigation_server.router_core import NMEA0183Sentences
from navigation_server.couplers import mppt_nmea0183

from navigation_server.generated.nmea2000_classes_gen import Pgn127751Class, Pgn127507Class


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

    def output_info_pb(self, output_pb):
        copy_protobuf_data(self, output_pb, ('product_id', 'firmware', 'serial', 'error', 'state', 'mppt_state',
                                             'day_max_power', 'day_power'))

    state_dict = {0: 0, 2: 9, 3: 1, 4: 2, 5: 5, 7: 4, 247: 4}  # correspondence between Victron and NMEA2000 state

    def gen_pgn_127507(self):
        res = Pgn127507Class()
        res.charger_instance = 1
        res.battery_instance = 1
        res.operating_state = self.state_dict.get(self.state, 0)
        res.charger_mode = 0
        if self.mppt_state != 0:
            res.charger_enable = 1
        else:
            res.charger_enable = 0
        res.equalization_pending = 0
        res.eq_time_remaining = 0
        return res

    def gen_pgn_127751(self, sid: int):
        res = Pgn127751Class()
        res.sequence_id = sid % 256
        res.connection_number = 1
        res.voltage = self.voltage
        res.current = self.current
        return res


MPPTBucket = namedtuple('MPPTBucket', ['voltage', 'current', 'power'])


class VictronMPPT:

    def __init__(self, opts, service):
        self._name = opts.get('name', str, 'VictronMPPT')
        self._coupler_name = opts.get('coupler', str, None)
        if self._coupler_name is None:
            _logger.error("The MPPT device must be linked with a coupler")
            raise ValueError
        self._coupler = None
        self._publisher_name = opts.get('publisher', str, None)
        if self._publisher_name is not None:
            self._protocol = opts.get_choice('protocol', ('nmea0183', 'nmea2000'), 'nmea0183')
            if self._protocol == 'nmea0183':
                NMEA0183Sentences.set_talker(opts.get('talker', str, 'ST'))
        self._publisher = None
        self._publish_function = None
        self._service = service
        self._current_data = None
        self._current_data_dict = None
        self._trend_depth = opts.get('trend_depth', int, 30)
        self._trend_period = opts.get('trend_period', float, 10.)
        self._trend_buckets = deque(maxlen=self._trend_depth)
        self._start_period = 0.0
        self._mean_v = 0.0
        self._mean_a = 0.0
        self._mean_p = 0.0
        self._nb_sample = 0

    def stop_service(self):
        _logger.info(f"MPPT Victron {self._name} request to stop service")
        self._service.stop_service()

    @property
    def trend_interval(self):
        return self._trend_period

    def get_trend_buckets(self):
        for b in self._trend_buckets:
            yield b

    def start(self):
        #
        try:
            self._coupler = resolve_ref(self._coupler_name)
        except KeyError:
            _logger.error("Victron MPPT missing coupler:%s" % self._coupler_name)
            self.stop_service()
        # now let's see for the publisher
        if self._publisher_name is not None:
            try:
                self._publisher = resolve_ref(self._publisher_name)
            except KeyError:
                _logger.error("MPPTService no publisher %s" % self._publisher_name)

            if self._publisher is not None:
                _logger.debug(
                    "MPPT Service publisher set:%s protocol:%s" % (self._publisher.object_name(), self._protocol))
                if self._protocol == 'nmea0183':

                    self._publish_function = self.publish0183
                else:
                    self._publish_function = self.publish2000
                    self._sid = 0

        self._coupler.register(self)
        self._start_period = time.monotonic()

    def publish(self, msg):
        _logger.debug("VEDirect message:%s" % msg.msg)
        self._current_data_dict = msg.msg  # that is the dictionary  with all current values
        self._current_data = MPPTData(msg.msg)
        # now let's compute the trend
        self._mean_v += self._current_data.voltage
        self._mean_a += self._current_data.current
        self._mean_p += self._current_data.panel_power
        self._nb_sample += 1
        clock = time.monotonic()
        if clock - self._start_period >= self._trend_period and self._nb_sample > 0:
            self._trend_buckets.append(MPPTBucket(self._mean_v/self._nb_sample, self._mean_a/self._nb_sample,
                                                  self._mean_p/self._nb_sample))
            self._start_period = clock
            self._mean_v = 0.0
            self._mean_a = 0.0
            self._mean_p = 0.0
            self._nb_sample = 0
        if self._publish_function is not None:
            self._publish_function()

    def get_solar_output(self, output_values_pb):
        if self._current_data is not None:
            self._current_data.output_pb(output_values_pb)

    def get_device_info(self, device_info):
        if self._current_data is not None:
            self._current_data.output_info_pb(device_info)

    def publish0183(self):
        _logger.debug("MPPT Service publish NMEA0183")
        msg = mppt_nmea0183(self._current_data_dict)
        self._publisher.publish(msg)

    def publish2000(self):
        msg = self._current_data.gen_pgn_127507()
        self._publisher.publish(msg)
        msg = self._current_data.gen_pgn_127751(self._sid)
        self._sid += 1
        self._publisher.publish(msg)

    def object_name(self):
        # for debug only
        traceback.print_stack()



class MPPT_Servicer(solar_mpptServicer):
    """

    """
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

    def GetTrend(self, request, context):
        _logger.debug("GRPC request GetTrend")
        ret_values = trend_response()
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
        super().finalize()
        add_solar_mpptServicer_to_server(MPPT_Servicer(self._mppt_device), self.grpc_server)
        self._mppt_device.start()
