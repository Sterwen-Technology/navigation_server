#-------------------------------------------------------------------------------
# Name:        server_common
# Purpose:     Abstract class for all servers
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import threading
import logging
import socket
import collections
import grpc
from concurrent import futures

from nmea_routing.configuration import NavigationConfiguration
from nmea_routing.filters import FilterSet

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NavigationServer:

    def __init__(self, opts):
        self._name = opts['name']
        self._port = opts.get('port', int, 0)
        self._options = opts

    def name(self):
        return self._name

    def class_name(self):
        return self.__class__.__name__

    def resolve_ref(self, name):
        try:
            reference = self._options[name]
        except KeyError:
            _logger.error("Unknown reference %s" % name)
            return None
        try:
            value = NavigationConfiguration.get_conf().get_object(reference)
        except KeyError:
            return None
        _logger.debug("Server resolve name %s ref %s result:%s" % (name, reference, value))
        return value

    def add_coupler(self, instrument):
        pass

    def remove_coupler(self, instrument):
        pass

    def update_couplers(self):
        pass

    def server_type(self):
        raise NotImplementedError("To be implemented in subclass")

    def nb_connections(self):
        return 0

    def protocol(self):
        return "N/A"

    @property
    def port(self):
        return self._port


ConnectionRecord = collections.namedtuple('ConnectionRecord', ['address', 'port', 'msg_count'])


class NavTCPServer(NavigationServer, threading.Thread):

    def __init__(self, options):
        super().__init__(options)
        if self._port == 0:
            raise ValueError
        threading.Thread.__init__(self, name=self._name)
        self._max_connections = options.get('max_connections', int, 10)
        self._heartbeat = options.get('heartbeat', float, 30.0)
        self._timeout = options.get('timeout', float, 5.0)
        self._max_silent = options.get('max_silent', float, 120.0)
        self._max_silent_period = max((int(self._max_silent / self._heartbeat), 1))
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(('0.0.0.0', self._port))
        self._socket.settimeout(self._timeout)
        self._stop_flag = False
        self._filters = None
        filter_names = options.getlist('filters', str)
        if filter_names is not None and len(filter_names) > 0:
            self._filters = FilterSet(filter_names)

    def running(self) -> bool:
        return self.is_alive()

    def server_type(self):
        return 'TCP'


class NavigationGrpcServer(NavigationServer):

    def __init__(self, options):

        super().__init__(options)
        if self._port == 0:
            raise ValueError
        self._end_event = None
        address = "0.0.0.0:%d" % self._port
        self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        self._grpc_server.add_insecure_port(address)

    def start(self) -> None:
        _logger.info("Server %s starting on port %d" % (self._name, self._port))
        self._grpc_server.start()

    def stop(self):
        _logger.info("Stopping %s GRPC Server" % self._name)
        self._end_event = self._grpc_server.stop(0.1)

    def join(self):
        if self._end_event is not None:
            self._end_event.wait()
