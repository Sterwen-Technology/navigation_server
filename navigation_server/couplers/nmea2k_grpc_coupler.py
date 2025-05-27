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


from navigation_server.router_common import GrpcClient, ServiceClient, N2K_MSG, NavGenericMsg, GrpcAccessException, GrpcStreamTimeout
from navigation_server.router_core import NMEA2000Msg, Coupler, CouplerReadError, CouplerTimeOut

from navigation_server.generated.n2k_can_service_pb2 import CANReadRequest
from navigation_server.generated.n2k_can_service_pb2_grpc import CAN_ControllerServiceStub
from navigation_server.generated.nmea2000_pb2 import nmea2000pb

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KGrpcCoupler(Coupler, ServiceClient):

    def __init__(self, opts):
        super().__init__(opts)
        ServiceClient.__init__(self, CAN_ControllerServiceStub)
        self._server = opts.get('server', str, None)
        if self._server is None:
            _logger.error(f"class {self.__class__.name} the 'server' parameter is mandatory")
            raise ValueError
        self._port= opts.get('port', int, 0)
        if self._port == 0:
            _logger.error(f"class {self.__class__.name} the 'port' parameter is mandatory")
            raise ValueError
        #
        self._mode = self.NMEA2000
        self._select_sources = opts.getlist('select_sources', int, None)
        self._reject_sources = opts.getlist('reject_sources', int, None)
        self._select_pgn = opts.getlist('select_pgn', int, None)
        self._reject_pgn = opts.getlist('reject_pgn', int, None)
        self._client:GrpcClient = GrpcClient.get_client(f"{self._server}:{self._port}")
        self._client.add_service(self)
        self._can_request = CANReadRequest()
        self._can_request.client = f"{self.object_name()}-reader"
        if self._select_sources is not None:
            self._can_request.select_sources.extend(self._select_sources)
        elif self._reject_sources is not None:
            self._can_request.reject_sources.extend(self._reject_sources)
        if self._select_pgn is not None:
            self._can_request.select_pgn.extend(self._select_pgn)
        elif self._reject_pgn is not None:
            self._can_request.reject_pgn.extend(self._reject_pgn)

    def open(self):
        _logger.debug("N2KGrpcCoupler open")
        self._client.connect()
        success = self._client.wait_connect(20.0)
        if success:
            _logger.debug("N2KGrpcCoupler open => connected")
            if not self.stream_is_alive():
                self._start_read_stream(self._stub.ReadNmea2000Msg, self._can_request)
            return True
        else:
            _logger.debug("N2KGrpcCoupler open => failed")
            return False

    def read(self):
        if self._client.connected:
            try:
                pb_msg = self._read_stream()
                _logger.debug("N2KGrpcCoupler message received with PGN %d" % pb_msg.pgn)
            except GrpcAccessException:
                # ok, we have a problem, let's wait and restart later
                time.sleep(1.0)
                raise CouplerReadError
            except GrpcStreamTimeout:
                raise CouplerTimeOut
            n2k_msg = NMEA2000Msg(pgn=pb_msg.pgn, protobuf=pb_msg)
            yield NavGenericMsg(N2K_MSG, msg=n2k_msg)
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

