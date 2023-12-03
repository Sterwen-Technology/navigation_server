# -------------------------------------------------------------------------------
# Name:        NMEA2K-Bitfield generator from XML
# Purpose:     Abstract superclass holding the bitfield analysis
#
# Author:      Laurent Carré
# Created:     03/12/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from nmea2000.nmea2k_encode_decode import BitField, BitFieldSplitException

_logger = logging.getLogger("ShipDataServer." + __name__)


class BitFieldGenerator:

    (NO_BITFIELD, NEW_BITFIELD, BITFIELD_IN_PROGRESS) = range(0, 3)

    def __init__(self):
        self._bitfield_in_create = None
        self._bitfield_no = 1

    def add_field(self, field):
        raise NotImplementedError

    @property
    def id(self) -> int:
        raise NotImplementedError

    def check_bf_add_field(self, fo):
        bf_state = self.check_bitfield(fo)
        if bf_state == self.NO_BITFIELD:
            self.add_field(fo)
        elif bf_state == self.NEW_BITFIELD:
            self.add_field(self._bitfield_in_create)

    def check_bitfield(self, field) -> int:
        if field.is_bit_value():
            if self._bitfield_in_create is not None:
                try:
                    self._bitfield_in_create.add_field(field)
                    return self.BITFIELD_IN_PROGRESS
                except BitFieldSplitException:
                    self._bitfield_in_create.finalize()
                    self._bitfield_in_create = BitField(field, self._bitfield_no)
                    self._bitfield_no += 1
                    return self.NEW_BITFIELD
            else:
                self._bitfield_in_create = BitField(field, self._bitfield_no)
                self._bitfield_no += 1
                return self.NEW_BITFIELD
        else:
            if self._bitfield_in_create is not None:
                self._bitfield_in_create.finalize()
                self._bitfield_in_create = None
            return self.NO_BITFIELD

    def check_and_finalize(self):
        if self._bitfield_in_create is not None:
            try:
                self._bitfield_in_create.finalize()
            except ValueError:
                _logger.error("PGN %d error finalizing last bitfield" % self.id)
