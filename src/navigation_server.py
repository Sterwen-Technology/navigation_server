#-------------------------------------------------------------------------------
# Name:        navigation_server.py
# Purpose:     top module for the navigation server
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import os
from argparse import ArgumentParser
import signal

import nmea0183
from src.data_server import NMEA_server
from shipmodul_if import *
from src.console import Console
from publisher import *
from src.client_publisher import *
from src.internal_gps import InternalGps
from simulator_input import *
from src.configuration import NavigationConfiguration
from src.ikonvert import iKonvert
from nmea2k_pgndefs import PGNDefinitions
from nmea2000_decode import N2kTracePublisher
from nmea2000_msg import N2KProbePublisher


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-s', '--settings', action='store', type=str, default='./settings.yml')

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


class NavigationServer:

    def __init__(self):

        self._name = 'main'
        self._console = None
        self._servers = []
        self._instruments = []
        self._publishers = []
        self._sigint_count = 0
        self._is_running = False
        self._logfile = None

        signal.signal(signal.SIGINT, self.stop_handler)

    @property
    def instruments(self):
        return self._instruments

    def name(self):
        return self._name

    def add_server(self, server):
        if type(server) == Console:
            if self._console is not None:
                _logger.error("Only one Console can bet set")
                raise ValueError
            self._console = server
            for s in self._servers:
                self._console.add_server(s)
            self._console.add_server(self)
        elif self._console is not None:
            self._console.add_server(server)
        self._servers.append(server)

    def start(self):
        '''
        def start_publisher(pub):
            for instrument in self._instruments:
                instrument.register(pub)
            pub.start()
            '''
        for publisher in self._publishers:
            publisher.start()
        for server in self._servers:
            server.start()
        for inst in self._instruments:
            inst.start()
        self._is_running = True

    def wait(self):
        for server in self._servers:
            server.join()
            _logger.info("%s threads joined" % server.name())
        for inst in self._instruments:
            inst.join()
            _logger.info("Instrument %s thread joined" % inst.name())
        print_threads()
        self._is_running = False

    def stop_server(self):
        for server in self._servers:
            server.stop()
        for inst in self._instruments:
            inst.stop()
        for pub in self._publishers:
            pub.stop()
        # self._console.close()
        _logger.info("All servers stopped")

    def stop_handler(self, signum, frame):
        self._sigint_count += 1
        if self._sigint_count == 1:
            _logger.info("SIGINT received => stopping the system")
            self.stop_server()
        else:
            print_threads()
            if self._sigint_count > 2:
                os._exit(1)
        # sys.exit(0)

    def add_instrument(self, instrument):
        self._instruments.append(instrument)
        for server in self._servers:
            server.add_instrument(instrument)
        if self._is_running:
            instrument.start()

    def add_publisher(self, publisher: Publisher):
        self._publishers.append(publisher)
        # publisher.start()


def print_threads():
    print("Number of active threads:", threading.active_count())
    thl = threading.enumerate()
    for t in thl:
        print(t.name)


def main():
    opts = parser.parse_args()
    config = NavigationConfiguration(opts.settings)
    config.add_class(NMEA_server)
    config.add_class(Console)
    config.add_class(ShipModulConfig)
    config.add_class(ShipModulInterface)
    config.add_class(IPInstrument)
    config.add_class(SimulatorInput)
    config.add_class(LogPublisher)
    config.add_class(Injector)
    config.add_class(iKonvert)
    config.add_class(N2kTracePublisher)
    config.add_class(N2KProbePublisher)
    config.add_class(InternalGps)
    # logger setup => stream handler for now
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(config.get_option('trace', 'INFO'))

    # global parameters
    nmea0183.NMEA0183Sentences.init(config.get_option('talker', 'SN'))
    PGNDefinitions.build_definitions(config.get_option("nmea2000_xml", 'def/PGNDefns.N2kDfn.xml'))

    main_server = NavigationServer()
    # create the servers
    for server_descr in config.servers():
        server = server_descr.build_object()
        main_server.add_server(server)
    # create the instruments
    for inst_descr in config.instruments():
        instrument = inst_descr.build_object()
        main_server.add_instrument(instrument)
    # create the publishers
    for pub_descr in config.publishers():
        publisher = pub_descr.build_object()
        print(publisher.descr())
        main_server.add_publisher(publisher)

    main_server.start()
    print_threads()
    main_server.wait()


if __name__ == '__main__':
    main()
