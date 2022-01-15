#-------------------------------------------------------------------------------
# Name:        server_common
# Purpose:     Abstract class for all servers
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import threading
import logging
import socket

from configuration import NavigationConfiguration

_logger = logging.getLogger("ShipDataServer")


class NavTCPServer(threading.Thread):

    def __init__(self, options ):
        self._name = options['name']
        self._port = options['port']
        self._options = options
        if self._port == 0:
            raise ValueError
        super().__init__(name=self._name)
        self._max_connections = options.get('max_connections', 10)
        self._heartbeat = options.get('heartbeat', 30.0)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(('0.0.0.0', self._port))
        self._socket.settimeout(5.0)
        self._stop_flag = False

    def name(self):
        return self._name

    def resolve_ref(self, name):
        reference = self._options[name]
        return NavigationConfiguration.get_conf().get_object(reference)

    def add_instrument(self, instrument):
        pass
