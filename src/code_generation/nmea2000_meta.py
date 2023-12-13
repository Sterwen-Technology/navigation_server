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
from collections import namedtuple

from nmea2000.nmea2k_pgn_definition import PGNDef
from nmea2000.nmea2k_encode_decode import BitField, BitFieldDef
from nmea2000.nmea2k_fielddefs import (FIXED_LENGTH_BYTES, FIXED_LENGTH_NUMBER, VARIABLE_LENGTH_BYTES, EnumField,
                                       REPEATED_FIELD_SET, Field)
from utilities.global_variables import MessageServerGlobals


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


class HiddenAttribute(AttributeGen):

    def __init__(self, field, decode_index):
        super().__init__(field, decode_index)


class AttributeDef(AttributeGen):

    def __init__(self, field, decode_index):
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

    def __init__(self, bitfield: BitField, field: Field, sub_field: BitFieldDef, decode_index: int):
        super().__init__(field, decode_index)
        self._bitfield = bitfield
        self._sub_field = sub_field

    @property
    def nb_slots(self) -> int:
        return self._bitfield.nb_decode_slots

    @property
    def mask(self) -> int:
        return self._sub_field.mask

    @property
    def bit_offset(self) -> int:
        return self._sub_field.bit_offset


class ScalarAttributeDef(AttributeDef):

    def __init__(self, field, decode_index):
        super().__init__(field, decode_index)

    @property
    def scale(self) -> float:
        return self._field.scale

    @property
    def offset(self) -> float:
        return self._field.offset


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


class FieldSetMeta:

    def __init__(self, field_list):
        self._field_list = field_list
        self._attributes = []
        self._attr_dict = {}
        self._enums = []
        self._decode_str = None
        self._decode_index = 0
        self._repeat_field_set = None
        self.analyze_attributes(field_list)
        self._nb_attributes = len(self._attributes)
        self._last_attr = self._nb_attributes - 1

    def analyze_attributes(self, field_list):
        self._decode_str = "<"

        for field in field_list:
            # print("Field:", field.name)
            if field.decode_method == FIXED_LENGTH_NUMBER:
                self._decode_str += field.decode_string

                current_attr = None
                if isinstance(field, BitField):
                    # need to look in subfields
                    for sub_field in field.sub_fields():
                        if sub_field.field().keyword is not None:
                            a_field = sub_field.field()
                            current_attr = BitFieldAttributeDef(field, a_field, sub_field, self._decode_index)
                            self._attributes.append(current_attr)
                            self._attr_dict[current_attr.method] = current_attr

                elif field.keyword is not None:
                    # need to generate a local variable and access method
                    current_attr = ScalarAttributeDef(field, self._decode_index)
                    self._attributes.append(current_attr)
                    self._attr_dict[current_attr.method] = current_attr

                self._decode_index += field.nb_decode_slots

                # check enum for local generation
                if current_attr is not None:
                    if issubclass(type(current_attr.field), EnumField):
                        enum_def = EnumDef(current_attr.field)
                        self._enums.append(enum_def)

            elif field.decode_method == REPEATED_FIELD_SET:
                # first let's generate the sub_class
                self._repeat_field_set = RepeatAttributeDef(self, field, self._decode_index)
                self._attributes.append(self._repeat_field_set)
                self._attr_dict[self._repeat_field_set.method] = self._repeat_field_set

            # end attributes analysis loop

    @property
    def decode_str(self) -> str:
        return self._decode_str

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
        self._class_name = f"Pgn{self._pgn}Class"

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
    def class_name(self) -> str:
        return self._class_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def repeat_field_set(self):
        return self._repeat_field_set


def nmea2000_gen_meta():
    class_def_list = []
    for cls in MessageServerGlobals.pgn_definitions.generation_iter():
        class_def_list.append(NMEA2000Meta(cls))
    return class_def_list


