#-------------------------------------------------------------------------------
# Name:        client_common
# Purpose:     super class with all client common functions
#
# Author:      Laurent Carré
#
# Created:     05/03/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import grpc
import logging

from navigation_server.router_common import GrpcAccessException


_logger = logging.getLogger("ShipDataClient." + __name__)


class GrpcClient:

    (NOT_CONNECTED, CONNECTING, CONNECTED) = range(10, 13)

    def __init__(self, server):
        self._server = server
        self._channel = None
        self._services = []
        self._state = self.NOT_CONNECTED

        self._req_id = 0

    def connect(self):
        self._channel = grpc.insecure_channel(self._server)
        for service in self._services:
            service.create_stub(self._channel)
        self._state = self.CONNECTING
        _logger.info("Server stub created on %s => connecting" % self._server)

    def add_service(self, service):
        self._services.append(service)
        service.attach_server(self)
        if self._state in (self.CONNECTING, self.CONNECTED):
            service.create_stub(self._channel)

    @property
    def state(self):
        return self._state

    @property
    def address(self):
        return self._server

    def server_call(self, rpc_func, req, response_class):
        _logger.debug("gRPC Client server call")
        self._req_id += 1
        req.id = self._req_id
        try:
            response = rpc_func(req)
            if response_class is not None:
                return response_class(response)
            else:
                return response
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info(f"Server error:{err.details()}")
                # self._state = self.NOT_CONNECTED
            else:
                _logger.error(f"Error accessing server:{err.details()}")
                self._state = self.NOT_CONNECTED
            raise GrpcAccessException

    def server_call_multiple(self, rpc_func, req, response_class):
        _logger.debug("gRPC Client server call with multiple responses")
        self._req_id += 1
        req.id = self._req_id
        try:
            for response in rpc_func(req):
                if response_class is not None:
                    yield response_class(response)
                else:
                    yield response
        except grpc.RpcError as err:
            if err.code() != grpc.StatusCode.UNAVAILABLE:
                _logger.info(f"Server error:{err.details()}")
                # self._state = self.NOT_CONNECTED
            else:
                _logger.error(f"Error accessing server:{err.details()}")
                self._state = self.NOT_CONNECTED
            raise GrpcAccessException


class ServiceClient:

    def __init__(self, stub_class):
        self._stub_class = stub_class
        self._stub = None
        self._server: GrpcClient = None

    def attach_server(self, server:GrpcClient):
        self._server = server

    def create_stub(self, channel):
        self._stub = self._stub_class(channel)

    def _server_call(self, rpc_func, request, response_class):
        if self._server is not None:
            return self._server.server_call(rpc_func, request, response_class)
        else:
            _logger.error("Attempt to call a service not attached to a server")
            raise GrpcAccessException

    def _server_call_multiple(self, rpc_func, request, response_class):
        if self._server is not None:
            for response in self._server.server_call_multiple(rpc_func, request, response_class):
                yield response
        else:
            _logger.error("attempt to call a service not attached to a server")
            raise GrpcAccessException

    def server_state(self):
        return self._server.state
