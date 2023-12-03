# -------------------------------------------------------------------------------
# Name:        generated_base
# Purpose:     Base classes for Python generated classes for NMEA2000
#
# Author:      Laurent Carré
#
# Created:     26/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------


import logging

from nmea2000.nmea2000_msg import NMEA2000Msg
from utilities.global_variables import MessageServerGlobals

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000OptimObject:

    __slots__ = ('_sa', '_ts')

    def __init__(self, message: NMEA2000Msg = None, protobuf=None):

        if message is not None:
            self._sa = message.sa
            self._ts = message.timestamp
            self.decode_payload(message.payload)
        elif protobuf is not None:
            self._sa = protobuf.sa
            self._ts = protobuf.timestamp
            self.from_protobuf(protobuf)

    def decode_payload(self, payload):
        self.decode_payload_segment(payload, 0)

    def decode_payload_segment(self, payload, from_byte):
        raise NotImplementedError("To be implemented in subclasses")

    def from_protobuf(self, protobuf):
        raise NotImplementedError("To be implemented in subclasses")

    def resolve_global_enum(self, enum_set: str, enum_value: int):
        return MessageServerGlobals.enums.get_enum(enum_set).get_name(enum_value)


