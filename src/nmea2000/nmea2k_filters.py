#-------------------------------------------------------------------------------
# Name:        nmea2k_filters
# Purpose:     Implementation of filters for NMEA2000 messages
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from router_core import NMEAFilter, TimeFilter
from router_common import N2K_MSG
from router_core import NMEA2000Msg

_logger = logging.getLogger('ShipDataServer.' + __name__)


class NMEA2000Filter(NMEAFilter):

    def __init__(self, opts):
        super().__init__(opts)
        self._pgns = opts.getlist('pgn', int, None)
        self._sa = opts.get('source', int, None)

    def valid(self) -> bool:
        if self._pgns is not None or self._sa is not None:
            return super().valid()
        else:
            return False

    def process_n2k(self, msg: NMEA2000Msg) -> bool:

        if self._sa is None or self._sa == msg.sa:
            sa = True
        else:
            sa = False
        if self._pgns is None or msg.pgn in self._pgns:
            pgn = True
        else:
            pgn = False
        result = sa and pgn
        if result:
            _logger.debug("Processing N2K filter %s with message %s ==>> OK in" % (self._name, msg.format2()))
        return result

    def message_type(self):
        return N2K_MSG


class NMEA2000TimeFilter(NMEA2000Filter):

    def __init__(self, opts):
        super().__init__(opts)
        self._period = opts.get('period', float, 0.0)
        self._timers = {}
        if self._pgns is None:
            self._timers[0] = TimeFilter(self._period)
        else:
            for pgn in self._pgns:
                self._timers[pgn] = TimeFilter(self._period)

    def valid(self) -> bool:
        if self._period > 0.0:
            return super().valid()
        else:
            return False

    def action(self, msg) -> bool:
        _logger.debug("NMEA2000TimeFilter for PGN %d" % msg.pgn)
        result = self._timers[msg.pgn].check_period()
        if result:
            _logger.debug("Time filter for %s => go" % self._name)
            if self._type == 'select':
                return True
            else:
                return False
        else:
            return False

