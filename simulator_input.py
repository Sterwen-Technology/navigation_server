#-------------------------------------------------------------------------------
# Name:        simulator_input
# Purpose:
#
# Author:      Laurent
#
# Created:     17/12/2021
# Copyright:   (c) Laurent 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import socket
import logging
from instrument import *

_logger = logging.getLogger("ShipDataServer")


class SimulatorInput(Instrument):

    def __init__(self, address, port):
        name = "Simulator@%s" % address
        self._address = (address, port)
        super().__init__(name)
        self._socket = None

    def open(self):
        _logger.info("%s opening socket" % self._name)
        try:
            self._socket = socket.create_connection(self._address, timeout=10.)
        except (socket.error, OSError) as err:
            _logger.error("%s cannot open data source %s" % (self._name, str(err)))
            return False
        self._state = self.CONNECTED
        _logger.info("%s connected" % self._name)
        return True

    def read(self):
        try:
            data = self._socket.recv(256)
        except OSError as e:
            raise InstrumentReadError(e)
        return data

    def close(self):
        self._socket.close()
