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

from src.IPInstrument import *

_logger = logging.getLogger("ShipDataServer")


class SimulatorInput(IPInstrument):

    def __init__(self, opts):
        super().__init__(opts)
        self._max_timeouts = opts.get('max_timeouts', int, 3)
        self._reopen_on_timeout = opts.get('reopen_on_timeout', bool, True)
        self._nb_timeout = 0

    def read(self):
        try:
            return super().read()
        except (InstrumentTimeOut, InstrumentReadError):
            self._nb_timeout += 1
            if self._nb_timeout > self._max_timeouts:
                _logger.info("Simulator read max errors reached")
                if self._reopen_on_timeout:
                    _logger.info("%s closing socket" % self.name())
                    self.close()
            raise

    def open(self):
        self._nb_timeout = 0
        return super().open()
