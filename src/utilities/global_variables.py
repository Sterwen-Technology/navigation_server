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


def find_pgn(pgn: int):
    return MessageServerGlobals.pgn_definitions.pgn_definition(pgn)
