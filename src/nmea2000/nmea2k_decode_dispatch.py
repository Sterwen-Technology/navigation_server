# -------------------------------------------------------------------------------
# Name:        NMEA2K- Find the right decoding classes and dispatch the message
# Purpose:
#
# Author:      Laurent Carré
# Created:     01/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from generated.nmea2000_classes_gen import nmea2k_generated_classes
from nmea2000.nmea2k_pgn_definition import PGNDef
from nmea2000.generated_base import NMEA2000OptimObject
from nmea2000.nmea2000_msg import NMEA2000Msg

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KMissingDecodeEncodeException(Exception):
    pass


def get_n2k_decoded_object(msg: NMEA2000Msg) -> NMEA2000OptimObject:

    try:
        n2k_obj_class = nmea2k_generated_classes[msg.pgn]
    except KeyError:
        _logger.error(f"No decoding class defined for PGN {msg.pgn}")
        raise N2KMissingDecodeEncodeClass

    if PGNDef.is_pgn_proprietary(msg.pgn):
        # find the actual class for the manufacturer
        mfg_id = msg.get_manufacturer()
        try:
            n2k_obj_class = n2k_obj_class[mfg_id]
        except KeyError:
            _logger.error(f"No decoding class for PGN {msg.pgn} manufacturer id {mfg_id}")
            raise N2KMissingDecodeEncodeClass

    # we have the class, so we can build the object
    return n2k_obj_class(message=msg)





