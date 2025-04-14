#-------------------------------------------------------------------------------
# Name:        gnss_coupler
# Purpose:     implementation of GNSS NMEA0183 GNSS interface - some features are specific to Ublox
#
# Author:      Laurent Carré
#
# Created:     10/04/2025
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import queue

from navigation_server.router_core import Coupler, NMEA0183Msg, CouplerTimeOut
from navigation_server.router_common import NavThread, NavGenericMsg


_logger = logging.getLogger("ShipDataServer."+__name__)


class GNSSCoupler(Coupler):

    def __init__(self, opts):

        super().__init__(opts)

        self._formatters = opts.getlist('formatters', str, ['RMC', 'GLL'])
        self._constellations = opts.getlist('constellations', str, None)
        self._pgn_output = opts.getlist('pgn_output', int, [129025, 129026, 129029])
        self._fixed = False
        self._reader = None
        self._fp = None
        self._input_queue = queue.SimpleQueue()


    def open(self) -> bool:
        """
        Open the link and start the reading flow
        """
        return False

    def stop(self):
        super().stop()


    def close(self):
        pass

    def _read(self) -> NavGenericMsg:
        pass





