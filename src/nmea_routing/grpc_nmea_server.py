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

from generated.nmea_server_pb2_grpc import NMEAServerServicer
from generated.nmea_messages_pb2 import nmea_msg, server_resp, server_cmd
from generated.nmea0183_pb2 import nmea0183pb
from generated.nmea2000_pb2 import nmea2000pb
from nmea_routing.server_common import NavigationGrpcServer
from nmea_routing.publisher import Publisher

_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcNMEAPublisher(Publisher):

    def __init__(self, couplers, queue, filters, name):
        super().__init__(None, internal=True, couplers=couplers, filters=filters, name=name)


class NMEAServerServicerImpl(NMEAServerServicer):

    def __init__(self, server):
        self._server = server

    def status(self, request, context):
        _logger.debug("NMEA GrPc Server request received:%s" % request.cmd)
        resp = server_resp()
        resp.reportCode = 0
        resp.status = "SERVER_OK"
        return resp

    def getNMEA(self, request, context):
        '''
        Need to open a new stream
        '''
        publisher = Publisher()
        while True:
            msg = publisher.get_message()
            if msg is None:
                break
            yield msg
