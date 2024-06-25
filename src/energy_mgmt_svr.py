#-------------------------------------------------------------------------------
# Name:        energy_mgmt_svr
# Purpose:     server for all energy related functions
#
# Author:      Laurent Carré
#
# Created:     16/05/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2024
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import logging
import sys
import os
import signal
from argparse import ArgumentParser

from victron_mppt.mppt_reader import MPPTService
from utilities.arguments import init_options
from utilities.log_utilities import NavigationLogSystem
from nmea_routing.configuration import NavigationConfiguration, ConfigurationException
from nmea_routing.grpc_server_service import GrpcServer
from utilities.global_exceptions import ObjectCreationError, ObjectFatalError

_version = "V1.10"


_logger = logging.getLogger("ShipDataServer.energy_main")
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"


class EnergyMainServer:

    def __init__(self):
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


def main():
    opts = init_options(default_base_dir)
    NavigationLogSystem.create_log(
        "Starting Navigation Energy manager %s - copyright Sterwen Technology 2021-2024" % _version)

    config = NavigationConfiguration(opts.settings)
    config.add_class(GrpcServer)
    config.add_class(MPPTService)
    NavigationLogSystem.finalize_log(config)
    _logger.info("Navigation Energy management working directory:%s" % os.getcwd())
    main_server = EnergyMainServer()

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
    main_server.start()
    main_server.wait()


if __name__ == '__main__':
    main()
