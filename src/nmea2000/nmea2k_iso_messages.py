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
from nmea2000.nmea2k_name import NMEA2000Name
from nmea2000.nmea2k_pgndefs import PGNDefinitions

_logger = logging.getLogger("ShipDataServer." + __name__)


class AddressClaim(NMEA2000Object):

    def __init__(self, sa=0, name=None, da=255):
        super().__init__(60928)
        self._sa = sa
        self._da = da
        self._name = name
        self._prio = 6

    def encode_payload(self) -> bytes:
        return self._name.bytes()

    def update(self):
        self._name = self._fields["System ISO Name"]

    @property
    def name(self) -> NMEA2000Name:
        return self._name


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


class ProductInformation(NMEA2000Object):

    def __init__(self):
        super().__init__(126996)
        self._da = 255
        self._prio = 7

    def update(self):
        # no internal representation - only fields
        pass

    def set_field(self, field, value):
        if self._fields is None:
            self._fields = {}
        self._fields[field] = value

    def set_product_information(self, model_id: str, software_version: str, model_version: str, serial_code: str):
        def build_fix_str(val):
            nb_space = 32 - len(val)
            if nb_space < 0:
                raise ValueError
            return val + str(nb_space*' ')

        product_info = build_fix_str(model_id)
        product_info += build_fix_str(software_version)
        product_info += build_fix_str(model_version)
        product_info += build_fix_str(serial_code)
        self.set_field('Product information', product_info)

    def encode_payload(self) -> bytes:
        return self._pgn_def.encode_payload(self._fields)

