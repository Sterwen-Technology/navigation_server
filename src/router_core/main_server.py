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

import logging
import signal
import threading
import datetime
import os

from router_common import MessageServerGlobals
# from router_common import NavigationConfiguration
from .console import Console
from .publisher import Publisher

_logger = logging.getLogger("ShipDataServer." + __name__)


class NavigationMainServer:

    def __init__(self, options):

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
            inst_descr = MessageServerGlobals.configuration.coupler(name)
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

