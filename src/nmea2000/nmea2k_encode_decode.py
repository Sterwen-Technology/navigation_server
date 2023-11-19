# -------------------------------------------------------------------------------
# Name:        NMEA2K-Encoding and decoding supporting classes
# Purpose:     Set of classes for optimized decoding and encoding of NMEA2000 messages
#
# Author:      Laurent Carré
# Created:     01/10/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import struct

_logger = logging.getLogger("ShipDataServer." + __name__)


class N2KDecodeResult:

    def __init__(self, name):
        self._length = 0
        self._name = name
        self._valid = True
        self._value = None
        self._increment = True

    @property
    def actual_length(self):
        return self._length

    @actual_length.setter
    def actual_length(self, value):
        self._length = value

    @property
    def name(self):
        return self._name

    @property
    def valid(self):
        return self._valid

    @property
    def value(self):
        return self._value

    @property
    def increment(self):
        return self._increment

    @value.setter
    def value(self, val):
        self._value = val

    def invalid(self):
        self._valid = False

    def no_increment(self):
        self._increment = False


class BitFieldDef:

    def __init__(self, field, rel_offset, is_enumfield: bool):
        self._field = field
        self._is_enum = is_enumfield
        self._rel_offset = rel_offset
        self._value_mask = (2 ** field.bit_length) - 1

    def get_value(self, input_word):
        value = (input_word >> self._rel_offset) & self._value_mask
        if self._is_enum:
            try:
                value = self._field.get_name(value)
            except KeyError:
                pass
        return value

    def field_name(self):
        return self._field.name

    def bit_length(self):
        return self._field.bit_length

    def field(self):
        return self._field

    def __str__(self):
        return "Field %s offset %d length %d" % (self._field.name, self._rel_offset, self._field.bit_length)


class BitFieldSplitException(Exception):
    pass


class BitField:

    struct_format = {
        1: ("<B", lambda v: v[0]),
        2: ("<H", lambda v: v[0]),
        3: ("<HB", lambda v: v[0] + (v[1] << 16)),
        4: ("<L", lambda v: v[0]),
        8: ("<Q", lambda v: v[0])
        }

    struct_2b = struct.Struct("<H")

    def __init__(self, field, no):
        self._bit_length = 0
        self._byte_length = 0
        self._struct = None
        self._process = None
        self._current_offset = 0
        self._fields = []
        self._start_byte = field.start_byte
        self._name = "bitfield#%d" % no
        _logger.debug("New bitfield %s first field %s start byte %d" % (self._name, field.name, self._start_byte))
        self.add_field(field)

    @property
    def name(self):
        return self._name

    @property
    def start_byte(self):
        return self._start_byte

    def add_field(self, field):
        if self._bit_length > 0 and self._bit_length % 8 == 0:
            raise BitFieldSplitException
        rel_offset = field.abs_bit_offset - self._start_byte * 8
        if self._current_offset != rel_offset:
            _logger.error("NMEA BitField offset error on field: %s expected: %d given:%d abs offset %d" %
                          (field.name, self._current_offset, rel_offset, field.abs_bit_offset))
            return
        bfdef = BitFieldDef(field, rel_offset, field.is_enum())
        self._fields.append(bfdef)
        self._bit_length += field.bit_length
        self._current_offset += field.bit_length

    def finalize(self):
        self._byte_length = self._bit_length // 8
        if self._bit_length % 8 != 0:
            self._byte_length += 1
            _logger.debug("BitField length is not a multiple of 8: %d byte length:%d" %
                          (self._bit_length, self._byte_length))

        if self._byte_length not in [1, 2, 3, 4, 8]:
            _logger.error("BitField length %d is not supported" % self._byte_length)
            for bf in self._fields:
                _logger.error("Error in bitfield => %s" % bf)
            raise ValueError
        self._struct = struct.Struct(self.struct_format[self._byte_length][0])
        self._process = self.struct_format[self._byte_length][1]

    def decode(self, data, index, result_fields):
        val = self._process(self._struct.unpack(data[index: index+self._byte_length]))
        for bfdef in self._fields:
            res = bfdef.get_value(val)
            _logger.debug("Decoding field %s (%dbits) result=%s" % (bfdef.field_name(), bfdef.bit_length(), str(res)))
            result_fields[bfdef.field_name()] = res

    def search_field(self, name):
        for bf in self._fields:
            if bf.field_name() == name:
                return bf.field()
        raise KeyError

    @staticmethod
    def decode_uint16(data):
        return BitField.struct_2b.unpack(data[:2])[0]


class DecodeSpecs:

    def __init__(self, start, end):
        self._start = start
        self._end = end

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    @start.setter
    def start(self, value):
        self._start = value

    @end.setter
    def end(self, value):
        self._end = value


class ValueCoder:

    def __init__(self, length, struct_format):
        self._length = length
        self._struct_format = struct.Struct(struct_format)

    def decode(self, bytes_in):
        raise NotImplementedError

    def encode(self, value: int, target_buffer, index) -> int:
        raise NotImplementedError


class ValueCoderUnsigned(ValueCoder):

    def __init__(self, length, struct_format, process_lambda=lambda x: x[0]):
        super().__init__(length, struct_format)
        self._invalid_value = 2**(length * 8) - 1
        self._process = process_lambda

    def decode(self, bytes_in) -> int:
        vd = self._struct_format.unpack(bytes_in)
        val = self._process(vd)
        # print("decode value =", val, "%08X" % val)
        if val == self._invalid_value:
            raise ValueError
        return val

    def encode(self, value: int, target_buffer, index) -> int:
        value = value & self._invalid_value
        if self._length == 3:
            self._struct_format.pack_into(target_buffer, index, value & 0xFFFF, (value >> 16) & 0xFF)
        else:
            self._struct_format.pack_into(target_buffer, index, value)
        return self._struct_format.size


class ValueCoderSigned(ValueCoder):

    def __init__(self, length, struct_format):
        super().__init__(length, struct_format)
        self._max_value = 2**((length*8) - 1) - 1
        self._min_value = -self._max_value

    def decode(self, bytes_in):
        vd = self._struct_format.unpack(bytes_in)
        return vd[0]

    def encode(self, value: int, target_buffer, index):
        if value > self._max_value or value < self._min_value:
            raise ValueError
        self._struct_format.pack_into(target_buffer, index, value)
        return self._struct_format.size


class DecodeDefinitions:

    uint_invalid = [
        0x00,  # this shall never happen
        0xFF,  # 1 byte
        0xFFFF,  # 2 bytes
        0xFFFFFF,  # 3 bytes
        0xFFFFFFFF  # 4 bytes
    ]

    int_table = {
        1: ValueCoderSigned(1, '<b'),
        2: ValueCoderSigned(2, '<h'),
        4: ValueCoderSigned(4, '<l'),
        8: ValueCoderSigned(8, '<q')
    }

    uint_table = {
        1: ValueCoderUnsigned(1, '<B'),
        2: ValueCoderUnsigned(2, '<H'),
        3: ValueCoderUnsigned(3, '<HB', process_lambda=lambda v: v[0] + (v[1] << 16)),
        4: ValueCoderUnsigned(4, '<L'),
        8: ValueCoderUnsigned(8, '<Q')
    }


if __name__ == "__main__":

    t1 = bytearray.fromhex("01020304")
    r1 = DecodeDefinitions.int_table[4].decode(t1)
    print(t1, "%08X" % r1)
    t2 = bytearray.fromhex("010203")
    r2 = DecodeDefinitions.uint_table[3].decode(t2)
    print(t2, "%08X" % r2)
    buffer = bytearray(16)
    l = DecodeDefinitions.uint_table[3].encode(r2, buffer, 0)
    print(l, buffer)
    index = l
    l = DecodeDefinitions.int_table[4].encode(r1, buffer, l)
    index += l
    print(l, buffer)
    r3 = -1
    l = DecodeDefinitions.int_table[4].encode(r3, buffer, index)
    print(index, r3, buffer)
    val = DecodeDefinitions.int_table[4].decode(buffer[index: index +l])
    print(val)
    index += l

    r3 = -(2**31 -1)
    l = DecodeDefinitions.int_table[4].encode(r3, buffer, index)
    index += l
    print(index, buffer)
    t2 = bytearray.fromhex('01000000')
    r3 = DecodeDefinitions.int_table[4].decode(t2)
    print(r3)
