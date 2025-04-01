#-------------------------------------------------------------------------------
# Name:        grpc_nmea_server.py
# Purpose:     module for the grpc data server
#
# Author:      Laurent Carré
#
# Created:     30/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from navigation_server.router_common import GrpcService, GrpcServerError, MessageServerGlobals
from navigation_server.generated.nmea_server_pb2_grpc import NMEAServerServicer, add_NMEAServerServicer_to_server
from navigation_server.generated.nmea_messages_pb2 import server_resp, nmea_msg
from .publisher import PullPublisher
from navigation_server.router_common import N2K_MSG

_logger = logging.getLogger("ShipDataServer." + __name__)


class GrpcNMEAServer(NMEAServerServicer):
    """
    A gRPC server class that extends the NMEAServerServicer to provide NMEA-related functionalities.

    This class implements methods to manage and serve NMEA data through gRPC. It includes operations
    to check the server's status, send NMEA messages, and retrieve NMEA data in a streaming fashion.
    The class is tailored to handle NMEA structured data and integrates with underlying couplers
    and message handling mechanisms to process and publish NMEA data.

    Attributes:
        _couplers (Any): The couplers used for routing and handling NMEA data.

    """
    def __init__(self, couplers):
        super().__init__()
        self._couplers = couplers
        self._read_session = 0
        self._publisher = None

    def status(self, request, context):
        resp = server_resp()
        resp.status = "OK"
        resp.reportCode = 0
        return resp

    def sendNMEA(self, request, context):
        resp = server_resp()
        resp.status = "NOT IMPLEMENTED"
        resp.reportCode = 1
        return resp

    def getNMEA(self, request, context):
        _logger.debug("getNMEA - enter")
        context.add_callback(self._get_stream_cb)
        self._publisher = PullPublisher(self._couplers, f"Grpc-NMEAServer-{self._read_session}")
        self._read_session += 1
        self._publisher.start()
        while True:
            msg = self._publisher.pull_msg()

            if msg.type == N2K_MSG:
                # _logger.debug("getNMEA message to be sent: %s" % msg.msg.format1())
                resp_msg = nmea_msg()
                msg.msg.as_protobuf(resp_msg.N2K_msg)
                yield resp_msg
            else:
                _logger.error("get_nmea: unknown message type")
                break
        _logger.debug("getNMEA - exit")

    def _get_stream_cb(self):
        _logger.debug("get_stream_cb - enter")
        self._publisher.stop()


class GrpcNMEAServerService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)

    def finalize(self):
        try:
            super().finalize()
        except GrpcServerError:
            return
        _logger.info("Adding service %s to server" % self._name)
        couplers = MessageServerGlobals.configuration.main_server.couplers()
        add_NMEAServerServicer_to_server(GrpcNMEAServer(couplers), self.grpc_server)