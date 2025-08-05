#-------------------------------------------------------------------------------
# Name:        server_main.py
# Purpose:     top module for the navigation server
#
# Author:      Laurent Carré
#
# Created:     25/10/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import threading
import datetime

from navigation_server.router_common import MessageServerGlobals, test_exec_hook, GenericTopServer
# from navigation_server.router_common import NavigationConfiguration
from .console import Console
from .publisher import Publisher

_logger = logging.getLogger("ShipDataServer." + __name__)


class NavigationMainServer(GenericTopServer):

    def __init__(self, options):

        super().__init__(options)
        MessageServerGlobals.main_server = self
        self._name = 'router_main'
        self._console = None
        self._couplers = {}
        self._publishers = []
        self._applications = []
        self._filters = []
        self._logfile = None
        self._stop_in_progress = False

        self._stop_lock = threading.Lock()

    def couplers(self):
        return self._couplers.values()

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

    def start(self) -> bool:
        '''
        navigation_definitions start_publisher(pub):
            for coupler in self._couplers:
                coupler.register(pub)
            pub.start()
            changed in version 1.7 => can run with no couplers - can be only a CAN application
            changed in version 2.4 => call super class start first
            '''
        super().start()
        for publisher in self._publishers:
            publisher.start()
        for inst in self._couplers.values():
            inst.request_start()
        return True



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
        self._is_running = False

    def stop_server(self):
        # 2024-09-27 introduce lock to avoid stop reentrance
        self._stop_lock.acquire()
        self._stop_in_progress = True
        for server in self._servers:
            server.stop()
        for inst in self._couplers.values():
            inst.stop()
        for pub in self._publishers:
            if pub.is_alive():
                _logger.info(f"Main: stopping publisher {pub.object_name()}")
                pub.stop()
        # self._console.close()
        self._stop_lock.release()
        _logger.info("All servers stopped")
        # print_threads()

    def request_stop(self, param):
        if self._stop_in_progress:
            _logger.warning("Main server stop request during stop")
            return
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

        new_coupler = None
        if coupler.has_run():
            # now we need to clean up all references
            for server in self._servers:
                server.remove_coupler(coupler)
            # then we create a new coupler instance
            inst_descr = MessageServerGlobals.configuration.coupler(name)
            new_coupler = inst_descr.build_object()
            new_coupler.restart()
            new_coupler.force_start()
            test_exec_hook(name, new_coupler)
            self.add_coupler(new_coupler)
        else:
            coupler.force_start()
            coupler.request_start()
        # update the console
        if self.console_present and new_coupler is not None:
            self._console.add_coupler(new_coupler)
        return "Start request OK"

