#-------------------------------------------------------------------------------
# Name:        agent_server.py
# Purpose:     main server for the local agent
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import signal
import os

_logger = logging.getLogger("ShipDataServer." + __name__)


class AgentMainServer:

    def __init__(self, options):
        self._servers = []
        self._services = []
        self._sigint_count = 0
        signal.signal(signal.SIGINT, self.stop_handler)

    def add_server(self, server):
        self._servers.append(server)

    def add_service(self, service):
        self._services.append(service)

    def start(self):
        for service in self._services:
            service.finalize()
        for server in self._servers:
            server.start()
        return True

    def stop_server(self):
        for server in self._servers:
            server.stop()

    def wait(self):
        for server in self._servers:
            server.join()

    def stop_handler(self, signum, frame):
        self._sigint_count += 1
        if self._sigint_count == 1:
            _logger.info("SIGINT received => stopping the system")
            self.stop_server()
        else:
            if self._sigint_count > 2:
                os._exit(1)

    def console_present(self):
        # for compatibility
        return False

