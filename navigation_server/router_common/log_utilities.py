#-------------------------------------------------------------------------------
# Name:        Log router_common
# Purpose:     Set of functions to manage logs
#
# Author:      Laurent Carré
#
# Created:     01/08/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import os
import datetime
from .global_variables import MessageServerGlobals
from .translation import translate, t

_logger = logging.getLogger("ShipDataServer")


class NavigationLogSystem:

    loghandler = None
    start_string = " "

    @staticmethod
    def _set_level_on_module(module_name, level):
        module_full_name = f"{MessageServerGlobals.root_package}.{module_name}"
        mod_log = _logger.getChild(module_full_name)
        # print(module, level, mod_log.level)
        if mod_log is not None:
            mod_log.setLevel(level)
            # print(module, level, mod_log.level)
        else:
            _logger.error("Module %s non-existent" % module_name)

    @staticmethod
    def adjust_log_level(config):
        '''
        Adjust the log level for each individual module (file)
        :param config:
        :return:
        '''
        modules = config.get_option('log_module', None)
        if modules is None:
            return
        if type(modules) is not dict:
            _logger.error("Invalid module list in log configuration => ignored")
            return
        # print(modules)
        for module, level in modules.items():
            NavigationLogSystem._set_level_on_module(module, level)

    @staticmethod
    def create_log(start_string: str, options):
        NavigationLogSystem.loghandler = logging.StreamHandler()
        logformat = logging.Formatter("%(asctime)s | [%(levelname)s] %(message)s")
        NavigationLogSystem.loghandler.setFormatter(logformat)
        _logger.addHandler(NavigationLogSystem.loghandler)
        _logger.setLevel('INFO')
        NavigationLogSystem.start_string = start_string
        _logger.info(translate("log.initializing", "Initializing log system"))
        if options.debug:
            NavigationLogSystem._set_level_on_module("router_common.configuration", "DEBUG")

    @staticmethod
    def log_start_string():
        _logger.info(NavigationLogSystem.start_string)

    @staticmethod
    def finalize_log(config):
        log_file = config.get_option("log_file", None)
        if log_file is not None:
            log_dir = MessageServerGlobals.trace_dir
            date_stamp = datetime.datetime.now().strftime("%y%m%d-%H%M")
            log_file_name = f"{log_file}_{date_stamp}.log"
            if log_dir is not None:
                log_fullname = os.path.join(log_dir, log_file_name)
            else:
                _logger.error(translate("log.invalid_dir", "Invalid directory for logging - keeping stderr"))
                return
            _logger.info(translate("log.redirected", "Logging redirected into: {log_file}", log_file=log_fullname))
            try:
                fp = open(log_fullname, 'w')
                NavigationLogSystem.loghandler.setStream(fp)
            except IOError as e:
                _logger.error(translate("log.error_opening", "Error opening log file {log_file} {error}", log_file=log_fullname, error=str(e)))
                pass
        function_name = config.get_option('function', 'ERROR')
        _logger.info(translate("server.starting", "Starting {server_name} version {version} - copyright Sterwen Technology 2021-2026",
                               server_name=function_name, version=MessageServerGlobals.version))
        _logger.setLevel(config.get_option('log_level', 'INFO'))
        NavigationLogSystem.adjust_log_level(config)

