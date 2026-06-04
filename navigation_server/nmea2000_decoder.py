#-------------------------------------------------------------------------------
# Name:        nmea2000_decoder
# Purpose:      Interactive decoder for NMEA2000 CAN messages
#
# Author:      Laurent Carré
#
# Created:     03/06/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import logging

from argparse import ArgumentParser

from log_replay.raw_log_reader import RawLogFile, RawLogCANMessage

from nmea2000_datamodel import PGNDef

_logger = logging.getLogger("ShipDataServer")

def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument('-i', '--id', action='store', default=None, type=str, help='CNA ID as HEX string')
    p.add_argument('-d','--data', action='store', default=None, type=str, help='Data as HEX string')
    return p


parser = _parser()


class Options(object):
    def __init__(self, p):
        self.parser = p
        self.options = None

    def __getattr__(self, name):
        if self.options is None:
            self.options = self.parser.parse_args()
        try:
            return getattr(self.options, name)
        except AttributeError:
            raise AttributeError(name)


def main():
    opts = Options(parser)
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel('INFO')

    if opts.id is not None:
        can_id = int(opts.id, 16)
        pgn, da, sa, prio = PGNDef.decode_canid(can_id)
        print(f"PGN={pgn}, DA={da}, SA={sa}, Prio={prio}")



if __name__ == '__main__':
    main()
