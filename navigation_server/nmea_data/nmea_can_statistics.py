#-------------------------------------------------------------------------------
# Name:        NMEA_Statistics (CAN based)
# Purpose:     Compute statistics on NMEA traffic
#
# Author:      Laurent Carré
#
# Created:     08/02/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

_logger = logging.getLogger("ShipDataServer." + __name__)



class CanAddressStatRecord:

    def __init__(self, sa):
        self._sa = sa
        self._pgn_stat = {}

    def record_pgn(self, pgn: int):
        try:
            self._pgn_stat[pgn] += 1
        except KeyError:
            self._pgn_stat[pgn] = 1

    def record_string(self) -> str:
        sorted_stat = {pgn: self._pgn_stat[pgn] for pgn in sorted(self._pgn_stat.keys())}
        return f"ADDR:{self._sa} PGN: {sorted_stat}"

    def sorted_tuple_list(self) -> list:
        return [item for item in sorted(self._pgn_stat.items())]


class CanStat:

    def __init__(self):
        self._addr_stat = {}

    def record_msg(self, sa:int, pgn: int):
        try:
            addr_record = self._addr_stat[sa]
        except KeyError:
            addr_record = CanAddressStatRecord(sa)
            self._addr_stat[sa] = addr_record
        addr_record.record_pgn(pgn)

    def print_stat(self, output_file):
        # sort addresses
        for address in sorted(self._addr_stat.keys()):
            output_file.write(self._addr_stat[address].record_string())
            output_file.write('\n')
            output_file.flush()
