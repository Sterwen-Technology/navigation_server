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

_logger = logging.getLogger("ShipDataServer." + __name__)

class MessageServerGlobals:

    pgn_definitions = None
    manufacturers = None
    enums = None
    version = None
    configuration = None
    global_variables = None


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


class Typedef:

    (UINT, INT, FLOAT, STRING, BYTES) = range(10, 15)
