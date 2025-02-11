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

import os
import logging
import sys

from navigation_server.router_common import (NavigationConfiguration, NavigationLogSystem, MessageServerGlobals,
                                             init_options, set_root_package, ConfigurationException, ObjectCreationError)

MessageServerGlobals.version = "2.2"
default_base_dir = "/"
_logger = logging.getLogger("ShipDataServer.main")


def server_main():
    """
    Generic main for all servers or services
    options:
    --settings: filename of the specific configuration file of the server/service
    --working_dir: working directory for the service, practically this shall be the head directory of the
                   navigation-server software
    """
    # initialise command line arguments
    opts = init_options(default_base_dir)
    set_root_package(server_main)
    if opts.version:
        sys.stdout.write(MessageServerGlobals.version)
        return

    # set log for the configuration phase
    NavigationLogSystem.create_log("Starting %s version %s - copyright Sterwen Technology 2021-2024")
    # build the configuration from the file
    try:
        config = NavigationConfiguration().build_configuration(opts.settings)
    except (FileNotFoundError, IOError) as err:
        _logger.critical("Error on configuration file => STOP")
        return
    NavigationLogSystem.finalize_log(config)
    _logger.info("Navigation server working directory:%s" % os.getcwd())
    # dynamically import modules declared in the configuration file
    config.initialize_features(config)
    # create all server or service objects
    try:
        config.build_objects()
    except (ConfigurationException, ObjectCreationError):
        _logger.critical("Error in configuration during build => STOP")
        return

    if config.get_option('decode_definition_only', False):
        _logger.info("Decode only mode -> no active server")
        return

    assert MessageServerGlobals.main_server is not None

    _logger.debug("Starting the main server")
    if config.main_server.start():
        if opts.timer is not None:
            # for debug only trace running threads at regular interval
            config.main_server.start_analyser(opts.timer)
        # wait for all threads to stop now
        config.main_server.wait()
        _logger.info("server shall stop now")
        config.main_server.print_threads()
        MessageServerGlobals.profiling_controller.stop_and_output()
        for thread in MessageServerGlobals.thread_controller.running_threads():
            _logger.warning(f"Wrongfully running thread {thread.name})")
    else:
        _logger.critical("Main server did not start properly => stop server")


if __name__ == '__main__':
    server_main()
    _logger.info("Navigation server main thread ends")
