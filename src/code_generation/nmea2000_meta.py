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
from nmea2000.nmea2k_encode_decode import BitField
from nmea2000.nmea2k_fielddefs import (FIXED_LENGTH_BYTES, FIXED_LENGTH_NUMBER, VARIABLE_LENGTH_BYTES, EnumField,
                                        REPEATED_FIELD_SET)
from utilities.global_variables import MessageServerGlobals


_logger = logging.getLogger("ShipDataServer." + __name__)


class AttributeGen:

    def __init__(self, field):
        self._field = field

class HiddenAttribute(AttributeGen):

    def __init__(self, field):
        super().__init__(field)


class AttributeDef(AttributeGen):

    def __int__(self, field):
        super().__init__(field)




class FieldSetMeta:

    def __init__(self, field_list):
        self._attributes, self._enums, self._decode_str = self.analyze_attributes(field_list)
        self._nb_attributes = len(self._attributes)
        self._last_attr = self._nb_attributes - 1

    def analyze_attributes(self, field_list):
        attributes = []
        enums = []
        decode_str = "<"
        decode_index = 0
        for field in field_list:
            print("Field:", field.name)
            if field.decode_method == FIXED_LENGTH_NUMBER:
                decode_str += field.decode_string

                current_attr = None
                if isinstance(field, BitField):
                    # need to look in subfields
                    for sub_field in field.sub_fields():
                        if sub_field.field().keyword is not None:
                            a_field = sub_field.field()
                            current_attr = BitFieldAttributeDef(a_field.keyword, '_%s' % a_field.keyword, a_field,
                                                                decode_index, 'int', field.nb_decode_slots,
                                                                sub_field.mask, sub_field.bit_offset)
                            attributes.append(current_attr)

                elif field.keyword is not None:
                    # need to generate a local variable and access method
                    current_attr = AttributeDef(field.keyword, '_%s' % field.keyword, field, decode_index,
                                                field.python_type, field.scale, field.offset)
                    attributes.append(current_attr)

                decode_index += field.nb_decode_slots

                # check enum for local generation
                if current_attr is not None:
                    if issubclass(type(current_attr.field), EnumField):
                        enum_def = EnumDef(current_attr.field.global_enum, current_attr.method,
                                           current_attr.field.get_enum_dict())
                        enums.append(enum_def)

            elif field.decode_method == REPEATED_FIELD_SET:
                # first let's generate the sub_class
                class_name = self.gen_repeat_class(field)
                attributes.append(RepeatAttributeDef(field.keyword, f"_{field.keyword}", field.count_method,
                                                     class_name, field.python_type))

            # end attributes analysis loop
        return attributes, enums, decode_str


class NMEA2000Meta(FieldSetMeta):

    def __init__(self, pgn_def: PGNDef):
        self._pgn = pgn_def.id
        self._name = pgn_def.name
        super().__init__(pgn_def.field_list)



