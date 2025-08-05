#-------------------------------------------------------------------------------
# Name:        nmea2k_grpc_coupler.py
# Purpose:     coupler over the gRPC service for the NMEA2000/CAN data access
#
# Author:      Laurent Carré
#
# Created:     24/05/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time


from navigation_server.router_common import (N2K_MSG, NavGenericMsg,
                                              GrpcStreamTimeout, GrpcAccessException)
from navigation_server.router_core import NMEA2000Msg, Coupler, CANGrpcStreamReader, CouplerReadError, CouplerTimeOut

from navigation_server.generated.n2k_can_service_pb2 import CANReadRequest
from navigation_server.generated.nmea2000_pb2 import nmea2000pb

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KGrpcCoupler(Coupler, CANGrpcStreamReader):

    def __init__(self, opts):
        super().__init__(opts)
        input_stream_opts = {}
        input_stream_opts['source_server'] = opts.get('source_server', str, None)
        input_stream_opts['source_port'] = opts.get('source_port', int, 0)
        input_stream_opts['select_sources'] = opts.getlist('select_sources', int, None)
        input_stream_opts['reject_sources'] = opts.getlist('reject_sources', int, None)
        input_stream_opts['reject_pgn'] = None
        CANGrpcStreamReader.__init__(self, self.object_name(), input_stream_opts)
        self._mode = self.NMEA2000

    def open(self):
        _logger.debug("N2KGrpcCoupler open attempt with state %d" % self._state)
        if self.start_stream_to_queue():
            _logger.info(f"N2KGrpcCoupler {self.object_name()} connected")
            self._state = self.CONNECTED
            return True
        else:
            _logger.error(f"N2KGrpcCoupler {self.object_name()} cannot connect to server")
            return False

    def _read(self):
        _logger.debug("N2KGrpcCoupler read")
        try:
            pb_msg = self._read_stream()
            _logger.debug("N2KGrpcCoupler message received with PGN %d" % pb_msg.pgn)
        except GrpcAccessException:
            # ok, we have a problem, let's wait and restart later
            time.sleep(1.0)
            self._state = self.NOT_READY
            _logger.debug("N2KGrpcCoupler => StreamReadError")
            raise CouplerReadError
        except GrpcStreamTimeout:
            _logger.debug("N2KGrpcCoupler => Timeout")
            raise CouplerTimeOut
        n2k_msg = NMEA2000Msg(pgn=pb_msg.pgn, protobuf=pb_msg)
        return NavGenericMsg(N2K_MSG, msg=n2k_msg)


    def stop(self):
        super().stop()
        self._stop_read_stream()

    def close(self):
        pass

