# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN messages classes
# Purpose:     Classes to implement ISO and CAN services messages 59904, 60928, 65240, 126992, 126993, 126996
#
# Author:      Laurent Carré
#
# Created:     18/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from nmea2000.nmea2000_msg import NMEA2000Msg, NMEA2000Object

_logger = logging.getLogger("ShipDataServer." + __name__)


class AddressClaim(NMEA2000Object):

    def __init__(self, sa=0, name=None):
        super().__init__(60928)
        self._sa = sa
        self._name = name
        self._prio = 6

    def encode_payload(self) -> bytes:
        return self._name.bytes()


class ProductInfo(NMEA2000Object):

    def __init__(self, sa=0):
        super.__init__(126996)
        self._sa = sa
        self._prio = 7


class ISORequest(NMEA2000Object):

    def __init__(self, sa=0, da=255, request_pgn=60928):
        super().__init__(59904)
        self._sa = sa
        self._da = da
        self._req_pgn = request_pgn

    def encode_payload(self) -> bytes:
        return bytes([
            self._req_pgn & 0xFF, (self._req_pgn >> 8) & 0xFF, (self._req_pgn >> 16) & 0xFF
        ])

    def update(self):
        try:
            self._req_pgn = self._fields['PGN']
        except KeyError:
            _logger.error("ISORequest error decoding NMEA2000 message missing PGN: %s" % self._fields)

    @property
    def request_pgn(self):
        return self._req_pgn


