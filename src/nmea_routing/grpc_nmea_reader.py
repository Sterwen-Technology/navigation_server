#-------------------------------------------------------------------------------
# Name:        grpc_nmea_reader
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     20/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging

from generated.input_server_pb2_grpc import NMEAInputServerServicer, add_NMEAInputServerServicer_to_server
from generated.nmea_messages_pb2 import server_resp
from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea0183.nmea0183_msg import nmea0183msg_from_protobuf
from nmea_routing.server_common import NavigationGrpcServer

_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcNmeaServicer(NMEAInputServerServicer):

    def __init__(self, callback_n2k, callback_0183):
        self._callback_n2k = callback_n2k
        self._callback_0183 = callback_0183

    def pushNMEA(self, request, context):
        resp = server_resp()
        resp.reportCode = 0
        if request.HasField("N2K_msg"):
            msg = request.N2K_msg
            self._callback_n2k(NMEA2000Msg(msg.pgn, prio=msg.priority, sa=msg.sa, da=msg.da, payload=msg.payload,
                                           timestamp=msg.timestamp))
        elif request.HasField("N0183_msg"):
            msg = request.N0183_msg
            self._callback_0183(nmea0183msg_from_protobuf(msg))
        else:
            _logger.error("pushNMEA unknown type of message")
        return resp

    def status(self, request, context):
        resp = server_resp()
        resp.reportCode = 1
        resp.status = "SERVER_OK"
        return resp


class GrpcDataServer(NavigationGrpcServer):

    def __init__(self, opts, callback_n2k, callback_0183):
        super().__init__(opts)
        add_NMEAInputServerServicer_to_server(GrpcNmeaServicer(callback_n2k, callback_0183), self._grpc_server)
