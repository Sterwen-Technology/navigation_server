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
from IPInstrument import *

_logger = logging.getLogger("ShipDataServer")


class SimulatorInput(IPInstrument):

    def __init__(self, opts):
        super().__init__(opts)
        self._max_timeouts = opts.get('max_timeouts', 3)
        self._reopen_on_timeout = opts.get('reopen_on_timeout', True)
        self._nb_timeout = 0

    def read(self):
        try:
            return super().read()
        except InstrumentTimeOut:
            self._nb_timeout += 1
            if self._nb_timeout > self._max_timeouts:
                if self._reopen_on_timeout:
                    self.close()
            raise

    def open(self):
        self._nb_timeout = 0
        return super().open()
