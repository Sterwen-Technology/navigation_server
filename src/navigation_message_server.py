#-------------------------------------------------------------------------------
# Name:        navigation_message_server.py
# Purpose:     top module for the navigation server
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import sys
import os
from argparse import ArgumentParser
import signal
import threading
import logging
import datetime

try:
    from nmea2000.nmea2k_active_controller import NMEA2KActiveController

except ModuleNotFoundError as e:
    print("Error in python-can import", e)
    include_can = False
else:
    print("CAN interface included")
    include_can = True
from nmea0183 import nmea0183_msg
from nmea_routing.message_server import NMEAServer, NMEASenderServer
from nmea_routing.grpc_server_service import GrpcServer
from nmea_routing.shipmodul_if import ShipModulInterface, ShipModulConfig
from nmea_routing.console import Console
from nmea_routing.publisher import Publisher, Injector, PrintPublisher
# from nmea_routing.client_publisher import *
from nmea_routing.internal_gps import InternalGps
from nmea2000.nmea2k_publisher import N2KTracePublisher, N2KStatisticPublisher
# from simulator_input import *
from nmea_routing.configuration import NavigationConfiguration, ConfigurationException
from nmea_routing.nmea_tcp_coupler import NMEATCPReader
from nmea_routing.ikonvert import iKonvert
from nmea2000.nmea2k_pgndefs import PGNDefinitions
from nmea2000.nmea2k_manufacturers import Manufacturers
from nmea2000.nmea2k_controller import NMEA2KController
if include_can:
    from nmea2000.nmea2k_can_coupler import DirectCANCoupler
from victron_mppt.mppt_coupler import MPPT_Coupler
from nmea_routing.ydn2k_coupler import YDCoupler
from nmea_routing.serial_nmeaport import NMEASerialPort
# from nmea_data.data_client import NMEAGrpcDataClient
from nmea_routing.filters import NMEA0183Filter, NMEA2000Filter, NMEA2000TimeFilter
from log_replay.raw_log_coupler import RawLogCoupler
from nmea_routing.grpc_nmea_coupler import GrpcNmeaCoupler
from nmea2000.nmea2k_grpc_publisher import GrpcPublisher
from nmea2000.grpc_input_application import GrpcInputApplication

from utilities.log_utilities import NavigationLogSystem
from utilities.global_exceptions import ObjectCreationError, ObjectFatalError
from utilities.global_variables import MessageServerGlobals


def _parser():
    p = ArgumentParser(description=sys.argv[0])

    p.add_argument('-s', '--settings', action='store', type=str, default='./conf/settings.yml')
    p.add_argument('-d', '--working_dir', action='store', type=str)
    p.add_argument("-t", "--timer", action='store', type=float, default=None)

    return p


MessageServerGlobals.version = "V1.80"
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"
parser = _parser()
_logger = logging.getLogger("ShipDataServer.main")


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


class NavigationMainServer:

    def __init__(self):

        self._name = 'main'
        self._console = None
        self._servers = []
        self._couplers = {}
        self._publishers = []
        self._services = []
        self._applications = []
        self._filters = []
        self._sigint_count = 0
        self._is_running = False
        self._logfile = None
        self._start_time = 0
        self._start_time_s = "Not started"
        self._analyse_timer = None
        self._analyse_interval = 0

        signal.signal(signal.SIGINT, self.stop_handler)

    @property
    def couplers(self):
        return self._couplers.values()

    @property
    def name(self):
        return self._name

    @property
    def console_present(self) -> bool:
        return self._console is not None

    @property
    def console(self):
        return self._console

    def class_name(self):
        return self.__class__.__name__

    @staticmethod
    def version():
        return MessageServerGlobals.version

    def add_server(self, server):
        self._servers.append(server)

    def start(self) -> bool:
        '''
        def start_publisher(pub):
            for coupler in self._couplers:
                coupler.register(pub)
            pub.start()
            changed in version 1.7 => can run with no couplers - can be only a CAN application
            '''

        for service in self._services:
            service.finalize()
        for publisher in self._publishers:
            publisher.start()
        for server in self._servers:
            _logger.debug("starting server %s class:%s" % (server.name, server.__class__.__name__))
            server.start()
        for inst in self._couplers.values():
            inst.request_start()
        self._is_running = True
        self._start_time = datetime.datetime.now()
        self._start_time_s = self._start_time.strftime("%Y/%m/%d-%H:%M:%S")
        return True

    def start_time_str(self):
        return self._start_time_s

    def wait(self):
        for server in self._servers:
            server.join()
            _logger.info("%s threads joined" % server.name)
        for inst in self._couplers.values():
            if inst.is_alive():
                inst.join()
            _logger.info("Coupler %s thread joined" % inst.object_name())
        _logger.info("Message server all servers and instruments threads stopped")
        if self._analyse_timer is not None:
            self._analyse_timer.cancel()
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
        # print_threads()

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
        self._couplers[coupler.object_name()] = coupler
        for server in self._servers:
            server.add_coupler(coupler)
            # _logger.debug("add coupler %s to %s" % (coupler.name(), server.name()))
            # server.update_couplers()
        if self._is_running:
            coupler.request_start()

    def add_publisher(self, publisher: Publisher):
        self._publishers.append(publisher)
        # publisher.start()

    def add_service(self, service):
        if type(service) is Console:
            if self._console is not None:
                _logger.error("Only one Console can be set")
                raise ValueError
            self._console = service
            for s in self._servers:
                self._console.add_server(s)
            self._console.add_server(self)
        self._services.append(service)

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

    def start_analyser(self, interval):
        self._analyse_interval = interval
        self._analyse_timer = threading.Timer(interval, self.timer_lapse)
        self._analyse_timer.start()

    def timer_lapse(self):
        print_threads()
        self._analyse_timer = threading.Timer(self._analyse_interval, self.timer_lapse)
        self._analyse_timer.start()


def print_threads():
    _logger.info("Number of remaining active threads: %d" % threading.active_count())
    _logger.info("Active thread %s" % threading.current_thread().name)
    thl = threading.enumerate()
    for t in thl:
        _logger.info("Thread:%s" % t.name)


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
    # set log for the configuration phase
    NavigationLogSystem.create_log("Starting Navigation server version %s - copyright Sterwen Technology 2021-2024" %
                                   MessageServerGlobals.version)

    # build the configuration from the file
    config = NavigationConfiguration(opts.settings)
    config.add_class(NMEAServer)
    config.add_class(NMEASenderServer)
    config.add_class(GrpcServer)
    config.add_class(Console)
    config.add_class(ShipModulConfig)
    config.add_class(ShipModulInterface)
    config.add_class(NMEATCPReader)
    config.add_class(PrintPublisher)
    config.add_class(Injector)
    config.add_class(iKonvert)
    config.add_class(N2KTracePublisher)
    config.add_class(N2KStatisticPublisher)
    config.add_class(GrpcPublisher)
    config.add_class(InternalGps)
    config.add_class(MPPT_Coupler)
    config.add_class(YDCoupler)
    config.add_class(NMEASerialPort)
    config.add_class(NMEA2KController)
    if include_can:
        config.add_class(NMEA2KActiveController)
    #  config.add_class(NMEAGrpcDataClient)
    config.add_class(NMEA0183Filter)
    config.add_class(NMEA2000Filter)
    config.add_class(NMEA2000TimeFilter)

    config.add_class(RawLogCoupler)
    config.add_class(GrpcNmeaCoupler)
    if include_can:
        config.add_class(DirectCANCoupler)
        config.add_class(GrpcInputApplication)

    NavigationLogSystem.finalize_log(config)
    print(__name__)
    _logger.info("Navigation server working directory:%s" % os.getcwd())
    nmea0183_msg.NMEA0183Sentences.init(config.get_option('talker', 'ST'))
    MessageServerGlobals.manufacturers = Manufacturers(config.get_option('manufacturer_xml',
                                                                         './def/Manufacturers.N2kDfn.xml'))
    MessageServerGlobals.pgn_definitions = PGNDefinitions(config.get_option("nmea2000_xml",
                                                                            './def/PGNDefns.N2kDfn.xml'))

    if config.get_option('decode_definition_only', False):
        _logger.info("Decode only mode -> no active server")
        return

    main_server = NavigationMainServer()
    # create the filters upfront
    for inst_descr in config.filters():
        inst_descr.build_object()
    _logger.debug("Filter created")
    for inst_descr in config.applications():
        inst_descr.build_object()
    _logger.debug("Applications created")
    # create the servers
    for server_descr in config.servers():
        try:
            server = server_descr.build_object()
        except (ConfigurationException, ObjectCreationError, ObjectFatalError) as e:
            _logger.error("Error building server %s" % e)
            continue
        main_server.add_server(server)
    _logger.debug("Servers created")
    # create the services and notably the Console
    for data_s in config.services():
        try:
            service = data_s.build_object()
        except (ConfigurationException, ObjectCreationError, ObjectFatalError) as e:
            _logger.error("Error building service:%s" % e)
            continue
        main_server.add_service(service)
    if not main_server.console_present:
        _logger.warning("No console defined")
    _logger.debug("Services created")
    # create the couplers
    for inst_descr in config.couplers():
        try:
            coupler = inst_descr.build_object()
        except (ConfigurationException, ObjectCreationError, ObjectFatalError) as e:
            _logger.error("Error building Coupler:%s" % str(e))
            continue
        main_server.add_coupler(coupler)
        if main_server.console_present:
            main_server.console.add_coupler(coupler)
    _logger.debug("Couplers created")
    # create the publishers
    for pub_descr in config.publishers():
        publisher = pub_descr.build_object()
        main_server.add_publisher(publisher)
    _logger.debug("Publishers created")

    _logger.debug("Starting the main server")
    if main_server.start():
        if opts.timer is not None:
            main_server.start_analyser(opts.timer)
    # print_threads()
        main_server.wait()


if __name__ == '__main__':
    main()
