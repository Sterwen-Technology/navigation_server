#-------------------------------------------------------------------------------
# Name:        NMEA_Statistics
# Purpose:     Compute statistics on NMEA traffic
#
# Author:      Laurent Carré
#
# Created:     25/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2002
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging


_logger = logging.getLogger("Data_analyser")


class NMEA183StatEntry:

    def __init__(self, talker, formatter):
        self._talker = talker
        self._formatter = formatter
        self._count = 0


class NMEA183Statistics:

    def __init__(self):
        self._entries = {}

