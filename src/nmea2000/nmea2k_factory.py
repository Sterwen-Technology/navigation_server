# -------------------------------------------------------------------------------
# Name:        nmea2k_factory
# Purpose:     Build NMEA2000Objects from a message
#
# Author:      Laurent Carré
#
# Created:     26/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from nmea2000.nmea2k_iso_messages import *
from nmea2000.nmea2000_msg import NMEA2000Msg, NMEA2000Object

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000Factory:

    table = {
        59904: ISORequest,
        60928: AddressClaim,
        126996: ProductInformation
    }

    @staticmethod
    def build_n2k_object(message: NMEA2000Msg):
        try:
            obj = NMEA2000Factory.table[message.pgn]()
        except KeyError:
            _logger.warning("Cannot build NMEA2000Object class for PGN %d - build generic object instead" % message.pgn)
            obj = NMEA2000Object(message.pgn)
        return obj.from_message(message)


