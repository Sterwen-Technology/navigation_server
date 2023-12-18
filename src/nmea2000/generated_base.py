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
import time

from nmea2000.nmea2000_msg import NMEA2000Msg
from utilities.global_variables import MessageServerGlobals
from generated.nmea2000_pb2 import nmea2000_decoded_pb

_logger = logging.getLogger("ShipDataServer." + __name__)


def resolve_global_enum(enum_set: str, enum_value: int):
    return MessageServerGlobals.enums.get_enum(enum_set).get_name(enum_value)


def check_valid(value: int, mask: int, default: int) -> int:
    if value == mask:
        return default
    else:
        return value


def clean_string(bytes_to_clean) -> str:
    null_start = bytes_to_clean.find(0xFF)
    if null_start > 0:
        bytes_to_clean = bytes_to_clean[:null_start]
    if len(bytes_to_clean) == 0:
        return ''
    try:
        str_to_clean = bytes_to_clean.decode()
    except UnicodeError:
        _logger.error("Error decoding string field %s" % bytes_to_clean)
        return ''
    return str_to_clean.strip('@\x20\x00')


def insert_string(buffer, start, last, string_to_insert):
    max_len = last - start
    if len(string_to_insert) > max_len:
        bytes_to_insert = string_to_insert[:max_len].encode()
    else:
        bytes_to_insert = string_to_insert.encode()
    last_to_insert = start + len(bytes_to_insert)
    buffer[start: last_to_insert] = bytes_to_insert




class NMEA2000DecodedMsg:

    __slots__ = ('_sa', '_da', '_timestamp', '_priority')

    def __init__(self, message: NMEA2000Msg = None, protobuf: nmea2000_decoded_pb = None):

        if message is not None:
            # initialization from a NMEA2000 CAN message
            self._sa = message.sa
            self._da = message.da
            self._timestamp = message.timestamp
            self._priority = message.prio
            self.decode_payload(message.payload)
        elif protobuf is not None:
            self._sa = protobuf.sa
            self._timestamp = protobuf.timestamp
            self._priority = protobuf.priority
            self.unpack_protobuf(protobuf)

        # we need a way to initialise the NMEA2000 message

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

    def message(self) -> NMEA2000Msg:
        msg = NMEA2000Msg(self.pgn, self._priority, self._sa, self._da, self._timestamp, self.encode_payload())
        return msg

    @property
    def sa(self) -> int:
        return self._sa
    @sa.setter
    def sa(self, sa: int):
        self._sa = sa & 0xff

    @property
    def priority(self) -> int:
        return self._priority

    @priority.setter
    def priority(self, prio: int):
        self._priority = prio & 7

    @property
    def timestamp(self) -> float:
        return self._timestamp

    @timestamp.setter
    def timestamp(self, ts: float):
        self._timestamp = ts

    @property
    def da(self) -> int:
        return self._da

    @da.setter
    def da(self, da: int):
        self._da = da & 0xff

    def set_timestamp(self):
        self._timestamp = time.time()




