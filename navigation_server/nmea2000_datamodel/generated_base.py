# -------------------------------------------------------------------------------
# Name:        generated_base
# Purpose:     Base classes for Python generated classes for NMEA2000
#
# Author:      Laurent Carré
#
# Created:     26/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------


import logging
import time
import math
from datetime import datetime
from math import isnan

from google.protobuf.json_format import MessageToJson

from navigation_server.router_core import NMEA2000Msg
from navigation_server.router_common import MessageServerGlobals, get_global_enum, N2KDecodeException
from navigation_server.generated.nmea2000_pb2 import nmea2000_decoded_pb

_logger = logging.getLogger("ShipDataServer." + __name__)

class JsonOptions:
    resolve_enum = 1


def resolve_global_enum(enum_set: str, enum_value: int):
    return MessageServerGlobals.enums.get_enum(enum_set).get_name(enum_value)


def check_valid(value: int, mask: int, default: int) -> int:
    '''
    Check if the value is valid versus NMEA2000 standard (all bits@1)
    If valid returns the value, if not returns the default value
    '''
    if value == mask:
        return default
    else:
        return value


def clean_string(bytes_to_clean: bytearray) -> str:
    '''
    This function converts fixed length string (as bytes) to Python string
    Cleaning from padding / null chars and superfluous blanks
    '''
    null_start = bytes_to_clean.find(0xFF)
    if null_start > 0:
        bytes_to_clean = bytes_to_clean[:null_start]
    elif null_start == 0:
        return ''
        # try to find if we have a 0x00 as well to end the string
    null_end = bytes_to_clean.find(0x00)
    if null_end == 0:
        return ''
    elif null_end > 0:
        bytes_to_clean = bytes_to_clean[:null_end]
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
    '''
    Extract a variable length string from an NMEA message
    payload: bytearray buffer containing the payload
    start_byte: decoding_index
    returns: string, total number of bytes decoded
    '''
    total_len = payload[start_byte]
    str_len = total_len - 2
    if payload[start_byte + 1] != 1:
        return '', total_len
    if str_len == 0:
        return '', total_len
    return clean_string(payload[start_byte + 2: start_byte + total_len]), total_len


def insert_var_str(payload: bytearray, start_byte, string_to_insert) -> int:
    """

    """
    bytes_to_insert = string_to_insert.encode()
    str_len = len(bytes_to_insert)
    payload[start_byte] = str_len + 2
    payload[start_byte + 1] = 1
    if str_len > 0:
        payload[start_byte + 2: start_byte + str_len + 2] = bytes_to_insert
    return str_len + 2


def insert_string(buffer, start, length, string_to_insert):
    '''
    Insert exactly length bytes in the buffer, padding with FF if needed
    '''
    delta_l = length - len(string_to_insert)
    if delta_l < 0:
        bytes_to_insert = string_to_insert[:length].encode()
    else:
        bytes_to_insert = string_to_insert.encode()
    last_to_insert = start + len(bytes_to_insert)
    buffer[start: last_to_insert] = bytes_to_insert
    if delta_l > 0:
        # then we need to pad extra bytes 0xFF
        for idx in range(last_to_insert, start + length):
            buffer[idx] = 0xFF


def check_convert_float(val: int, invalid_mask: int, scale: float, offset: float = 0.0) -> float:
    '''
    Convert a value from the NMEA2000 payload to a float in the standard unit (ISO ones)
    '''
    if val == -1 or val == invalid_mask:
        return float('nan')
    else:
        return (val * scale) + offset


def convert_to_int(value: float, invalid_mask: int, scale: float, offset: float = 0.0) -> int:
    if math.isnan(value):
        return invalid_mask
    return int((value - offset) / scale)


N2K_DECODED = 201

class FormattingOptions:
    ResolveEnum = 1
    RemoveInvalid = 2
    AlternativeUnits = 4



class NMEA2000DecodedMsg:
    """
    Superclass for all generated NMEA2000 messages classes. This is a pure virtual superclass.
    Instances must be created from an actual (generated) child class.
    """

    __slots__ = ('_sa', '_da', '_timestamp', '_priority')
    canboat_header = '{{"timestamp:":"{0}","prio":{1},"navigation_server":{2},"dst":{3},"pgn":{4},"description":"{5}", "fields":{{'
    active_header = canboat_header

    DEFAULT_BUFFER_SIZE = (31*7)+6   # max Fast packet

    def __init__(self, message: NMEA2000Msg = None, protobuf: nmea2000_decoded_pb = None):
        """

        """

        if message is not None:
            # initialization from a NMEA2000 CAN message
            self._sa = message.sa
            self._da = message.da
            self._timestamp = message.timestamp
            self._priority = message.prio
            self.decode_payload(message.payload)  # from the subclass
        elif protobuf is not None:
            self._sa = protobuf.sa
            self._da = protobuf.da
            self._timestamp = protobuf.timestamp
            self._priority = protobuf.priority
            self.unpack_protobuf(protobuf)  # from the subclass
        else:
            self._timestamp = time.time()
            self._sa = 0
            self._da = 255
            self._priority = 7

    def protobuf_message(self) -> nmea2000_decoded_pb:
        '''
        Returns an instance of the generic class supporting protobuf encoded message ready to be
        '''
        message = nmea2000_decoded_pb()
        message.pgn = self.pgn  # implemented in specific subclasses
        message.sa = self._sa
        message.da = self._da
        message.timestamp = self._timestamp
        message.priority = self._priority
        _logger.debug("Protobuf encoding for PGN%d" % self.pgn)
        pl_pb = self.as_protobuf()  # as_protobuf implemented in subclasses
        message.payload.Pack(pl_pb)
        return message

    def as_protobuf_json(self) -> str:
        message_pb = self.protobuf_message()
        return MessageToJson(message_pb, preserving_proto_field_name=True)

    def message(self) -> NMEA2000Msg:
        msg = NMEA2000Msg(self.pgn, prio=self._priority, sa=self._sa, da=self._da,
                          payload=self.encode_payload(), timestamp=self._timestamp)
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

    @property
    def type(self):
        return N2K_DECODED

    def push_json(self, stream, option: int):
        '''
        Push a Json representation of the message on the stream
        '''
        stream.write(self.active_header.format(datetime.fromtimestamp(self._timestamp).isoformat(), self._priority,
                                      self._sa, self._da, self.pgn, self.name))
        formatters = self.formatters(option & FormattingOptions.RemoveInvalid != 0)
        nb_items = len(formatters)
        assert nb_items > 0
        for fmt in formatters[:nb_items - 1]:
            fmt.output_valid(self, option, stream)
            # write a coma
            stream.write(',')
        # last item
        formatters[nb_items - 1].output_valid(self, option, stream)
        stream.write('}}')


    def decode_payload(self, payload):
        raise NotImplementedError

    def encode_payload(self):
        raise NotImplementedError

    def as_protobuf(self):
        raise NotImplementedError

    def unpack_protobuf(self, protobuf):
        raise NotImplementedError

    def json_format(self):
        raise NotImplementedError

    def formatters(self, check_validity: bool):
        if check_validity:
            fmt_list = []
            for fmt in self.json_format():
                if fmt.check_valid(self):
                    fmt_list.append(fmt)
            return fmt_list
        else:
            return self.json_format()


class GenericFormatter:

    def __init__(self, attribute: str, field_name: str, invalid_mask = 0):
        self._attr = attribute
        self._field_name = field_name
        self._valid_mask = invalid_mask

    def output(self, msg, option, stream) -> bool:
        '''
        Format the field and push it to the stream
        Return True if the field is valid and pushed
        msg: NMEA2000 message including the field
        option: Combination of FormattingOptions
        stream: output stream
        '''
        if self._check_valid(msg, option):
            stream.write('"')
            stream.write(self._field_name)
            stream.write('":')
            self.format(msg, option, stream)
            return True
        return False

    def format(self, msg, option, stream):
        stream.write(str(msg.__getattribute__(self._attr)))

    def _check_valid(self, msg, option) -> bool:
        if self._valid_mask != 0 and option & FormattingOptions.RemoveInvalid:
            return msg.__getattribute__(self._attr) != self._valid_mask
        else:
            return True

    def output_valid(self, msg, option, stream):
        stream.write('"')
        stream.write(self._field_name)
        stream.write('":')
        self.format(msg, option, stream)

    def check_valid(self, msg):
        return msg.__getattribute__(self._attr) != self._valid_mask


class FloatFormatter(GenericFormatter):

    def __init__(self, attribute, field_name, format_str, alternative=None):
        '''
        Define a floating point formatter for Json or other string based output
        format_str: The floating point format string using 'format' syntax: {:x.yf}. This is based on the Unit definition
        alternative: list or set that contains PGN specific conversion and formatting parameters
        (coefficient or scale, offset, format_str)
        '''
        super().__init__(attribute, field_name)
        if alternative is not None:
            self._coefficient = alternative[0]
            self._offset = alternative[1]
            self._format_str = alternative[2]
        else:
            self._format_str = format_str
            self._coefficient = None

    def format(self, msg, option, stream):
        value = msg.__getattribute__(self._attr)
        if isnan(value):
            stream.write('"nan"')
            return
        if (option & FormattingOptions.AlternativeUnits != 0) and self._coefficient is not None:
            value =  (value * self._coefficient) + self._offset
        stream.write(self._format_str.format(value))

    def _check_valid(self, msg, option) -> bool:
        if option & FormattingOptions.RemoveInvalid:
            if isnan(msg.__getattribute__(self._attr)):
                return False
        return True

    def check_valid(self, msg):
        if isnan(msg.__getattribute__(self._attr)):
            return False
        return True


class EnumFormatter(GenericFormatter):

    def __init__(self, attribute, field_name, invalid_mask: int, local: dict = None, global_enum: str=None):
        super().__init__(attribute, field_name, invalid_mask)
        self._enum_def = local
        self._global_ref = global_enum

    def format(self, msg, option, stream):
        if option & JsonOptions.resolve_enum != 0:
            if self._enum_def is None:
                if self._global_ref is not None:
                    self._enum_def = get_global_enum(self._global_ref)
                else:
                    raise N2KDecodeException(f"No Enum definition for {self._field_name}")
            try:
                value = self._enum_def[msg.__getattribute__(self._attr)]
            except KeyError:
                value = f"Value out of range {msg.__getattribute__(self._attr)}"
            stream.write('"')
            stream.write(value)
            stream.write('"')
        else:
            super().format(msg, option, stream)

class TextFormatter(GenericFormatter):

    def __init__(self, attribute, field_name):
        super().__init__(attribute, field_name)

    def format(self, msg, option, stream):
        stream.write('"')
        stream.write(msg.__getattribute__(self._attr))
        stream.write('"')

    def _check_valid(self, msg, option) -> bool:
        return True

    def check_valid(self, msg) -> bool:
        return True


class RepeatedFormatter(GenericFormatter):

    def __init__(self, attribute, field_name, list_attribute):
        super().__init__(attribute, field_name)
        self._list = list_attribute

    def valid_formatters(self, msg, formatters, check_validity: bool):
        if check_validity:
            fmt_list = []
            for fmt in formatters:
                if fmt.check_valid(msg):
                    fmt_list.append(fmt)
            return fmt_list
        else:
            return formatters

    def output_valid(self, msg, option, stream):
        super().output(msg, option, stream)
        nb_items = msg.__getattribute__(self._attr)
        if nb_items > 0:
            stream.write(',"list":[')
            repeated_attr = msg.__getattribute__(self._list)
            formatters = repeated_attr[0].json_format()
            nb_attr = len(formatters)
            assert nb_attr > 0

            items_written = 0
            for attr in repeated_attr:
                stream.write('{')
                val_formatters = self.valid_formatters(attr, formatters, option & FormattingOptions.RemoveInvalid != 0)
                nb_attr_val = len(val_formatters)
                if nb_attr_val > 0:
                    loop_fmt = val_formatters[:nb_attr_val - 1]
                    for fmt in loop_fmt:
                        fmt.output_valid(attr, option, stream)
                        stream.write(',')
                    val_formatters[nb_attr_val - 1].output_valid(attr, option, stream)
                stream.write('}')
                items_written += 1
                if items_written < nb_items:
                    stream.write(",")
            stream.write(']')






