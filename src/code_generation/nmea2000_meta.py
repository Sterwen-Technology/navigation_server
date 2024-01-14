# -------------------------------------------------------------------------------
# Name:        nmea2000_meta.py
# Purpose:     Build the NMEA2000 meta model for further code generation
#
# Author:      Laurent Carré
#
# Created:     08/12/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import struct
from collections import namedtuple

from nmea2000.nmea2k_pgn_definition import PGNDef
from nmea2000.nmea2k_encode_decode import BitField, BitFieldDef
from nmea2000.nmea2k_fielddefs import (FIXED_LENGTH_BYTES, FIXED_LENGTH_NUMBER, VARIABLE_LENGTH_BYTES, EnumField,
                                       REPEATED_FIELD_SET, Field)
from utilities.global_variables import MessageServerGlobals, manufacturer_name, find_pgn


_logger = logging.getLogger("ShipDataServer." + __name__)


class AttributeGen:

    def __init__(self, field: Field, decode_index: int):
        self._field = field
        self._decode_index = decode_index

    @property
    def field(self):
        return self._field

    @property
    def field_index(self) -> int:
        return self._decode_index

    @property
    def byte_length(self) -> int:
        return self._field.length()

    @property
    def invalid_mask(self) -> int:
        return 2**self._field.bit_length-1


class ReservedAttribute(AttributeGen):

    def __init__(self, field, decode_index):
        super().__init__(field, decode_index)
        if field.signed:
            self._default_value = 2 ** (field.bit_length - 1) - 1
        else:
            self._default_value = 2**field.bit_length - 1

    @property
    def default_value(self) -> int:
        return self._default_value


class AttributeDef(AttributeGen):

    def __init__(self, field: Field, decode_index=-1):
        super().__init__(field, decode_index)
        self._variable = f"_{field.keyword}"
        self._need_check = False
        self._default = 0


    @property
    def method(self) -> str:
        return self._field.keyword

    @property
    def variable(self) -> str:
        return self._variable

    @property
    def field_type(self) -> str:
        return self._field.python_type

    @property
    def need_check(self) -> bool:
        return self._need_check

    @property
    def default(self) -> int:
        return self._default

    def set_check_default(self, default: int):
        self._default = default
        self._need_check = True

    @property
    def typedef(self):
        return self._field.typedef


class BitFieldAttributeDef(AttributeDef):

    def __init__(self, bitfield: BitField, field: Field, sub_field: BitFieldDef, sub_field_idx: int, decode_index: int):
        super().__init__(field, decode_index)
        self._bitfield = bitfield
        self._sub_field = sub_field
        self._sub_field_idx = sub_field_idx

    @property
    def nb_slots(self) -> int:
        return self._bitfield.nb_decode_slots

    @property
    def mask(self) -> int:
        return self._sub_field.mask

    @property
    def bit_offset(self) -> int:
        return self._sub_field.bit_offset

    @property
    def sub_field_index(self) -> int:
        return self._sub_field_idx

    @property
    def last_sub_field(self) -> bool:
        return self._sub_field_idx == self._bitfield.nb_sub_fields - 1


class ReservedBitFieldAttribute(ReservedAttribute):

    def __init__(self, bitfield: BitField, field: Field, sub_field: BitFieldDef, sub_field_idx: int, decode_index: int):
        super().__init__(field, decode_index)
        self._bitfield = bitfield
        self._sub_field = sub_field
        self._sub_field_idx = sub_field_idx

    @property
    def nb_slots(self) -> int:
        return self._bitfield.nb_decode_slots

    @property
    def mask(self) -> int:
        return self._sub_field.mask

    @property
    def bit_offset(self) -> int:
        return self._sub_field.bit_offset

    @property
    def sub_field_index(self) -> int:
        return self._sub_field_idx

    @property
    def last_sub_field(self) -> bool:
        return self._sub_field_idx == self._bitfield.nb_sub_fields - 1


class ScalarAttributeDef(AttributeDef):

    def __init__(self, field, decode_index):
        super().__init__(field, decode_index)
        if field.signed:
            self._invalid_value = 2 ** (field.bit_length - 1) - 1
        else:
            self._invalid_value = 2 ** field.bit_length - 1

    @property
    def scale(self) -> float:
        return self._field.scale

    @property
    def offset(self) -> float:
        return self._field.offset

    @property
    def invalid_value(self) -> int:
        return self._invalid_value

    @property
    def nb_slots(self) -> int:
        return self._field.nb_decode_slots


class EnumDef:

    def __init__(self, field: EnumField):
        self._field = field

    @property
    def global_ref(self) -> str:
        return self._field.global_enum

    @property
    def method(self) -> str:
        return self._field.keyword

    @property
    def enum_dict(self) -> dict:
        return self._field.get_enum_dict()


class DecodeSegment:

    (VALUE_SET, FIX_LENGTH, VARIABLE_LENGTH) = range(1, 4)

    def __init__(self, segment_type, start_byte):
        self._segment_type = segment_type
        self._start_byte = start_byte
        if segment_type == self.VALUE_SET:
            self._decode_string = "<"
            self._attributes = []
            self._variable = None
        else:
            self._decode_string = None
            self._attributes = None
        self._length = 0

    def add_decode_field(self, field_str: str):
        if self._segment_type == self.VALUE_SET:
            self._decode_string += field_str
        else:
            raise ValueError

    def add_attribute(self, attribute):
        if self._segment_type == self.VALUE_SET:
            self._attributes.append(attribute)
        else:
            raise ValueError

    def set_attribute(self, attribute):
        if self._segment_type != self.VALUE_SET:
            self._attributes = attribute
        else:
            raise ValueError

    def set_variable(self, variable: str):
        self._variable = variable

    @property
    def variable(self) -> str:
        return self._variable

    def set_length(self, length):
        if self._segment_type == self.FIX_LENGTH:
            self._length = length

    def compute_length(self):
        if self._segment_type == self.VALUE_SET:
            self._length = struct.calcsize(self._decode_string)

    @property
    def segment_type(self):
        return self._segment_type

    @property
    def start_byte(self):
        return self._start_byte

    @property
    def attributes(self):
        return self._attributes

    @property
    def length(self):
        if self._length == 0 and self._segment_type == self.VALUE_SET:
            self.compute_length()
        return self._length

    @property
    def decode_string(self):
        return self._decode_string


class FieldSetMeta:

    def __init__(self, field_list):
        self._field_list = field_list
        self._attributes = []
        self._reserved_attributes = []
        self._attr_dict = {}
        self._enums = []
        self._segments = []
        self._decode_index = 0
        self._repeat_field_set = None
        self._variable_size = False
        self._static_size = 0

        self.analyze_attributes(field_list)
        self._nb_attributes = len(self._attributes)
        self._last_attr = self._nb_attributes - 1

    def analyze_attributes(self, field_list):

        segment = None
        current_byte = 0
        # self._segments.append(segment)

        for field in field_list:
            # print("Field:", field.name)
            if field.decode_method == FIXED_LENGTH_NUMBER:

                if segment is None:
                    segment = DecodeSegment(DecodeSegment.VALUE_SET, current_byte)
                    self._decode_index = 0
                    self._segments.append(segment)
                elif segment.segment_type != DecodeSegment.VALUE_SET:
                    # need to change segment type
                    current_byte += segment.length
                    segment = DecodeSegment(DecodeSegment.VALUE_SET, current_byte)
                    self._decode_index = 0
                    self._segments.append(segment)

                segment.add_decode_field(field.decode_string)
                current_attr = None
                if isinstance(field, BitField):
                    # need to look in subfields
                    sub_field_idx = 0
                    for sub_field in field.sub_fields():
                        a_field = sub_field.field()  # a_field is the one that appears in the PGN definition
                        if sub_field.field().keyword is not None:
                            current_attr = BitFieldAttributeDef(field, a_field, sub_field, sub_field_idx,
                                                                self._decode_index)
                            self._attributes.append(current_attr)
                            self._attr_dict[current_attr.method] = current_attr
                            segment.add_attribute(current_attr)
                        else:
                            attr = ReservedBitFieldAttribute(a_field, a_field, sub_field, sub_field_idx,
                                                             self._decode_index)
                            segment.add_attribute(attr)
                            self._reserved_attributes.append(attr)
                        sub_field_idx += 1

                elif field.keyword is not None:
                    # need to generate a local variable and access method
                    current_attr = ScalarAttributeDef(field, self._decode_index)
                    self._attributes.append(current_attr)
                    self._attr_dict[current_attr.method] = current_attr
                    segment.add_attribute(current_attr)
                else:
                    attr = ReservedAttribute(field, self._decode_index)
                    segment.add_attribute(attr)
                    self._reserved_attributes.append(attr)

                self._decode_index += field.nb_decode_slots
                # check enum for local generation
                if current_attr is not None:
                    if issubclass(type(current_attr.field), EnumField):
                        enum_def = EnumDef(current_attr.field)
                        self._enums.append(enum_def)

            elif field.decode_method == FIXED_LENGTH_BYTES:
                if segment is not None:
                    current_byte += segment.length
                segment = DecodeSegment(DecodeSegment.FIX_LENGTH, current_byte)
                self._segments.append(segment)
                segment.set_length(field.length())
                if field.keyword is not None:
                    current_attr = AttributeDef(field)
                    self._attributes.append(current_attr)
                    self._attr_dict[current_attr.method] = current_attr
                else:
                    current_attr = ReservedAttribute(field, -1)
                    self._reserved_attributes.append(current_attr)
                segment.set_attribute(current_attr)

            elif field.decode_method == VARIABLE_LENGTH_BYTES:
                if segment is not None:
                    current_byte += segment.length
                segment = DecodeSegment(DecodeSegment.VARIABLE_LENGTH, current_byte)
                self._segments.append(segment)
                if field.keyword is not None:
                    current_attr = AttributeDef(field)
                    self._attributes.append(current_attr)
                    self._attr_dict[current_attr.method] = current_attr
                else:
                    current_attr = ReservedAttribute(field, -1)
                    self._reserved_attributes.append(current_attr)
                segment.set_attribute(current_attr)
                self._variable_size = True

            elif field.decode_method == REPEATED_FIELD_SET:
                # first let's generate the sub_class
                self._variable_size = True
                self._repeat_field_set = RepeatAttributeDef(self, field, self._decode_index)
                self._attributes.append(self._repeat_field_set)
                self._attr_dict[self._repeat_field_set.method] = self._repeat_field_set

            # end attributes analysis loop
        decode_var = "_struct_str_"
        nb_var = 0
        for segment in self._segments:
            if segment.segment_type == DecodeSegment.VALUE_SET:
                segment.set_variable(f"{decode_var}{nb_var}")
                nb_var += 1
            self._static_size += segment.length


    @property
    def attributes(self) -> list:
        return self._attributes

    @property
    def enums(self) -> list:
        return self._enums

    @property
    def last_attr(self) -> int:
        return self._last_attr

    def get_attribute(self, key):
        return self._attr_dict[key]

    @property
    def nb_segments(self) -> int:
        return len(self._segments)

    @property
    def segments(self) -> list:
        return self._segments

    @property
    def variable_size(self) -> bool:
        return self._variable_size

    @property
    def static_size(self) -> int:
        return self._static_size


class RepeatAttributeDef(FieldSetMeta, AttributeDef):

    def __init__(self, pgn_def, field, decode_index):
        AttributeDef.__init__(self, field, decode_index)
        super().__init__(field.field_list)
        self._class_name = f"{field.keyword.title()}Class"
        try:
            count_field = pgn_def.get_attribute(field.count_method)
        except KeyError:
            _logger.error(f"{self.method} missing repeat count method {field.count_method}")
            raise
        count_field.set_check_default(0)

    @property
    def class_name(self) -> str:
        return self._class_name

    @property
    def count_method(self) -> str:
        return self._field.count_method


class NMEA2000Meta(FieldSetMeta):

    def __init__(self, pgn_def: PGNDef):
        self._pgn = pgn_def.id
        self._name = pgn_def.name
        self._pgn_def = pgn_def
        print(f"generating meta model for: {self._name} PGN {self._pgn}")
        super().__init__(pgn_def.field_list)
        if pgn_def.is_proprietary:
            self._class_name = f"Pgn{self._pgn}Mfg{self.manufacturer}Class"
        else:
            self._class_name = f"Pgn{self._pgn}Class"
        self._read_only = pgn_def.has_flag('ReadOnly')
        if pgn_def.has_flag('ReadWrite'):
            self._read_only = False
            self._force_write = True
        else:
            self._force_write = False

    @property
    def pgn(self) -> int:
        return self._pgn

    @property
    def manufacturer(self) -> int:
        try:
            return self._pgn_def.manufacturer_id
        except ValueError:
            return 0

    @property
    def manufacturer_name(self) -> str:
        return manufacturer_name(self.manufacturer)

    @property
    def is_proprietary(self) -> bool:
        return self._pgn_def.is_proprietary

    @property
    def class_name(self) -> str:
        return self._class_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def repeat_field_set(self):
        return self._repeat_field_set

    @property
    def read_only(self) -> bool:
        # being proprietary is NOT a reason for not being encoded
        return self._read_only

    @property
    def force_write(self) -> bool:
        return self._force_write

    def has_flag(self, flag: str) -> bool:
        return self._pgn_def.has_flag(flag)


def nmea2000_gen_meta(pgn=None):
    class_def_list = []
    if pgn is None or pgn == 0:
        for cls in MessageServerGlobals.pgn_definitions.generation_iter():
            class_def_list.append(NMEA2000Meta(cls))
    else:
        try:
            cls = find_pgn(pgn)
        except KeyError:
            return None
        class_def_list.append(NMEA2000Meta(cls))
    return class_def_list


