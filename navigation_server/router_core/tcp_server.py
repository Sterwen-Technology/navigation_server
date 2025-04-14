#-------------------------------------------------------------------------------
# Name:        server_common
# Purpose:     Abstract class for all servers
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import socket
import collections

from navigation_server.router_common import NavigationServer, NavThread
from .filters import FilterSet

_logger = logging.getLogger("ShipDataServer."+__name__)


ConnectionRecord = collections.namedtuple('ConnectionRecord', ['address', 'port', 'msg_count'])


class NavTCPServer(NavigationServer, NavThread):

    def __init__(self, options):
        super().__init__(options)
        if self._port == 0:
            _logger.error(f"Server {self._name} must have a TCP port defined")
            raise ValueError
        NavThread.__init__(self, name=self._name)
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

