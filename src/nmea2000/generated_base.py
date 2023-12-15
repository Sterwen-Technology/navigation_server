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
from generated.nmea2000_pb2 import nmea2000_decoded_pb

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000Payload:

    def decode_payload(self, payload):
        self.decode_payload_segment(payload, 0)

    def unpack_payload(self, protobuf: nmea2000_decoded_pb, payload):
        protobuf.payload.Unpack(payload)
        self.from_protobuf(payload)

    def decode_payload_segment(self, payload, from_byte):
        raise NotImplementedError("To be implemented in subclasses")

    def from_protobuf(self, protobuf):
        raise NotImplementedError("To be implemented in subclasses")

    @staticmethod
    def resolve_global_enum(enum_set: str, enum_value: int):
        return MessageServerGlobals.enums.get_enum(enum_set).get_name(enum_value)


def check_valid(value: int, mask: int, default: int) -> int:
    if value == mask:
        return default
    else:
        return value


class NMEA2000DecodedMsg:

    # __slots__ = ('_sa', '_timestamp', '_priority')

    def __init__(self, message: NMEA2000Msg = None, protobuf: nmea2000_decoded_pb = None):

        if message is not None:
            # initialization from a NMEA2000 CAN message
            self._sa = message.sa
            self._timestamp = message.timestamp
            self._priority = message.prio
        elif protobuf is not None:
            self._sa = protobuf.sa
            self._timestamp = protobuf.timestamp
            self._priority = protobuf.priority

    def protobuf_message(self) -> nmea2000_decoded_pb:
        message = nmea2000_decoded_pb()
        message.pgn = self.pgn  # implemented in specific subclasses
        message.sa = self._sa
        message.timestamp = self._timestamp
        message.priority = self._priority
        _logger.debug("Protobuf encoding for PGN%d" % self.pgn)
        pl_pb = self.as_protobuf()  # as_protobuf implemented in subclasses
        message.payload.Pack(pl_pb)
        return message




