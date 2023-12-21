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


class MessageServerGlobals:

    pgn_definitions = None
    manufacturers = None
    enums = None
    version = None


def find_pgn(pgn: int, mfg_id: int = 0):
    return MessageServerGlobals.pgn_definitions.pgn_definition(pgn, mfg_id)


def manufacturer_name(mfg_id: int) -> str:
    try:
        return MessageServerGlobals.manufacturers.by_code(mfg_id).name
    except KeyError:
        return "NoName"


class Typedef:

    (UINT, INT, FLOAT, STRING, BYTES) = range(10, 15)
