#-------------------------------------------------------------------------------
# Name:        grpc_server_service
# Purpose:     gRPC service and server main classes
#
# Author:      Laurent Carré
#
# Created:     25/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import grpc
from concurrent import futures

import logging

from nmea_routing.server_common import NavigationServer
from nmea_routing.configuration import NavigationConfiguration

_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcServerError(Exception):
    pass


class GrpcServer(NavigationServer):

    grpc_server_global = None
    @staticmethod
    def get_grpc_server():
        return GrpcServer.grpc_server_global.grpc_server

    def __init__(self, options):

        if self.grpc_server_global is not None:
            _logger.critical("Only one gRPC server can run in the system")
            raise ValueError

        super().__init__(options)
        if self._port == 0:
            raise ValueError
        self._end_event = None
        nb_threads = options.get('nb_thread', int, 5)
        address = "0.0.0.0:%d" % self._port
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=nb_threads))
        self._grpc_server.add_insecure_port(address)
        self.grpc_server_global = self
        self._running = False

    def server_type(self):
        return "gRPCServer"

    def start(self) -> None:
        _logger.info("Server %s starting on port %d" % (self._name, self._port))
        self._grpc_server.start()
        self._running = True

    def stop(self):
        _logger.info("Stopping %s GRPC Server" % self._name)
        self._end_event = self._grpc_server.stop(0.1)
        self._running = False

    def join(self):
        if self._end_event is not None:
            self._end_event.wait()

    @property
    def grpc_server(self):
        return self._grpc_server

    def running(self) -> bool:
        return self._running


class GrpcService:

    def __init__(self, opts):
        self._name = opts.get('name', str, "DefaultGrpcService")
        self._server_name = opts.get('server', str, None)
        self._server = None
        _logger.info("Creating service %s on server %s" % (self._name, self._server_name))

    def finalize(self):
        if self._server_name is None:
            raise GrpcServerError("No server defined for the service: %s" % self._name)
        self._server = NavigationConfiguration.get_conf().get_object(self._server_name)
        assert self._server is not None

    @property
    def grpc_server(self):
        return self._server.grpc_server

