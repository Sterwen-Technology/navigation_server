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
                                             CANGrpcStreamReader, GrpcStreamTimeout, GrpcAccessException)
from navigation_server.router_core import NMEA2000Msg, Coupler, CouplerReadError, CouplerTimeOut

from navigation_server.generated.n2k_can_service_pb2 import CANReadRequest
from navigation_server.generated.nmea2000_pb2 import nmea2000pb

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KGrpcCoupler(Coupler, CANGrpcStreamReader):

    def __init__(self, opts):
        super().__init__(opts)
        CANGrpcStreamReader.__init__(self, self.object_name(), opts)
        self._mode = self.NMEA2000

    def open(self):
        _logger.debug("N2KGrpcCoupler open")
        return self.start_stream_to_queue()

    def _read(self):
        if self._client.connected:
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
        else:
            # let's wait
            time.sleep(10.0)
            self._state = self.NOT_READY
            raise CouplerReadError

    def stop(self):
        super().stop()
        self._stop_read_stream()

    def close(self):
        pass

