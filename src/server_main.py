#-------------------------------------------------------------------------------
# Name:        server_main.py
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


# from router_core.main_server import NavigationMainServer


MessageServerGlobals.version = "2.01"
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"
_logger = logging.getLogger("ShipDataServer.main")


def main():
    # global global_configuration

    opts = init_options(default_base_dir)
    # global parameters

    # print("Current directory", os.getcwd())
    # set log for the configuration phase
    NavigationLogSystem.create_log("Starting %s version %s - copyright Sterwen Technology 2021-2024")


    # build the configuration from the file
    config = NavigationConfiguration().build_configuration(opts.settings)
    NavigationLogSystem.finalize_log(config)
    _logger.info("Navigation server working directory:%s" % os.getcwd())
    # nmea0183_msg.NMEA0183Sentences.init(config.get_option('talker', 'ST'))
    config.initialize_features(config)

    config.build_objects()

    if config.get_option('decode_definition_only', False):
        _logger.info("Decode only mode -> no active server")
        return

    _logger.debug("Starting the main server")
    if config.main_server.start():
        if opts.timer is not None:
            config.main_server.start_analyser(opts.timer)
    # print_threads()
        config.main_server.wait()


if __name__ == '__main__':
    main()
