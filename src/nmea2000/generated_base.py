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
from google.protobuf.json_format import MessageToJson

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


def clean_string(bytes_to_clean: bytearray) -> str:
    null_start = bytes_to_clean.find(0xFF)
    if null_start > 0:
        bytes_to_clean = bytes_to_clean[:null_start]
    elif null_start == 0:
        return ''
    if len(bytes_to_clean) == 0:
        return ''
    try:
        str_to_clean = bytes_to_clean.decode()
    except UnicodeError:
        _logger.error("Error decoding string field %s start=%d" % (bytes_to_clean, null_start))
        return ''
    result = str_to_clean.rstrip('@\x20\x00')
    if result.isprintable():
        return result
    else:
        return ''


def extract_var_str(payload: bytearray, start_byte: int):
    str_len = payload[start_byte]
    total_len = str_len + 2
    if payload[start_byte + 1] != 1:
        return '', total_len
    return clean_string(payload[start_byte + 2: start_byte + total_len]), total_len


def insert_var_str(payload: bytearray, start_byte, string_to_insert) -> int:
    bytes_to_insert = string_to_insert.encode()
    str_len = len(bytes_to_insert)
    payload[start_byte] = str_len
    payload[start_byte + 1] = 1
    if str_len > 0:
        payload[start_byte + 2: start_byte + str_len + 2] = bytes_to_insert
    return str_len + 2


def insert_string(buffer, start, length, string_to_insert):
    if len(string_to_insert) > length:
        bytes_to_insert = string_to_insert[:length].encode()
    else:
        bytes_to_insert = string_to_insert.encode()
    last_to_insert = start + len(bytes_to_insert)
    buffer[start: last_to_insert] = bytes_to_insert


def check_convert_float(val: int, invalid_mask: int, scale: float, offset: float = 0.0) -> float:
    if val == -1 or val == invalid_mask:
        return float('nan')
    else:
        return (val * scale) + offset


def convert_to_int(value: float, invalid_mask: int, scale: float, offset: float = 0.0) -> int:
    if value == float('nan'):
        return invalid_mask
    return int((value - offset) / scale)



class NMEA2000DecodedMsg:

    __slots__ = ('_sa', '_da', '_timestamp', '_priority')

    DEFAULT_BUFFER_SIZE = 1024

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

    def as_json(self) -> str:
        message_pb = self.protobuf_message()
        return MessageToJson(message_pb, including_default_value_fields=True, preserving_proto_field_name=True)

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




