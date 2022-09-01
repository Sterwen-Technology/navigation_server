#-------------------------------------------------------------------------------
# Name:        navigation_message_server.py
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

from nmea_routing import nmea0183
from nmea_routing.message_server import NMEAServer
from nmea_routing.shipmodul_if import *
from nmea_routing.console import Console
from nmea_routing.publisher import *
from nmea_routing.client_publisher import *
from nmea_routing.internal_gps import InternalGps
# from simulator_input import *
from nmea_routing.configuration import NavigationConfiguration
from nmea_routing.IPCoupler import NMEA0183TCPReader, NMEA2000TCPReader
from nmea_routing.ikonvert import iKonvert
from nmea2000.nmea2k_pgndefs import PGNDefinitions
from nmea_routing.nmea2000_msg import N2KProbePublisher, N2KTracePublisher
from victron_mppt.mppt_coupler import MPPT_Coupler
from nmea_routing.ydn2k_coupler import YDCoupler
from nmea_routing.serial_nmeaport import NMEASerialPort


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-s', '--settings', action='store', type=str, default='./conf/settings.yml')
    p.add_argument('-d', '--working_dir', action='store', type=str)

    return p


version = "V1.02"
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"
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
        self._couplers = {}
        self._publishers = []
        self._sigint_count = 0
        self._is_running = False
        self._logfile = None

        signal.signal(signal.SIGINT, self.stop_handler)

    @property
    def couplers(self):
        return self._couplers.values()

    def name(self):
        return self._name

    @staticmethod
    def version():
        global version
        return version

    def add_server(self, server):
        if type(server) == Console:
            if self._console is not None:
                _logger.error("Only one Console can be set")
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
            for coupler in self._couplers:
                coupler.register(pub)
            pub.start()
            '''
        for publisher in self._publishers:
            publisher.start()
        for server in self._servers:
            server.start()
        for inst in self._couplers.values():
            inst.request_start()
        self._is_running = True

    def wait(self):
        for server in self._servers:
            server.join()
            _logger.info("%s threads joined" % server.name())
        for inst in self._couplers.values():
            if inst.is_alive():
                inst.join()
            _logger.info("Coupler %s thread joined" % inst.name())
        print_threads()
        self._is_running = False

    def stop_server(self):
        for server in self._servers:
            server.stop()
        for inst in self._couplers.values():
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

    def request_stop(self, param):
        self.stop_server()

    def add_coupler(self, coupler):
        self._couplers[coupler.name()] = coupler
        for server in self._servers:
            server.add_coupler(coupler)
            server.update_couplers()
        if self._is_running:
            coupler.request_start()

    def add_publisher(self, publisher: Publisher):
        self._publishers.append(publisher)
        # publisher.start()

    def start_coupler(self, name: str):
        try:
            coupler = self._couplers[name]
        except KeyError:
            return "Unknown Coupler"
        if coupler.is_alive():
            return "Coupler running"

        if coupler.has_run():
            # now we need to clean up all references
            for server in self._servers:
                server.remove_coupler(coupler)
            inst_descr = NavigationConfiguration.get_conf().coupler(name)
            new_coupler = inst_descr.build_object()
            new_coupler.force_start()
            self.add_coupler(new_coupler)
        else:
            coupler.force_start()
            coupler.request_start()
        return "Start request OK"


def print_threads():
    _logger.info("Number of remaining active threads: %d" % threading.active_count())
    thl = threading.enumerate()
    for t in thl:
        _logger.info("Thread:%s" % t.name)


def adjust_log_level(config):
    modules = config.get_option('log_module', None)
    if modules is None:
        return
    # print(modules)
    for module, level in modules.items():
        mod_log = _logger.getChild(module)
        if mod_log is not None:
            mod_log.setLevel(level)
        else:
            _logger.error("Module %s non-existent" % module)


def main():
    # global global_configuration

    opts = parser.parse_args()
    # global parameters
    if opts.working_dir is not None:
        os.chdir(opts.working_dir)
    else:
        if os.getcwd() != default_base_dir:
            os.chdir(default_base_dir)
    # print("Current directory", os.getcwd())
    config = NavigationConfiguration(opts.settings)
    config.add_class(NMEAServer)
    config.add_class(Console)
    config.add_class(ShipModulConfig)
    config.add_class(ShipModulInterface)
    config.add_class(NMEA0183TCPReader)
    config.add_class(LogPublisher)
    config.add_class(Injector)
    config.add_class(iKonvert)
    config.add_class(N2KTracePublisher)
    config.add_class(N2KProbePublisher)
    config.add_class(InternalGps)
    config.add_class(MPPT_Coupler)
    config.add_class(YDCoupler)
    config.add_class(NMEASerialPort)
    config.add_class(NMEA2000TCPReader)
    # logger setup => stream handler for now
    loghandler = logging.StreamHandler()
    logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
    loghandler.setFormatter(logformat)
    _logger.addHandler(loghandler)
    _logger.setLevel(config.get_option('log_level', 'INFO'))
    adjust_log_level(config)

    _logger.info("Starting Navigation server version %s - copyright Sterwen Technology 2021-2022" % version)
    _logger.info("Navigation server working directory:%s" % os.getcwd())
    nmea0183.NMEA0183Sentences.init(config.get_option('talker', 'ST'))
    PGNDefinitions.build_definitions(config.get_option("nmea2000_xml", './def/PGNDefns.N2kDfn.xml'))
    # PGNDefinitions.print_pgndef(129540, sys.stdout)

    main_server = NavigationServer()
    # create the servers
    for server_descr in config.servers():
        server = server_descr.build_object()
        main_server.add_server(server)
    # create the instruments
    for inst_descr in config.couplers():
        coupler = inst_descr.build_object()
        main_server.add_coupler(coupler)
    # create the publishers
    for pub_descr in config.publishers():
        publisher = pub_descr.build_object()
        main_server.add_publisher(publisher)

    main_server.start()
    # print_threads()
    main_server.wait()


if __name__ == '__main__':
    main()
