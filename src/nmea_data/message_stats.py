#-------------------------------------------------------------------------------
# Name:        data_server
# Purpose:      The data server decodes and manage the current set of navigation
#               And more generally the ship data
# Author:      Laurent Carré
#
# Created:     28/01/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import time

from nmea_data.nmea_statistics import N2KStatistics, NMEA183Statistics

_logger = logging.getLogger("ShipDataServer." + __name__)

class DataStatistics:

    def __init__(self):
        self._n2kstats = N2KStatistics()
        self._n183stats = NMEA183Statistics()
        self._server = None
        self._sigtime = 0


    def handler(self, signum, frame):
        t = time.monotonic()
        if t - self._sigtime > 10.0:
            self._sigtime = t
            self._n2kstats.print_entries()
            self._n183stats.print_entries()
        else:
            self._server.stop()

    def set_server(self, server):
        self._server = server

    def add_n2kentry(self, pgn, sa):
        self._n2kstats.add_entry(pgn, sa)

    def add_n183entry(self, talker, formatter):
        self._n183stats.add_entry(talker, formatter)
