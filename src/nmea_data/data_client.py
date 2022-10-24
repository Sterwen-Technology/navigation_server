#-------------------------------------------------------------------------------
# Name:        data_client
# Purpose:      gRPC client to access NMEA data servers
#
# Author:      Laurent Carré
#
# Created:     23/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

import grpc

from nmea_routing.generic_msg import NavGenericMsg, N2K_MSG, N0183_MSG
from generated.nmea0183_pb2 import nmea0183
from generated.nmea2000_pb2 import nmea2000
from generated.server_pb2 import nmea_msg
from generated.server_pb2_grpc import NavigationServerStub

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEADataClient:

    def __init__(self, opts):

        self._address = "%s:%d" % (opts.get('address', str, '127.0.0.1'), opts.get('port', int, 4505))
        _logger.info("Creating client for data server at %s" % self._address)
        self._channel = grpc.insecure_channel(self._address)
        self._stub = NavigationServerStub(self._channel)


    def send_msg(self, msg_to_send: NavGenericMsg):
        msg = nmea_msg()
        if msg_to_send.type() == N0183_MSG:
            msg.N0183_msg = msg_to_send.as_protobuf()
        else:
            msg.N2K_msg = msg_to_send.as_protobuf()

        try:
            resp = self._stub.pushNMEA(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.info("Server not accessible")
