#-------------------------------------------------------------------------------
# Name:        log_analyzer
# Purpose:      Interactive log analyzer for NMEA2000 CAN messages
#
# Author:      Laurent Carré
#
# Created:     06/02/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import logging

from argparse import ArgumentParser

from log_replay.raw_log_reader import RawLogFile, RawLogCANMessage

_logger = logging.getLogger("ShipDataServer")

def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument('-f', '--file', action='store', default=None, help='File for input')
    p.add_argument('-s','--start', action='store', default=0, type=int, help='Start record')
    p.add_argument('-e','--end', action='store', default=0, type=int, help='End record')
    p.add_argument('--pgn_list', action='store', default=None, help='PGN list')
    p.add_argument('-a', '--analyse', action='store_true', default=False, help='analyse only the file')
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

    if opts.file is None:
        _logger.error("Input file name is mandatory")
        return

    log_file = RawLogFile(opts.file)
    log_file.load_file(None, [], input_msg_only=False)
    if opts.analyse:
        return
    records = log_file.records
    index = opts.start
    if opts.end == -1:
        end = len(records)
    else:
        end = opts.end
    while index < end:
        msg = records[index]
        print(f"{msg.direction}|{msg.sa}|{msg.da}|{msg.pgn}:{msg.message}")
        index += 1




if __name__ == '__main__':
    main()
