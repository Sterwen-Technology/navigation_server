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

import os
import logging


from router_common import NavigationConfiguration, ConfigurationException
from router_common import NavigationLogSystem
from router_common import ObjectCreationError, ObjectFatalError
from router_common import MessageServerGlobals
from router_common import init_options
from nmea2000 import PGNDefinitions, Manufacturers

# from router_core.main_server import NavigationMainServer


MessageServerGlobals.version = "2.0"
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"
_logger = logging.getLogger("ShipDataServer.main")


def main():
    # global global_configuration

    opts = init_options(default_base_dir)
    # global parameters

    # print("Current directory", os.getcwd())
    # set log for the configuration phase
    NavigationLogSystem.create_log("Starting Navigation server version %s - copyright Sterwen Technology 2021-2024" %
                                   MessageServerGlobals.version)

    # build the configuration from the file
    config = NavigationConfiguration().build_configuration(opts.settings)

    NavigationLogSystem.finalize_log(config)
    _logger.info("Navigation server working directory:%s" % os.getcwd())
    # nmea0183_msg.NMEA0183Sentences.init(config.get_option('talker', 'ST'))
    MessageServerGlobals.manufacturers = Manufacturers(config.get_option('manufacturer_xml',
                                                                         './def/Manufacturers.N2kDfn.xml'))
    MessageServerGlobals.pgn_definitions = PGNDefinitions(config.get_option("nmea2000_xml",
                                                                            './def/PGNDefns.N2kDfn.xml'))

    if config.get_option('decode_definition_only', False):
        _logger.info("Decode only mode -> no active server")
        return

    main_server = config.main.build_object()
    # create the filters upfront
    for inst_descr in config.filters():
        try:
            inst_descr.build_object()
        except ConfigurationException as e:
            _logger.error(str(e))
            continue
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
        try:
            publisher = pub_descr.build_object()
            main_server.add_publisher(publisher)
        except ConfigurationException as e:
            _logger.error(str(e))
            continue
    _logger.debug("Publishers created")

    _logger.debug("Starting the main server")
    if main_server.start():
        if opts.timer is not None:
            main_server.start_analyser(opts.timer)
    # print_threads()
        main_server.wait()


if __name__ == '__main__':
    main()
