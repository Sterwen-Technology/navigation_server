#-------------------------------------------------------------------------------
# Name:        grpc_nmea_input_server
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     20/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging

from generated.input_server_pb2_grpc import NMEAInputServerServicer, add_NMEAInputServerServicer_to_server
from generated.nmea_messages_pb2 import server_resp
from nmea2000.nmea2000_msg import NMEA2000Msg
from nmea0183.nmea0183_msg import nmea0183msg_from_protobuf
from nmea_routing.grpc_server_service import GrpcService, GrpcServerError
from nmea2000.nmea2k_decode_dispatch import get_n2k_object_from_protobuf


_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcNmeaServicer(NMEAInputServerServicer):
    '''
    The class is a generic servicer for incoming NMEA messages
    Current version is a non-streaming one
    All messages types are supported
    NMEA0183
    NMEA2000 Non decoded
    NMEA2000 Decoded protobuf
    '''

    def __init__(self, callback_n2k, callback_0183, callback_pb):
        self._callback_n2k = callback_n2k
        self._callback_0183 = callback_0183
        self._callback_pb = callback_pb
        self._accept_messages = False

    def pushNMEA(self, request, context):
        '''

        '''
        resp = server_resp()
        resp.reportCode = 0
        if not self._accept_messages:
            _logger.debug("GrpcNmeaService not ready")
            return resp

        if request.HasField("N2K_msg"):
            if self._callback_n2k is None:
                resp.reportCode = 1
                resp.status = "NMEA2000 direct messages not supported"
            else:
                msg = request.N2K_msg
                self._callback_n2k(NMEA2000Msg(msg.pgn, prio=msg.priority, sa=msg.sa, da=msg.da, payload=msg.payload,
                                               timestamp=msg.timestamp))
        elif request.HasField("N0183_msg"):
            if self._callback_0183 is None:
                resp.reportCode = 1
                resp.status = " NMEA0183 messages not supported"
            else:
                msg = request.N0183_msg
                self._callback_0183(nmea0183msg_from_protobuf(msg))
        else:
            _logger.error("pushNMEA unknown type of message")
            resp.reportCode = 2
            resp.status = "pushNMEA unknown type of message"
        return resp

    def pushDecodedNMEA2K(self, request, context):
        resp = server_resp()
        resp.reportCode = 0
        if not self._accept_messages:
            _logger.debug("GrpcNmeaService not ready")
            return resp

        if self._callback_pb is None:
            resp.reportCode = 1
            resp.status = "NMEA2000 Protobuf not supported"
        else:
            try:
                n2k_object = get_n2k_object_from_protobuf(request)
            except Exception as e:
                _logger.error("Input server - error converting protobuf:%s" % e)
                resp.reportCode = 1
                resp.status = str(e)
                return resp
            #print(n2k_object)
            self._callback_pb(n2k_object)
        return resp

    def status(self, request, context):
        resp = server_resp()
        resp.reportCode = 1
        resp.status = "SERVER_OK"
        return resp

    def open(self):
        self._accept_messages = True

    def close(self):
        self._accept_messages = False


class GrpcDataService(GrpcService):

    def __init__(self, opts, callback_n2k=None, callback_0183=None, callback_pb=None):
        super().__init__(opts)
        self._callback_n2k = callback_n2k
        self._callback_0183 = callback_0183
        self._callback_pb = callback_pb
        self._servicer = None

    def finalize(self):
        try:
            super().finalize()
        except GrpcServerError:
            return
        _logger.info("Adding service %s to server" % self._name)
        self._servicer = GrpcNmeaServicer(self._callback_n2k, self._callback_0183, self._callback_pb)
        add_NMEAInputServerServicer_to_server(self._servicer, self.grpc_server)

    def open(self):
        if self._servicer is not None:
            try:
                self._servicer.open()
                return True
            except GrpcServerError as err:
                _logger.error("Error opening %s: %s" % (self._name, err))
                return False
        else:
            _logger.error("Attempt to open a non ready service")
            return False

    def close(self):
        if self._servicer is not None:
            self._servicer.close()
