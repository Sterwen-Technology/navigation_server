#-------------------------------------------------------------------------------
# Name:        generic_top_server.py
# Purpose:     main server for the local agent
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import signal
import os
import threading
import datetime

from .global_variables import MessageServerGlobals

_logger = logging.getLogger("ShipDataServer." + __name__)


class GenericTopServer:

    def __init__(self, options):
        self._name = 'generic_main'
        self._servers = []
        self._services = []
        self._analyse_interval = 0
        self._analyse_timer = None
        self._is_running = False
        self._sigint_count = 0
        self._start_time = 0
        self._start_time_s = "Not started"
        MessageServerGlobals.main_server = self
        signal.signal(signal.SIGINT, self.stop_handler)

    @property
    def name(self):
        return self._name

    def start_time_str(self):
        return self._start_time_s

    def add_server(self, server):
        self._servers.append(server)

    def add_service(self, service):
        self._services.append(service)

    def add_process(self, process):
        raise NotImplementedError("GenericTopServer does not support process management")

    def start(self):
        for service in self._services:
            service.finalize()
        for server in self._servers:
            _logger.debug("starting server %s class:%s" % (server.name, server.__class__.__name__))
            server.start()
        self._is_running = True
        self._start_time = datetime.datetime.now()
        self._start_time_s = self._start_time.strftime("%Y/%m/%d-%H:%M:%S")
        return True

    def stop_server(self):
        for service in self._services:
            service.stop_service()
        for server in self._servers:
            server.stop()

    def wait(self):
        for server in self._servers:
            _logger.debug("Server %s wait for join" % server.name)
            server.join()
            _logger.debug("Server %s joined" % server.name)
        _logger.debug("Top server => all servers joined")

    def stop_handler(self, signum, frame):
        self._sigint_count += 1
        if self._sigint_count == 1:
            _logger.info("SIGINT received => stopping the system")
            self.stop_server()
        else:
            if self._sigint_count > 2:
                os._exit(1)

    @property
    def console_present(self):
        # for compatibility
        return False

    def is_agent(self):
        return False

    def start_analyser(self, interval):
        self._analyse_interval = interval
        self._analyse_timer = threading.Timer(interval, self.timer_lapse)
        self._analyse_timer.start()

    def stop_analyser(self):
        self._analyse_interval = 0

    def timer_lapse(self):
        self.print_threads()
        if self._analyse_interval > 0:
            self._analyse_timer = threading.Timer(self._analyse_interval, self.timer_lapse)
            self._analyse_timer.start()

    def print_threads(self):
        _logger.info("Activity analyzer")
        _logger.info("Number of remaining active threads: %d" % threading.active_count())
        _logger.info("Active thread %s" % threading.current_thread().name)
        thl = threading.enumerate()
        for t in thl:
            _logger.info("Thread:%s" % t.name)