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

import threading
import logging
import socket
import collections

from router_common import resolve_ref

_logger = logging.getLogger("ShipDataServer."+__name__)


class NavigationServer:

    def __init__(self, opts):
        self._name = opts['name']
        self._port = opts.get('port', int, 0)
        self._options = opts

    @property
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
        return self.resolve_direct_ref(reference)

    @staticmethod
    def resolve_direct_ref(reference):
        try:
            value = resolve_ref(reference)
        except KeyError:
            return None
        _logger.debug("Server resolve %s result:%s" % (reference, value))
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


