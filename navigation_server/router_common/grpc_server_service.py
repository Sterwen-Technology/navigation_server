#-------------------------------------------------------------------------------
# Name:        grpc_server_service
# Purpose:     gRPC service and server main classes
#
# Author:      Laurent Carré
#
# Created:     25/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import grpc
from concurrent import futures

import threading
import logging

from .server_common import NavigationServer
from navigation_server.router_common import ConfigurationException
from .global_variables import resolve_ref

from navigation_server.generated.grpc_control_pb2 import GrpcCommand, GrpcAck
from navigation_server.generated.grpc_control_pb2_grpc import NavigationGrpcControlServicer, add_NavigationGrpcControlServicer_to_server

_logger = logging.getLogger("ShipDataServer."+__name__)


class GrpcServerError(Exception):
    pass


class NavigationGrpcControlServicerImpl(NavigationGrpcControlServicer):
    """
    That is default service that is included with all GrpcServer
    For the moment only a single method is implemented most to ping and check presence
    """
    def SendCommand(self, request, context):
        _logger.info(f"SendCommand from {context.peer()}")
        response = GrpcAck()
        response.id = request.id
        response.response = "OK"
        return response


class GrpcServer(NavigationServer):

    grpc_server_global = None
    @staticmethod
    def get_grpc_server():
        # print(__name__, "get grpc server", GrpcServer.grpc_server_global)
        return GrpcServer.grpc_server_global.grpc_server

    def __init__(self, options):

        if self.grpc_server_global is not None:
            _logger.critical("Only one gRPC server can run in the system")
            raise ValueError

        super().__init__(options)
        if self._port == 0:
            raise ValueError
        self._end_event = None
        self._wait_lock = threading.Semaphore(0)
        nb_threads = options.get('nb_thread', int, 5)
        address = "0.0.0.0:%d" % self._port
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=nb_threads))
        self._grpc_server.add_insecure_port(address)
        GrpcServer.grpc_server_global = self
        self._running = False
        self._services = []
        # print(__name__, "Building GrpcServer", self.name)
        # add the default service
        self._grpc_service = NavigationGrpcControlServicerImpl()
        add_NavigationGrpcControlServicer_to_server(self._grpc_service, self._grpc_server)

    def server_type(self):
        return "gRPCServer"

    def start(self) -> None:
        _logger.info("Server %s starting on port %d" % (self._name, self._port))
        self._grpc_server.start()
        self._running = True

    def stop(self):
        _logger.debug("Stopping %s GRPC Server" % self._name)
        self._end_event = self._grpc_server.stop(0.1)
        self._wait_lock.release()
        self._running = False

    def join(self):
        _logger.debug("gRPC server enter join - number of running services:%d" % len(self._services))
        if len(self._services) == 0:
            self.stop()
            return
        self._wait_lock.acquire()
        _logger.debug("gRPC Server wait lock released")
        if self._end_event is not None:
            _logger.debug("gRPC Server wait for server termination")
            self._end_event.wait()
            _logger.debug("gRPC Server terminated")
        else:
            self._grpc_server.wait_for_termination()

    @property
    def grpc_server(self):
        return self._grpc_server

    @staticmethod
    def grpc_port() -> int:
        # print(__name__, "GrpcServer get port", GrpcServer.grpc_server_global)
        return GrpcServer.grpc_server_global.port

    def running(self) -> bool:
        return self._running

    def add_service(self, name):
        self._services.append(name)

    def remove_service(self, name):
        self._services.remove(name)
        if len(self._services) == 0:
            self.stop()


class GrpcService:

    def __init__(self, opts):
        self._name = opts.get('name', str, "DefaultGrpcService")
        self._server_name = opts.get('server', str, None)
        if self._server_name is None:
            raise ConfigurationException(f"Service {self._name} missing server reference")
        self._server = None
        _logger.info("Creating service %s on server %s" % (self._name, self._server_name))

    def finalize(self):
        if self._server_name is None:
            raise GrpcServerError("No server defined for the service: %s" % self._name)
        self._server = resolve_ref(self._server_name)
        assert self._server is not None
        self._server.add_service(self._name)

    @property
    def grpc_server(self):
        return self._server.grpc_server

    def stop_service(self):
        self._server.remove_service(self._name)

    @property
    def name(self):
        return self._name


class GrpcSecondaryService(GrpcService):

    def __init__(self, opts):
        super().__init__(opts)
        self._primary_name = opts.get('primary', str, None)
        if self._primary_name is None:
            raise ConfigurationException(f"Secondary service {self._name} missing primary name")
        self._primary_service = None
        _logger.info("Creating service %s on service %s" % (self._name, self._primary_name))

    def finalize(self):
        super().finalize()
        self._primary_service = resolve_ref(self._primary_name)
        assert self._primary_service is not None

