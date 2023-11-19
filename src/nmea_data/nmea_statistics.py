#-------------------------------------------------------------------------------
# Name:        NMEA_Statistics
# Purpose:     Compute statistics on NMEA traffic
#
# Author:      Laurent Carré
#
# Created:     25/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from nmea2000.nmea2k_pgndefs import PGNDefinitions, N2KUnknownPGN
from nmea2000.nmea2000_msg import NMEA2000Msg


_logger = logging.getLogger("Data_analyser")


class NMEA183StatEntry:

    def __init__(self, talker, formatter):
        self._talker = talker
        self._formatter = formatter
        self._count = 0

    def add_count(self):
        self._count += 1

    def __str__(self):
        return "%s:%s count:%d" % (self._talker, self._formatter, self._count)


class NMEA183Statistics:

    def __init__(self):
        self._entries = {}
        self._total_msg = 0

    def add_entry(self, talker, formatter):
        key = talker + formatter
        self._total_msg += 1
        new_entry = False
        try:
            entry = self._entries[key]
        except KeyError:
            entry = NMEA183StatEntry(talker, formatter)
            new_entry = True
        entry.add_count()
        if new_entry:
            self._entries[key] = entry

    def print_entries(self):
        print("Total number of N0183 messages:%d" % self._total_msg)
        for entry in self._entries.values():
            print(entry)


class N2KStatEntry:

    def __init__(self, pgn, sa, mfg):
        self._pgn = pgn
        self._sa = sa
        self._mfg = mfg
        self._count = 0

    def add_count(self):
        self._count += 1

    def __str__(self):
        try:
            pgn_name = PGNDefinitions.pgn_definition(self._pgn, self._mfg).name
        except N2KUnknownPGN:
            pgn_name = "Unknown (Mfg=%d)" % self._mfg

        return "PGN %d (%s) sa %d: %d" % (self._pgn, pgn_name, self._sa, self._count)


class N2KStatistics:

    def __init__(self):
        self._entries = {}
        self._total_msg = 0

    def add_entry(self, msg):

        if PGNDefinitions.is_pgn_proprietary(msg.pgn):
            manufacturer = msg.get_manufacturer()
            # print("PGN", msg.pgn, "Manufacturer", manufacturer)
            key = msg.sa << 29 + msg.pgn << 11 + manufacturer
        else:
            manufacturer = 0
            key = msg.sa << 18 + msg.pgn
        self._total_msg += 1
        new_entry = False
        try:
            entry = self._entries[key]
        except KeyError:
            entry = N2KStatEntry(msg.pgn, msg.sa, manufacturer)
            new_entry = True
        entry.add_count()
        if new_entry:
            self._entries[key] = entry

    def print_entries(self):
        print("Total number of N2K messages:%d" % self._total_msg)
        for entry in self._entries.values():
            print(entry)

