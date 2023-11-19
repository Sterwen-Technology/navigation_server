#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      Laurent
#
# Created:     14/04/2019
# Copyright:   (c) Laurent 2019
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import sys
import logging

from argparse import ArgumentParser

from log_replay.raw_log_reader import RawLogFile, RawLogCANMessage

_logger = logging.getLogger("ShipDataServer")

def _parser():
    p = ArgumentParser(description=sys.argv[0])
    p.add_argument("-o", "--output", action="store", type=str)
    p.add_argument('-f', '--file', action='store', default=None, help='File for input instead of server')
    p.add_argument("-p", "--port", action="store", type=int,
                   default=3555,
                   help="Listening port for NMEA input, default is 3555")
    p.add_argument("-a", "--address", action="store", type=str,
                   default='',
                   help="IP address or URL for NMEA Input, default is localhost")
    p.add_argument("-pr", "--protocol", action="store", type=str,
                   choices=['TCP','UDP'], default='TCP',
                   help="Protocol to read NMEA sentences, default TCP")
    p.add_argument('-s','--sleep', action='store', type=float, default=0.25)

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

    records = RawLogFile(opts.file)
    for msg in records.get_messages(0, 50):
        print(msg)
    print("Source addresses", RawLogCANMessage.source_addresses)


if __name__ == '__main__':
    main()
