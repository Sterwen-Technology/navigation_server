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
from nmea_routing.filters import FilterSet
from nmea_routing.publisher import Publisher

from generated.nmea_messages_pb2 import nmea_msg, server_cmd
from generated.input_server_pb2_grpc import NMEAInputServerStub


_logger = logging.getLogger("ShipDataServer."+__name__)


class NMEAGrpcDataClient:

    def __init__(self, opts):

        self._name = opts['name']
        self._address = "%s:%d" % (opts.get('address', str, '127.0.0.1'), opts.get('port', int, 4504))
        _logger.info("Creating client for data server at %s" % self._address)
        self._channel = grpc.insecure_channel(self._address)
        self._stub = NMEAInputServerStub(self._channel)
        self._couplers = []
        self._filters = None
        filter_names = opts.getlist('filters', str)
        if filter_names is not None and len(filter_names) > 0:
            self._filters = FilterSet(filter_names)
        self._publisher = None
        self._nmea0183_raw = opts.get('nmea0138_raw', bool, True)


    def name(self):
        return self._name

    def send_msg(self, msg_to_send: NavGenericMsg):
        _logger.debug("DataClient send_msg %s" % msg_to_send.printable())
        msg = nmea_msg()

        if msg_to_send.type == N0183_MSG:
            msg_to_send.as_protobuf(msg.N0183_msg, set_raw=self._nmea0183_raw)
        else:
            msg_to_send.as_protobuf(msg.N2K_msg)

        try:
            resp = self._stub.pushNMEA(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.error("Data client %s GRPC Server %s not accessible" % (self._name, self._address))
                self._publisher.stop()

    def add_coupler(self, coupler):
        self._couplers.append(coupler)

    def start(self):
        _logger.info("Starting GRPC data client:%s for server:%s" % (self._name, self._address))
        if self.check_status():
            _logger.info("Data GRPC server %s ready" % self._name)
        self._publisher = GRPCDirectPublisher(self, self._couplers, self._filters)
        self._publisher.start()

    def stop(self):
        self._publisher.stop()

    def check_status(self):
        msg = server_cmd()
        msg.cmd = "TEST_STATUS"
        try:
            resp = self._stub.status(msg)
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.error("Server Status - Error accessing server:%s" % err)
            else:
                _logger.error("Data client %s GRPC Server %s not accessible" % (self._name, self._address))
            return False
        if resp.status == "SERVER_OK":
            return True
        else:
            return False


class GRPCDirectPublisher(Publisher):

    def __init__(self, client, couplers, filters):
        super().__init__(None, internal=True, couplers=couplers, name=client.name(), filters=filters)
        self._client = client

    def process_msg(self, msg):
        self._client.send_msg(msg)
        return True



