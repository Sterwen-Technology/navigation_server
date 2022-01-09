#-------------------------------------------------------------------------------
# Name:        N2K_probe
# Purpose:     probe ofe NMEA2000 network using Digital Yacht iKonvert
#
# Author:      Laurent Carré
#
# Created:     25/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import sys
import os
from argparse import ArgumentParser
import signal

from console import Console
from publisher import *
from client_publisher import *
from ikonvert import iKonvert
from nmea2k_pgndefs import PGNDefinitions
from nmea2000_msg import N2KProbePublisher


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument("-p", "--port", action="store", type=str,
                   default="/dev/ttyUSB1",
                   help="serial port for iKonvert USB/N2K, default=/dev/ttyUSB1")

    p.add_argument('-m', "--mode", action="store", type=str,
                   choices=['NORMAL','ALL'],
                   default='NORMAL')

    p.add_argument('-i', '--interval', action="store", type=float,
                   default=5.0)
    p.add_argument('-d', '--trace_level', action="store", type=str,
                   choices=["CRITICAL","ERROR", "WARNING", "INFO", "DEBUG"],
                   default="INFO",
                   help="Level of traces, default INFO")
    p.add_argument("-l", "--log", action="store", type=str,
                   help="Logfile for all incoming NMEA sentences")
    p.add_argument("-t", "--trace", action="store", type=str)
    return p


parser = _parser()
_logger = logging.getLogger("ShipDataServer")


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


class N2K_probe:

    def __init__(self, opts, console):

        self.name = 'main'

        self._console = console

        self._instrument = iKonvert(opts.port, opts.mode, opts.trace)
        self._injectors = []
        self._logpub = None
        self._sigint_count = 0
        self._is_running = False
        self._logfile = None
        self._pub = None

        try:
            self._logfile = opts.log
            if self._logfile is not None:
                self._logpub = LogPublisher([], self._logfile)
        except AttributeError:
            pass
        signal.signal(signal.SIGINT, self.stophandler)

    def start(self, interval):
        if self._logpub is not None:
            # if instruments are added before start

            self._instrument.register(self._logpub)
            self._logpub.start()

        self._instrument.start()
        self._pub = N2KProbePublisher(self._instrument, interval)
        self._pub.start()

        self._is_running = True

    def wait(self):
        self._instrument.join()
        _logger.info("Instrument %s thread joined" % self._instrument.name())
        print_threads()
        self._pub.dump_records()
        self._is_running = False

    def stop_server(self):

        self._instrument.stop()

        if self._logpub is not None:
            self._logpub.stop()
        # _logger.info("NMEA reader stopped")
        #self._console.close()
        _logger.info("All servers stopped")

    def stophandler(self, signum, frame):
        self._sigint_count += 1
        if self._sigint_count == 1:
            _logger.info("SIGINT received => stopping the system")
            self.stop_server()
        else:
            print_threads()
            if self._sigint_count > 2:
                os._exit(1)
        # sys.exit(0)


def print_threads():
    print("Number of active threads:", threading.active_count())
    thl = threading.enumerate()
    for t in thl:
        print(t.name)


def main():
    opts = Options(parser)
    # logger setup => stream handler for now
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(opts.trace_level)

    PGNDefinitions.build_definitions('PGNDefns.N2kDfn.xml')
    # console = Console(opts)

    server = N2K_probe(opts, None)
    server.start(opts.interval)
    # console.add_injector('GPS', 'InternalGPS', 'Shipmodul')

    server.wait()


if __name__ == '__main__':
    main()
