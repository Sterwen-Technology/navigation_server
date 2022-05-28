#-------------------------------------------------------------------------------
# Name:        NMEA2K-PGNDefs
# Purpose:     Manages all NMEA2000 PGN definitions
#
# Author:      Laurent Carré
#
# Created:     05/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import sys
import xml.etree.ElementTree as ET
from collections import namedtuple

import struct


_logger = logging.getLogger("ShipDataServer"+".decode")


class N2KDecodeException(Exception):
    pass


class N2KDecodeEOLException(N2KDecodeException):
    pass


class N2KMissingEnumKeyException(N2KDecodeException):
    pass


class PGNDefinitions:

    pgn_definitions = None

    @staticmethod
    def build_definitions(xml_file):
        PGNDefinitions.pgn_definitions = PGNDefinitions(xml_file)
        return PGNDefinitions.pgn_definitions

    @staticmethod
    def pgn_defs():
        return PGNDefinitions.pgn_definitions

    @staticmethod
    def pgn_definition(pgn):
        return PGNDefinitions.pgn_definitions.pgn_def(pgn)

    def __init__(self, xml_file):

        try:
            self._tree = ET.parse(xml_file)
        except ET.ParseError as e:
            _logger.error("Error parsing XML file %s: %s" % (xml_file, str(e)))
            raise

        self._root = self._tree.getroot()
        # print(self._root.tag)
        defs = self._root.find('PGNDefns')
        if defs is None:
            print('missing root tag')
            return
        self._pgn_defs = {}
        pgndefs = defs.findall('PGNDefn')
        for pgnxml in defs.iterfind('PGNDefn'):
            pgn = PGNDef(pgnxml)
            self._pgn_defs[pgn.id] = pgn

    def print_summary(self):
        print("NMEA2000 PGN definitions => number of PGN:%d" % len(self._pgn_defs))
        for pgn in self._pgn_defs.values():
            print(pgn,pgn.length,"Bytes")
            for f in pgn.fields():
                print("\t", f.descr())

    def pgns(self):
        return self._pgn_defs.values()

    def pgn_def(self, number):
        if type(number) == str:
            number = int(number)
        return self._pgn_defs[number]


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


class PGNDef:

    trace_enum_error = False

    @staticmethod
    def set_trace(enum_error: bool):
        PGNDef.trace_enum_error = enum_error

    def __init__(self, pgnxml):
        self._id_str = pgnxml.attrib['PGN']
        self._xml = pgnxml
        self._id = int(self._id_str)
        self._name = pgnxml.find('Name').text
        self._fields = {}
        self._fast_packet = False
        bl = pgnxml.find('ByteLength')
        if bl is not None:
            self._byte_length = int(bl.text)
            if self._byte_length <= 0:
                self._variable_length = True
            else:
                self._variable_length = False
            if self._byte_length > 8:
                self._fast_packet = True
        else:
            self._byte_length = 0
            self._variable_length = True
            self._fast_packet = True

        fields = pgnxml.find('Fields')
        if fields is None:
            _logger.info("PGN %s has no Fields" % self._id_str)
            return

        for field in fields.iter():
            if field.tag.endswith('Field'):
                try:
                    field_class = globals()[field.tag]
                except KeyError:
                    _logger.error("Field class %s not defined" % field.tag)
                    continue
                fo = field_class(field)
                self._fields[fo.name] = fo
            elif field.tag == "RepeatedFieldSet":
                fo = RepeatedFieldSet(field, self)
                self._fields[fo.name] = fo
                break

    def __str__(self):
        return "%s %s" % (self._id_str, self._name)

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def length(self):
        return self._byte_length

    def fast_packet(self) -> bool:
        return self._fast_packet

    def fields(self):
        return self._fields.values()

    def field(self, name):
        return self._fields[name]

    def decode_pgn_data(self, data: bytes):
        '''
        if len(data) != self._byte_length:
            raise N2KDecodeException("PGN %s decode error expected %d bytes got %d" %
                                     (self._id_str, self._byte_length, len(data)))
        '''

        result = {}
        fields: dict = {}
        _logger.debug("start decoding PGN %d %s payload(%d bytes) %s" % (self._id, self._name, len(data), data.hex()))
        index = 0
        for field in self._fields.values():
            try:
                inner_result = field.decode(data, index, fields)
            except N2KMissingEnumKeyException as e:
                if self.trace_enum_error:
                    _logger.info(str(e))
                continue
            except N2KDecodeEOLException:
                _logger.error("EOL error in PGN %s" % self._id_str)
                break
            except N2KDecodeException as e:
                _logger.error("Decoding error in PGN %s: %s" % (self._id_str, str(e)))
                continue
            if inner_result.increment:
                index += inner_result.actual_length
            if inner_result.name == "Reserved":
                continue
            if inner_result.valid:
                fields[inner_result.name] = inner_result.value

        result['pgn'] = self._id
        result['name'] = self._name
        result['fields'] = fields
        _logger.debug("End decoding PGN %d" % self._id)

        return result


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


class Field:

    bit_mask = [
        0xFF,
        0x7F,
        0x3F,
        0x1F,
        0x0F,
        0x07,
        0x03,
        0x01
    ]

    bit_mask16 = [
        0xFFFF,
        0x7FFF,
        0x3FFF,
        0x1FFF,
        0x0FFF,
        0x07FF,
        0x03FF,
        0x01FF
    ]

    bit_mask_l = [
        0x00,
        0x01,
        0x03,
        0x07,
        0x0F,
        0x1F,
        0x3F,
        0x7F,
        0xFF
    ]

    uint_invalid = [
        0x00,  # this shall never happen
        0xFF,  # 1 byte
        0xFFFF,  # 2 bytes
        0xFFFFFF,  # 3 bytes
        0xFFFFFFFF  # 4 bytes
    ]

    def __init__(self, xml, do_not_process=None):
        self._start_byte = 0
        self._end_byte = 0
        self._bit_offset = 0
        self._byte_length = 0
        self._variable_length = False
        self._name = xml.attrib['Name']
        self._attributes = {}
        # print("Field name:", self._name, "class:", self.__class__.__name__)
        for attrib in xml.iter():
            if attrib.tag == self.__class__.__name__:
                continue
            process_it = True
            if do_not_process is not None:
                for a_to_skip in do_not_process:
                    if a_to_skip == attrib.tag:
                        process_it = False
                        break
            if process_it:
                self._attributes[attrib.tag] = self.extract_attr(attrib)
        self.compute_decode_param()

    def extract_attr(self, xml):
        attr_def = {
            "BitOffset": (True, int),
            "BitLength": (True, int),
            "Description": (True, str),
            "Offset": (True, float),
            "Scale": (True, float),
            "FormatAs": (True, str),
            "Units": (True, str)
        }
        try:
            set_as_attr, attr_type = attr_def[xml.tag]
        except KeyError:
            _logger.error("Missing attribute definition %s" % xml.tag)
            return None

        if attr_type == str:
            t = xml.text
        else:
            t = attr_type(xml.text)
        if set_as_attr:
            self.__setattr__(xml.tag, t)
        return t

    @property
    def name(self):
        return self._name

    def type(self):
        return self.__class__.__name__

    def attributes(self):
        return self._attributes.keys()

    def length(self):
        return self._byte_length

    def descr(self):
        return "%s %s offset %d length %d bit offset %d" % (self._name, self.type(),
                                                            self._start_byte,self._byte_length, self._bit_offset)

    def compute_decode_param(self):
        self.extract_values_param()

    def extract_values_param(self):
        self._start_byte = self.BitOffset // 8
        self._bit_offset = self.BitOffset % 8
        if self.BitLength > 0:
            self._byte_length = self.BitLength // 8
            if self.BitLength % 8 != 0:
                self._byte_length += 1
            self._end_byte = self._start_byte + self._byte_length
        else:
            self._variable_length = True

    def decode(self, payload, index, fields):
        '''
        print("Decoding field %s type %s start %d length %d offset %d bits %d" % (
            self._name, self.type(), self._start_byte, self._byte_length, self._bit_offset, self.BitLength
        ))
        '''
        _logger.debug("Decoding field %s type %s start %d(%d) end %d (%d)" %
                      (self._name, self.type(), self._start_byte, index,  self._end_byte, len(payload)))
        specs = DecodeSpecs(0, 0)
        if self._start_byte == 0:
            specs.start = index
        else:
            specs.start = self._start_byte
        if self._byte_length != 0:
            specs.end = specs.start + self._byte_length

        #try:
        res = self.decode_value(payload, specs)
        if res.valid:
            validity = "valid"
        else:
            validity = "invalid"
        _logger.debug("Result %s=%s %s" % (res.name, str(res.value),validity))
        return res
        #except Exception as e:
            # _logger.error("For field %s(%s)) %s" % (self._name, self.type(), str(e)))
            # raise N2KDecodeException("For field %s(%s)) %s" % (self._name, self.type(), str(e)))

    def extract_uint_byte(self, b_dec):
        res = N2KDecodeResult(self._name)
        res.actual_length = 1
        val2 = struct.unpack('<B', b_dec)
        # remove the leading bits
        val = val2[0]
        # print("Byte decode",self._name,"byte:",b_dec,"Offset",self._bit_offset,"length",self.BitLength,":%X"%val)
        if self._bit_offset != 0:
            val >>= 8-(self._bit_offset + self.BitLength)
        res.value = val & self.bit_mask_l[self.BitLength]
        if self._bit_offset + self.BitLength < 8:
            res.no_increment()
        return res

    def extract_uint(self, payload, specs):
        b_dec = payload[specs.start:specs.end]
        res = N2KDecodeResult(self._name)
        res.actual_length = self._byte_length
        if self._byte_length == 1:
            res = self.extract_uint_byte(b_dec)
        elif self._byte_length == 2:
            value = struct.unpack("<H", b_dec)
            res.value = value[0]
        elif self._byte_length == 3:
            value = struct.unpack('<BH', b_dec)
            tmpv = value[0] + (value[1] << 8)
            _logger.debug("Decoding 3 bytes as Uint %s %X %X %X" % (str(b_dec), value[0], value[1], tmpv))
            res.value = tmpv
        elif self._byte_length == 4:
            value = struct.unpack('<L', b_dec)
            res.value = value[0]
        else:
            raise N2KDecodeException("Incorrect Field length for UInt field %s type %s length %d" % (
                self._name, self.type(), self._byte_length))
        # print("%X %X"%(res.value, self.uint_invalid[self._byte_length]))
        if res.value == self.uint_invalid[self._byte_length]:
            res.invalid()
        return res

    def extract_int(self, payload, specs):
        b_dec = payload[specs.start: specs.end]
        res = N2KDecodeResult(self._name)
        res.actual_length = self._byte_length
        if self._bit_offset != 0 or self.BitLength < 8:
            raise N2KDecodeException("Cannot decode Int with bit offset or not byte")

        if self._byte_length == 1:
            value = struct.unpack('<b', b_dec)
            invalid = 0x7F
        elif self._byte_length == 2:
            value = struct.unpack("<h", b_dec)
            invalid = 0x7FFF
            #  print(specs.start, specs.end, b_dec, value[0])
        elif self._byte_length == 4:
            value = struct.unpack('<l', b_dec)
            invalid = 0x7FFFFFFF
        elif self._byte_length == 8:
            value = struct.unpack('<q', b_dec)
            invalid = 0x7FFFFFFFFFFFFFFF
        else:
            raise N2KDecodeException("Incorrect Field length %s" % self._name)
        res.value = value[0]
        if res.value == invalid:
            res.invalid()
        return res

    def apply_scale_offset(self, value: float):
        try:
            value = value*self.Scale
        except AttributeError:
            pass
        try:
            value += self.Offset
        except AttributeError:
            pass
        return value

    def decode_value(self, payload, specs):
        b_dec = payload[specs.start:specs.end]
        if self._byte_length == 1:
            return self.extract_uint_byte(b_dec)
        elif self._byte_length == 2:
            # convert the 2 bytes into an integer big endian
            res = N2KDecodeResult(self._name)
            res.actual_length = 2
            val = struct.unpack('>H', b_dec)
            val = val[0]
            # mask upper bits
            val = val & self.bit_mask16[self._bit_offset]
            remaining_bits = 16 - (self._bit_offset + self.BitLength)
            if remaining_bits > 0:
                val >>= remaining_bits
            res.value = val
            if val == 0xFF:
                res.invalid()
            return res
        elif self._byte_length == 3 or self._byte_length == 4:
            return self.extract_uint(payload, specs)
        else:
            # _logger.error("Cannot decode bit fields over 3 bytes %s %s" % (self._name, self.type()))
            raise N2KDecodeException("Cannot decode bit fields over 3 bytes %s %s" % (self._name, self.type()))

    def extract_var_str(self, payload, specs):
        lg = payload[specs.start]
        type_s = payload[specs.start+1]
        res = N2KDecodeResult(self._name)
        res.actual_length = lg
        # print(lg, type_s, payload[self._start_byte+2:self._start_byte+lg+1])
        if type_s != 1 and lg > 2:
            res.invalid()
            return
        specs.end = specs.start + lg
        if lg == 2:
            res.value = "None"
            return res
        if specs.end > len(payload):
            raise N2KDecodeEOLException
        res.value = payload[specs.start+2:specs.end].decode()
        return res


class UIntField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_uint(payload, specs)


class InstanceField(Field):

    def __init__(self, xml):
        super().__init__(xml)


class EnumField(Field):

    def __init__(self, xml):
        super().__init__(xml, do_not_process=("EnumValues", "EnumPair"))
        self._value_pair = {}
        enum_values = xml.find('EnumValues')
        if enum_values is None:
            _logger.error("EnumField %s with no values" % self._name)
            return
        pairs = enum_values.findall('EnumPair')
        for value in pairs:
            index = value.attrib['Value']
            if index.isdigit():
                index = int(index)
            self._value_pair[index] = value.attrib['Name']
        # print(self._value_pair)

    def get_name(self, value):
        try:
            return self._value_pair[value]
        except KeyError:
            #_logger.error("Enum %s key %d non existent" % (self._name, value))
            # return None
            raise N2KMissingEnumKeyException("Enum %s key %d non existent" % (self._name, value))

    def decode_value(self, payload, specs):
        res = self.extract_uint(payload, specs)
        if not res.valid:
            return res
        enum_index = res.value
        # print("Enum",b_dec,enum_index)
        res.value = self.get_name(enum_index)
        return res


class EnumIntField (EnumField):

    def decode_value(self, payload, specs):
        res = self.extract_uint(payload, specs)
        if not res.valid:
            return res
        enum_index = res.value
        res.value = self._value_pair.get(enum_index, res.value)
        return res


class IntField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_int(payload, specs)


class DblField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        res = self.extract_int(payload, specs)
        # print("Dbl result %X" % res.value, "Valid", res.valid)
        if res.valid:
            res.value = self.apply_scale_offset(float(res.value))
        return res


class UDblField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        res = self.extract_uint(payload, specs)
        if res.valid:
            res.value = self.apply_scale_offset(float(res.value))
        return res


class ASCIIField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):

        return self.extract_var_str(payload, specs)


class StringField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_var_str(payload, specs)


class RepeatedFieldSet:

    def __init__(self, xml, pgn):
        self._name = xml.attrib['Name']
        self._pgn = pgn
        self._count = xml.attrib["Count"]
        self._subfields = {}
        for field in xml.iter():
            if field.tag.endswith('Field'):
                try:
                    field_class = globals()[field.tag]
                except KeyError:
                    _logger.error("Field class %s not defined in PGN %d" % (field.tag, pgn))
                    continue
                fo = field_class(field)
                self._subfields[fo.name] = fo

    @property
    def name(self):
        return self._name

    def descr(self):
        out = "%s %s" % (self._name, "RepeatedFieldSet")
        for f in self._subfields.values():
            out += '\n\t\t'
            out += f.descr()
        return out

    def decode(self, payload, index, fields):
        res = N2KDecodeResult(self._name)
        try:
            nb_set = fields[self._count]
        except KeyError:
            nb_set = 0
        if nb_set < 1:
            _logger.info("Field set %s empty in PGN %d" % (self._name, self._pgn.id))
            res.invalid()
            res.actual_length = 0
            return res
        payload_l = len(payload)
        _logger.debug("Start decoding Repeating fields at %d number of sets %d" % (index, nb_set))
        specs = DecodeSpecs(index, 0)
        result_fields: list = []
        decoded_set = 0
        while decoded_set < nb_set:
            for f in self._subfields.values():
                if f.length() != 0:
                    specs.end = specs.start+f.length()
                if specs.end > payload_l:
                    raise N2KDecodeEOLException
                _logger.debug("Decoding field %s type %s start %d end %d" %
                              (f.name, f.type(), specs.start, specs.end))
                l_res = f.decode_value(payload, specs)
                if l_res.valid:
                    result_fields.append((l_res.name, l_res.value))
                _logger.debug("Result %s=%s" % (f.name, str(l_res.value)))
                specs.start += l_res.actual_length
                res.actual_length += l_res.actual_length
            decoded_set += 1

        res.value = result_fields
        return res





