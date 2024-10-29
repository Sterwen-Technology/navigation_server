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


MessageServerGlobals.version = "2.06b"
default_base_dir = "/mnt/meaban/Sterwen-Tech-SW/navigation_server"
_logger = logging.getLogger("ShipDataServer.main")


def main():
    """
    Generic main for all servers or services
    options:
    --settings: filename of the specific configuration file of the server/service
    --working_dir: working directory for the service, practically this shall be the head directory of the
                   navigation_server software
    """
    # initialise command line arguments
    opts = init_options(default_base_dir)

    # set log for the configuration phase
    NavigationLogSystem.create_log("Starting %s version %s - copyright Sterwen Technology 2021-2024")

    # build the configuration from the file
    config = NavigationConfiguration().build_configuration(opts.settings)
    NavigationLogSystem.finalize_log(config)
    _logger.info("Navigation server working directory:%s" % os.getcwd())
    # dynamically import modules declared in the configuration file
    config.initialize_features(config)
    # create all server or service objects
    config.build_objects()

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
    main()
    _logger.info("Navigation server main thread ends")
