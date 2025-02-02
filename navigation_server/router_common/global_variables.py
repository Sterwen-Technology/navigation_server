# -------------------------------------------------------------------------------
# Name:        global_variables
# Purpose:     class handling system global variables
#
# Author:      Laurent Carré
#
# Created:     24/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import inspect
import os.path

_logger = logging.getLogger("ShipDataServer." + __name__)


class MessageServerGlobals:

    pgn_definitions = None
    manufacturers = None
    enums = None
    units = None
    version = None
    configuration = None
    global_variables = None
    server_name: str = None
    data_dir = None
    thread_controller = None
    profiling_controller = None
    main_server = None
    root_package = None
    home_dir = None


def set_root_package(root_object):
    """
    store the name of the root package in the globals
    """
    root_module=root_object.__module__
    dot = root_module.find(".")
    MessageServerGlobals.root_package = root_module[:dot]
    if os.getenv("NAVIGATION_HOME", None) is not None:
        home = os.getenv("NAVIGATION_HOME")
        MessageServerGlobals.home_dir = home
    else:
        source_file = inspect.getfile(root_object)
        base_dir = os.path.dirname(source_file)
        home_dir = os.path.split(base_dir)
        MessageServerGlobals.home_dir = home_dir[0]


def find_pgn(pgn: int, mfg_id: int = 0):
    return MessageServerGlobals.pgn_definitions.pgn_definition(pgn, mfg_id)


def manufacturer_name(mfg_id: int) -> str:

    try:
        return MessageServerGlobals.manufacturers.by_code(mfg_id).name
    except KeyError:
        return "NoName"


def resolve_ref(name: str):
    return MessageServerGlobals.configuration.get_object(name)


def resolve_class(name: str):
    return MessageServerGlobals.configuration.get_class(name)


def set_global_var(key, value):
    MessageServerGlobals.configuration.set_global(key, value)


def get_global_var(key):
    return MessageServerGlobals.configuration.get_global(key)


def get_global_option(key, default):
    return MessageServerGlobals.configuration.get_option(key, default)

def get_global_enum(key):
    return MessageServerGlobals.enums.get_enum(key)


def set_hook(key, hook):
    _logger.debug("Setting hook for key:%s" % key)
    MessageServerGlobals.configuration.store_hook(key, hook)


def test_exec_hook(key, target):
    _logger.debug("Resolving hook for %s" % key)
    try:
        hook_func = MessageServerGlobals.configuration.get_hook(key)
    except KeyError:
        _logger.info("No hook for key %s" % key)
        return
    hook_func(target)


def server_name() -> str:
    return MessageServerGlobals.server_name


class Typedef:

    (UINT, INT, FLOAT, STRING, BYTES) = range(10, 15)
