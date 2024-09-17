# -------------------------------------------------------------------------------
# Name:        pgn_python_gen
# Purpose:     Python code generator for pgn supporting classes
#
# Author:      Laurent Carré
#
# Created:     23/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------


import logging
import datetime


from code_generation.nmea2000_meta import (BitFieldAttributeDef, RepeatAttributeDef, ScalarAttributeDef, NMEA2000Meta,
                                           FieldSetMeta, DecodeSegment, ReservedAttribute, ReservedBitFieldAttribute)
from router_common import Typedef
from router_common import N2KDecodeException

_logger = logging.getLogger("ShipDataServer." + __name__)


class PythonPGNGenerator:

    level_indent = ['', '    ', '        ', '            ', '                ']
    base_class = 'NMEA2000Payload'
    message_base_class = 'NMEA2000DecodedMsg'

    def __init__(self, output_file: str, read_only: bool):

        self._read_only = read_only
        try:
            self._of = open(output_file, 'w')
        except IOError as err:
            _logger.error("Python code generator - error opening output file %s:%s" % (output_file, err))
            raise
        print(f"Generating Python code in {output_file} read only={read_only}")
        self._level = 0
        self.write('#   Python code generated by NMEA message router application (c) Sterwen Technology 2023\n')
        self.write('#   generated on %s\n' % datetime.datetime.now().strftime("%Y-%m-%d:%H:%M"))
        self.write('#   do not modify code\n\n\n')

        # generate imports
        self.write("import struct\n")
        self.write("\nfrom router_common import N2KInvalidMessageException\n")
        self.write(f"from nmea2000.generated_base import *\n")
        self.write("from generated.nmea2000_pb2 import nmea2000_decoded_pb\n")
        # self.write("from nmea2000.nmea2000_msg import NMEA2000Msg\n")
        # self._of.write("from router_common.global_variables import MessageServerGlobals\n")
        self.write('\n')

    def close(self):
        self._of.close()

    def write_indent(self):
        self._of.write(self.level_indent[self._level])

    def write(self, output_str: str):
        self.write_indent()
        self._of.write(output_str)

    def nl(self):
        self._of.write('\n')

    def inc_indent(self):
        self._level += 1

    def dec_indent(self):
        self._level -= 1

    def set_level(self, level):
        self._level = level

    def gen_classes(self, class_def_list: list, protobuf_conv: bool, base_name: str):
        # add protobuf import
        if protobuf_conv:
            self._of.write(f"from generated.{base_name}_pb2 import *\n\n")
        # generate all classes
        for cls in class_def_list:
            try:
                self.gen_class(cls, protobuf_conv)
            except N2KDecodeException:
                continue

        # now write the class dictionary
        self.set_level(0)
        self.write("\n#####################################################################\n")
        self.write("#         Generated class dictionary\n")
        self.write("#####################################################################\n")
        self.write("nmea2k_generated_classes = {\n")
        self.set_level(2)

        def write_cls_entry(cls_def: NMEA2000Meta):
            self.write(f"{cls_def.pgn}: {cls_def.class_name}")

        for cls in class_def_list[:len(class_def_list)-1]:
            write_cls_entry(cls)
            self._of.write(",\n")
        write_cls_entry(class_def_list[len(class_def_list)-1])
        self._of.write("\n")
        self.write("}\n")
        self.set_level(0)
        self.write("# end of generated file\n")

    def gen_class(self, pgn_def: NMEA2000Meta, protobuf_conv: bool):

        self.set_level(0)
        self.write('\n')
        self.write(f"class {pgn_def.class_name}({self.message_base_class}):\n\n")
        if pgn_def.force_write:
            read_only = False
        else:
            read_only = pgn_def.read_only or self._read_only  # to be improved by allowing specific classes
        print("Generating class for PGN", pgn_def.pgn, pgn_def.name, "Read_only=", read_only)
        if pgn_def.repeat_field_set is not None:
            # generate inner class
            self.inc_indent()
            self.gen_repeat_class(pgn_def.repeat_field_set, protobuf_conv, pgn_def.class_name, read_only)
            self.dec_indent()
            self.nl()

        # print("Decode str:", pgn_def.decode_str)
        # now start generating
        # class variables
        self.inc_indent()
        self.write("_pgn = %d\n" % pgn_def.pgn)
        self.write("_name = '%s'\n" % pgn_def.name)
        self.write(f"_proprietary = {pgn_def.is_proprietary}\n")
        if pgn_def.is_proprietary:
            self.write(f"_manufacturer_id = {pgn_def.manufacturer}\n")
        if protobuf_conv:
            # generate accessor for protobuf class
            self.nl()
            self.write("@staticmethod\n")
            self.write("def protobuf_class():\n")
            self.inc_indent()
            self.write(f'return {pgn_def.class_name}Pb\n')
            self.dec_indent()
            self.nl()

        self.gen_class_variables(pgn_def, pgn_def.attributes, pgn_def.last_attr)
        # self.nl()
        self.gen_enums_definition(pgn_def.enums)

        #  __init__ method
        # self.inc_indent()
        self.write("def __init__(self, message=None, protobuf=None):\n")
        self.inc_indent()

        if pgn_def.repeat_field_set is not None:
            self.write(f'self._{pgn_def.repeat_field_set.count_method} = 0\n')
            self.write(f'self.{pgn_def.repeat_field_set.variable} = []\n')
        self.write("super().__init__(message, protobuf)\n")
        self.nl()
        # properties methods
        self.dec_indent()
        # access to class parameters
        self.gen_getter('pgn', 'int')
        self.gen_getter('name', 'str')
        self.gen_getter('proprietary', 'bool')
        if pgn_def.is_proprietary:
            self.gen_getter('manufacturer_id', 'int')

        self.gen_accessors_methods(pgn_def.attributes, pgn_def.enums, read_only)

        if not read_only and pgn_def.repeat_field_set is not None and pgn_def.has_flag('AddItem'):
            # lets generate an item adder
            self.gen_item_adder(pgn_def.repeat_field_set)

        if pgn_def.variable_size:
            self.gen_decode_encode_variable(pgn_def, read_only)
        else:
            self.gen_decode_encode(pgn_def, read_only)

        if protobuf_conv:
            self.gen_from_protobuf(pgn_def)

        self.gen_str_conversion(pgn_def, 'PGN{self._pgn}({self._name})')

    def gen_str_conversion(self, pgn_def, header: str):

        # string conversion method

        self.write("def __str__(self):\n")
        self.inc_indent()
        self.write(f"return f'{header} [")
        for attr in pgn_def.attributes[:pgn_def.last_attr]:
            self._of.write("%s={self.%s}, " % (attr.method, attr.variable))
        self._of.write("%s={self.%s}]'\n\n" % (pgn_def.attributes[pgn_def.last_attr].method,
                                               pgn_def.attributes[pgn_def.last_attr].variable))
        self.dec_indent()

    def gen_class_variables(self, pgn_def: FieldSetMeta, attributes, last_attr):
        for segment in pgn_def.segments:
            if segment.segment_type == DecodeSegment.VALUE_SET:
                self.write(f"{segment.variable} = struct.Struct('{segment.decode_string}')\n")
                self.write(f"{segment.variable}_size = {segment.variable}.size\n")
        self.write("__slots__ = (")
        for attr in attributes[:last_attr]:
            self._of.write("'%s', " % attr.variable)
        self._of.write("'%s')\n\n" % attributes[last_attr].variable)
        if not pgn_def.variable_size:
            self.write(f"_static_size = {pgn_def.static_size}\n")
            self.nl()
            self.write("@classmethod\n")
            self.write("def size(cls):\n")
            self.inc_indent()
            self.write("return cls._static_size\n")
            self.dec_indent()
        self.nl()
        self.write("@staticmethod\n")
        self.write("def variable_size() -> bool:\n")
        self.inc_indent()
        self.write(f"return {pgn_def.variable_size}\n")
        self.dec_indent()
        self.nl()

    def gen_enums_definition(self, enums):
        # enums or enum reference
        for enum in enums:
            self.write(f"_{enum.method}_enum = ")
            if enum.global_ref is not None:
                self._of.write(f"'{enum.global_ref}'\n")
            else:
                self._of.write("{\n")
                nb_enums = len(enum.enum_dict)
                count = 0
                self.inc_indent()
                for key, text in enum.enum_dict.items():
                    self.write(f"{key}: '{text}'")
                    if count < nb_enums - 1:
                        self._of.write(",\n")
                    else:
                        self._of.write("\n")
                    count += 1
                self.write("}\n")
                self.dec_indent()
        # enums end

    def gen_accessors_methods(self, attributes, enums, read_only: bool):
        for attr in attributes:
            self.gen_getter(attr.method, attr.field_type)

        if not read_only:
            for attr in attributes:
                if isinstance(attr, RepeatAttributeDef):
                    continue  # no setter for list
                self.write("@%s.setter\n" % attr.method)
                self.write("def %s(self, value: %s):\n" % (attr.method, attr.field_type))
                self.inc_indent()
                self.write("self.%s = value\n\n" % attr.variable)
                self.dec_indent()
        #
        # enums property
        for enum in enums:
            self.write("@property\n")
            self.write(f"def {enum.method}_text(self) -> str:\n")
            self.inc_indent()
            if enum.global_ref is not None:
                self.write(f"return resolve_global_enum(self._{enum.method}_enum, self._{enum.method})\n\n")
            else:
                self.write(f"return self._{enum.method}_enum.get(self._{enum.method}, '{enum.method} key error')\n\n")
            self.dec_indent()

    def gen_decode_encode(self, pgn_def, read_only: bool):
        #
        # decode method =================================================
        #
        self.write(f"def decode_payload(self, payload, start_byte=0):\n")
        self.inc_indent()
        for segment in pgn_def.segments:
            # print("Start segment", segment.segment_type, segment.start_byte, segment.length)
            if segment.segment_type == DecodeSegment.VALUE_SET:
                self.gen_decode_value_set_segment(segment)
                self.write(f"start_byte += {segment.length}\n")
            elif segment.segment_type == DecodeSegment.FIX_LENGTH:
                self.gen_decode_fix_length_segment(segment)
                self.write(f"start_byte += {segment.length}\n")
            else:
                _logger.error("PGN %d Variable length segment is not supported" % pgn_def.pgn)
                raise N2KDecodeException

        if not isinstance(pgn_def, RepeatAttributeDef):
            if pgn_def.repeat_field_set is not None:
                self.gen_repeated_decode(pgn_def.repeat_field_set)
        self.write("return self\n")
        self.dec_indent()
        self.nl()
        if read_only:
            print(f"PGN {pgn_def.pgn} no encode generated")
            self.write("#  Read Only no encode_payload\n")
            return
        #
        # encode method
        #
        if isinstance(pgn_def, RepeatAttributeDef):
            # here we need to generate a complementary encoding only
            self.write("def encode_payload(self, buffer, start_byte):\n")
            self.inc_indent()
        elif not pgn_def.read_only:
            self.write("def encode_payload(self) -> bytearray:\n")
            self.inc_indent()
            # compute the buffer size
            # compute the size of the output buffer
            # fixed determined size
            self.write(f"buf_size = self.__class__.size()\n")
            self.write(f"buffer = bytearray(buf_size)\n")
            self.write("start_byte = 0\n")
        else:
            return

        for segment in pgn_def.segments:
            if segment.segment_type == DecodeSegment.VALUE_SET:
                self.gen_encode_value_set_segment(segment)
            elif segment.segment_type == DecodeSegment.FIX_LENGTH:
                self.gen_encode_fix_length(segment)

        if isinstance(pgn_def, RepeatAttributeDef):
            # need to return the length of encoded portion
            self.write(f"return self._static_size + start_byte\n")
        else:
            if pgn_def.repeat_field_set is not None:
                self.gen_repeated_encode(pgn_def.repeat_field_set)
            self.write("return buffer\n")
        self.dec_indent()
        self.nl()

    def gen_decode_encode_variable(self, pgn_def, read_only: bool):
        '''
        Generate Python code for classes with variable length segments
        '''
        #
        # decode method =================================================
        #
        self.write(f"def decode_payload(self, payload, start_byte=0):\n")
        self.inc_indent()
        # self.write("decode_index = start_byte\n")
        for segment in pgn_def.segments:
            # print("Start segment", segment.segment_type, segment.start_byte, segment.length)
            if segment.segment_type == DecodeSegment.VALUE_SET:
                self.gen_decode_value_set_segment(segment)
                self.write(f"start_byte += {segment.length}\n")
            elif segment.segment_type == DecodeSegment.FIX_LENGTH:
                self.gen_decode_fix_length_segment(segment)
                self.write(f"start_byte += {segment.length}\n")
            elif segment.segment_type == DecodeSegment.VARIABLE_LENGTH:
                self.gen_decode_variable_length(segment)
            else:
                _logger.error("PGN %d Unknown segment type" % pgn_def.pgn)
                raise N2KDecodeException

        if not isinstance(pgn_def, RepeatAttributeDef):
            if pgn_def.repeat_field_set is not None:
                self.gen_repeated_decode_variable(pgn_def.repeat_field_set)
        self.write("return self, start_byte\n")
        self.dec_indent()
        self.nl()

        if read_only:

            return
        #
        # encode method
        #
        if isinstance(pgn_def, RepeatAttributeDef):
            # here we need to generate a complementary encoding only
            self.write("def encode_payload(self, buffer, start_byte):\n")
            self.inc_indent()
        elif not pgn_def.read_only:
            self.write("def encode_payload(self) -> bytearray:\n")
            self.inc_indent()
            # compute the buffer size
            # compute the size of the output buffer
            # fixed determined size
            self.write(f"buf_size = self.DEFAULT_BUFFER_SIZE\n")
            self.write(f"buffer = bytearray(buf_size)\n")
            self.write("start_byte = 0\n")
        else:
            return

        for segment in pgn_def.segments:
            if segment.segment_type == DecodeSegment.VALUE_SET:
                self.gen_encode_value_set_segment(segment, variable_length=True)
                self.write(f"start_byte += {segment.length}\n")
            elif segment.segment_type == DecodeSegment.FIX_LENGTH:
                self.gen_encode_fix_length(segment, variable_length=True)
                self.write(f"start_byte += {segment.length}\n")
            elif segment.segment_type == DecodeSegment.VARIABLE_LENGTH:
                self.gen_encode_var_length(segment)

        if not isinstance(pgn_def, RepeatAttributeDef):
            if pgn_def.repeat_field_set is not None:
                self.gen_repeated_encode_variable(pgn_def.repeat_field_set)
            self.write("return buffer[:start_byte]\n")
        else:
            self.write("return start_byte\n")
        self.dec_indent()
        self.nl()

    validation_hooks = {
        'valid_key': 'gen_check_valid'
    }

    def gen_decode_value_set_segment(self, segment: DecodeSegment, variable_length=False):

        self.write(f"val = self.{segment.variable}.unpack_from(payload, start_byte)\n")
        for attr in segment.attributes:
            if issubclass(attr.__class__, ReservedAttribute):
                continue
            # print("Decode for", attr.method, attr.__class__.__name__)
            if isinstance(attr, ScalarAttributeDef):
                if attr.nb_slots == 2:
                    # ok we need to combine 2 slots
                    self.write(f"word = val[{attr.field_index}] + (val[{attr.field_index + 1}] << 16)\n")
                    source_var = "word"
                else:
                    source_var = f"val[{attr.field_index}]"
                if attr.need_check:
                    self.write(f"self.{attr.variable} = check_valid({source_var}, {attr.invalid_value}, {attr.default})")
                else:
                    self.write(f"self.{attr.variable} = ")
                    if attr.scale is not None:
                        self._of.write(f"check_convert_float({source_var}, 0x{attr.invalid_value:x}, {str(attr.scale)}")
                        if attr.offset is not None:
                            self._of.write(f", {str(attr.offset)})")
                        else:
                            self._of.write(")")
                    elif attr.field_type == "float":
                        self._of.write(f"float({source_var})")
                        if attr.offset is not None:
                            self._of.write(f" + {str(attr.offset)}")
                    else:
                        self._of.write(f"{source_var}")

            elif isinstance(attr, BitFieldAttributeDef):
                # print(attr.method, attr.nb_slots, attr.bit_offset)
                if attr.nb_slots == 2:
                    if attr.sub_field_index == 0:
                        self.write(f"word = val[{attr.field_index}] + (val[{attr.field_index + 1}] << 16)\n")
                    self.write(f"self.{attr.variable} = ")
                    if attr.bit_offset == 0:
                        self._of.write("word ")
                    else:
                        self._of.write(f"(word >> {attr.bit_offset}) ")

                else:
                    self.write(f"self.{attr.variable} = ")
                    if attr.bit_offset == 0:
                        self._of.write(f"val[{attr.field_index}] ")
                    else:
                        self._of.write(f"(val[{attr.field_index}] >> {attr.bit_offset}) ")
                self._of.write(f"& 0x{attr.mask:X}")
            self.nl()
            # here we can implement the check hook
            if attr.field.validation_hook is not None:
                try:
                    validation_m = getattr(self, self.validation_hooks.get(attr.field.validation_hook))
                except AttributeError:
                    continue
                validation_m(attr)



    def gen_decode_fix_length_segment(self, segment: DecodeSegment, variable_length=False):
        decode_start = "start_byte"
        decode_end = f"start_byte + {segment.length}"
        self.write(f"self.{segment.attributes.variable} = ")
        if segment.attributes.typedef == Typedef.STRING:
            self._of.write("clean_string(")
        else:
            self._of.write("clean_bytes(")
        self._of.write(f"payload[{decode_start}: {decode_end}])\n")

    def gen_decode_variable_length(self, segment:DecodeSegment):
        # only strings for the moment
        self.write("dec_str, dec_str_len = extract_var_str(payload, start_byte)\n")
        self.write(f"self.{segment.attributes.variable} = dec_str\n")
        self.write("start_byte += dec_str_len\n")

    def gen_encode_fix_length(self, segment: DecodeSegment, variable_length=False):
        if variable_length:
            encode_start = "start_byte"
        else:
            encode_start = f"{segment.start_byte} + start_byte"
        if segment.attributes.typedef == Typedef.STRING:
            self.write(f"insert_string(buffer, {encode_start}, {segment.length}, self.{segment.attributes.variable})\n")
        else:
            self.write(f"insert_byte(buffer, {encode_start}, {segment.length}, self.{segment.attributes.variable})\n")

    def gen_encode_var_length(self, segment: DecodeSegment):
        self.write(f"inserted_len = insert_var_str(buffer, start_byte, self.{segment.attributes.variable})\n")
        self.write("start_byte += inserted_len\n")

    def gen_repeated_decode(self, attr):
        self.write("start_byte = self._static_size\n")
        self.write(f"self.{attr.variable} = []\n")
        self.write(f"for i in range(0, self.{attr.count_method}):\n")
        self.inc_indent()
        self.write(f"self.{attr.variable}.append(self.{attr.class_name}().decode_payload(payload, start_byte))\n")
        self.write(f"start_byte += self.{attr.class_name}.size()")
        self.dec_indent()
        self.nl()

    def gen_repeated_decode_variable(self, attr):
        self.write(f"for i in range(0, self.{attr.count_method}):\n")
        self.inc_indent()
        if attr.variable_size:
            self.write(f"dec_obj, start_byte = self.{attr.class_name}().decode_payload(payload, start_byte)\n")
            self.write(f"self.{attr.variable}.append(dec_obj)\n")
        else:
            self.write(f"self.{attr.variable}.append(self.{attr.class_name}().decode_payload(payload, start_byte))\n")
            self.write(f"start_byte += self.{attr.class_name}.size()\n")
        self.dec_indent()
        self.nl()

    def gen_encode_value_set_segment(self, segment: DecodeSegment, variable_length=False):
        '''
        Generate encoding method for a segment with only numeric values
        '''
        val_encode = []
        numvi = 0
        val_var = ''

        # self.write_indent()
        # first need to convert in int if float
        for attr in segment.attributes:
            # print(attr.field.name, attr.__class__.__name__)
            if issubclass(attr.__class__, ReservedAttribute):
                if isinstance(attr, ReservedBitFieldAttribute):
                    if attr.sub_field_index == 0:
                        vi = f"v{numvi}"
                        val_encode.append(vi)
                        numvi += 1
                        if attr.nb_slots == 2:
                            val_var = "word"
                        else:
                            val_var = vi
                        # first sub-field so no OR
                        self.write(f"{val_var} = 0x{attr.default_value:x} << {attr.bit_offset}\n")
                    else:
                        self.write(f"{val_var} |= 0x{attr.default_value:x} << {attr.bit_offset}\n")
                        if attr.nb_slots == 2 and attr.last_sub_field:
                            self.write(f"{val_encode[attr.field_index]} = {val_var} & 0xFFFF\n")
                            vi = f"v{numvi}"
                            numvi += 1
                            val_encode.append(vi)
                            self.write(f"{vi} = ({val_var} & 0xFF) >> 16\n")
                else:
                    vi = f"v{numvi}"
                    numvi += 1
                    val_encode.append(vi)
                    self.write(f"{vi} = 0x{attr.default_value:x}\n")
            elif issubclass(attr.__class__, ScalarAttributeDef):
                if attr.field_type == "float":
                    vi = f"v{numvi}"
                    numvi += 1
                    val_encode.append(vi)
                    vi_allocated = True
                    if attr.nb_slots == 2:
                        # need to create an intermediate variable
                        i_res = 'word'
                    else:
                        i_res = vi
                    self.write(f"{i_res} = convert_to_int(self.{attr.variable}, 0x{attr.invalid_value:x}, {attr.scale}")
                    if attr.offset is None:
                        self._of.write(")\n")
                    else:
                        self._of.write(f", {attr.offset})\n")
                    val_var = i_res
                else:
                    val_encode.append(f"self.{attr.variable}")
                    vi_allocated = False
                if attr.nb_slots == 2:
                    assert (attr.byte_length == 3)  # only that case is implemented
                    if not vi_allocated:
                        vi = f"v{numvi}"
                        numvi += 1
                        val_encode.append(vi)
                    self.write(f"{vi} = {val_var} & 0xffff\n")
                    vi = f"v{numvi}"
                    numvi += 1
                    val_encode.append(vi)
                    self.write(f"{vi} = ({val_var} >> 16) & 0xff\n")

            elif isinstance(attr, BitFieldAttributeDef):
                if attr.sub_field_index == 0:
                    vi = f"v{numvi}"
                    val_encode.append(vi)
                    numvi += 1
                    if attr.nb_slots == 2:
                        val_var = "word"
                    else:
                        val_var = vi
                    # first sub-field so no OR
                    self.write(f"{val_var} = (self.{attr.variable} & 0x{attr.mask:x}) << {attr.bit_offset}\n")
                else:
                    self.write(f"{val_var} |= (self.{attr.variable} & 0x{attr.mask:x}) << {attr.bit_offset}\n")
                    if attr.nb_slots == 2 and attr.last_sub_field:
                        self.write(f"{val_encode[attr.field_index]} = {val_var} & 0xFFFF\n")
                        vi = f"v{numvi}"
                        numvi += 1
                        val_encode.append(vi)
                        self.write(f"{vi} = ({val_var} & 0xFF) >> 16\n")
            else:
                val_encode.append(f"self.{attr.variable}")

        if variable_length:
            encode_start = "start_byte"
        else:
            encode_start = f"{segment.start_byte} + start_byte"

        self.write(f"self.{segment.variable}.pack_into(buffer, {encode_start}, ")
        last_attr = len(val_encode) - 1
        for val in val_encode[:last_attr]:
            self._of.write("%s, " % val)
        self._of.write("%s)\n" % val_encode[last_attr])

    def gen_repeated_encode(self, field_set: RepeatAttributeDef):
        self.write(f"for repeat_field in self.{field_set.variable}:\n")
        self.inc_indent()
        self.write(f"repeat_field.encode_payload(buffer, start_byte)\n")
        self.write(f"start_byte += self.{field_set.class_name}.size()\n")
        self.dec_indent()
        self.nl()

    def gen_repeated_encode_variable(self, field_set: RepeatAttributeDef):
        self.write(f"for repeat_field in self.{field_set.variable}:\n")
        self.inc_indent()
        self.write("start_byte = repeat_field.encode_payload(buffer, start_byte)\n")
        self.dec_indent()
        self.nl()

    def gen_getter(self, method, var_type):
        self.write("@property\n")
        self.write(f"def {method}(self) -> {var_type}:\n")
        self.inc_indent()
        self.write(f"return self._{method}\n\n")
        self.dec_indent()

    def gen_repeat_class(self, repeat_field: RepeatAttributeDef, protobuf_conv, outer_class, read_only: bool):

        # self.inc_indent()
        self.write(f"class {repeat_field.class_name}:\n")
        self.nl()
        self.inc_indent()
        self.gen_class_variables(repeat_field, repeat_field.attributes, repeat_field.last_attr)
        self.nl()
        self.gen_enums_definition(repeat_field.enums)
        self.nl()
        # gen __init__ method
        self.write('def __init__(self, protobuf=None):\n')
        self.inc_indent()
        if protobuf_conv:
            self.write('if protobuf is not None:\n')
            self.inc_indent()
            self.write('self.from_protobuf(protobuf)\n')
            self.dec_indent()
        else:
            self.write("pass\n")
        self.dec_indent()
        self.nl()
        self.gen_accessors_methods(repeat_field.attributes, repeat_field.enums, read_only)
        if repeat_field.variable_size:
            self.gen_decode_encode_variable(repeat_field, read_only)
        else:
            self.gen_decode_encode(repeat_field, read_only)
        if protobuf_conv:
            self.gen_from_protobuf(repeat_field, outer_class)

        self.gen_str_conversion(repeat_field, f"({repeat_field.class_name})")
        self.dec_indent()

    def gen_item_adder(self, field_def: RepeatAttributeDef):
        self.write(f"def add_{field_def.class_name.removesuffix('Class')}(self, item: {field_def.class_name}):\n")
        self.inc_indent()
        self.write(f"if self.{field_def.variable} is None:\n")
        self.inc_indent()
        self.write(f"self.{field_def.variable} = []\n")
        self.write(f"self.{field_def.count_method} = 0\n")
        self.dec_indent()
        self.write(f"self.{field_def.variable}.append(item)\n")
        self.write(f"self.{field_def.count_method} += 1\n")
        self.dec_indent()
        self.nl()

    def gen_from_protobuf(self, pgn_def, base_class=None):
        if base_class is not None:
            class_name = f'{base_class}Pb.{pgn_def.class_name}Pb'
        else:
            class_name = pgn_def.class_name + 'Pb'
        self.write(f'def from_protobuf(self, message: {class_name}):\n')
        self.inc_indent()
        for attr in pgn_def.attributes:
            if isinstance(attr, RepeatAttributeDef):
                #  self.write(f'self.{attr.variable} = []\n')
                self.write(f'for sub_set in message.{attr.method}:\n')
                self.inc_indent()
                self.write(f'self.{attr.variable}.append(self.{attr.class_name}(protobuf=sub_set))\n')
                self.dec_indent()
                self.write(f'self.{attr.count_method} = len(self.{attr.variable})\n')
            else:
                self.write(f'self.{attr.variable} = message.{attr.method}\n')
        self.dec_indent()
        self._of.write('\n')
        # now generate the conversion to protobuf

        def gen_protobuf_attr():
            for attr in pgn_def.attributes:
                self.write_indent()
                if isinstance(attr, RepeatAttributeDef):
                    self._of.write(f'for sub_set in self.{attr.variable}:\n')
                    self.inc_indent()
                    self.write(f'message.{attr.method}.append(sub_set.as_protobuf())\n')
                    self.dec_indent()
                    self.write(f'self.{attr.count_method} = len(self.{attr.variable})\n')
                else:
                    self._of.write(f'message.{attr.method} = self.{attr.variable}\n')

        self.write(f'def as_protobuf(self) -> {class_name}:\n')
        self.inc_indent()
        self.write(f'message = {class_name}()\n')
        gen_protobuf_attr()
        self.write('return message\n')
        self.dec_indent()
        self.nl()
        # now insert the data in a existing message
        self.write(f'def set_protobuf(self, message: {class_name}):\n')
        self.inc_indent()
        gen_protobuf_attr()
        self.dec_indent()
        self.nl()
        if base_class is None:
            self.write("def unpack_protobuf(self, protobuf: nmea2000_decoded_pb):\n")
            self.inc_indent()
            self.write(f'payload = {pgn_def.class_name}Pb()\n')
            self.write('protobuf.payload.Unpack(payload)\n')
            self.write("self.from_protobuf(payload)\n")
            self.dec_indent()
            self.nl()

    def gen_check_valid(self, attr):
        self.write(f'if self.{attr.variable} == {attr.invalid_value}:\n')
        self.inc_indent()
        self.write('raise N2KInvalidMessageException\n')
        self.dec_indent()




