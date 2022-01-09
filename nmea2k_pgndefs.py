#-------------------------------------------------------------------------------
# Name:        NMEA2K-PGNDefs
# Purpose:     Manages all NMEA2000 PGN definitions
#
# Author:      Laurent Carré
#
# Created:     05/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technolgy 2021
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import logging
import sys
import xml.etree.ElementTree as ET

import struct


_logger = logging.getLogger("ShipDataServer")


class N2KDecodeException(Exception):
    pass


class N2KDecodeEOLException(N2KDecodeException):
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


class PGNDef:

    def __init__(self, pgnxml):
        self._id_str = pgnxml.attrib['PGN']
        self._xml = pgnxml
        self._id = int(self._id_str)
        self._name = pgnxml.find('Name').text
        self._fields = {}
        bl = pgnxml.find('ByteLength')
        if bl is not None:
            self._byte_length = int(bl.text)
        else:
            self._byte_length = 0
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
        fields: list = []
        _logger.debug("start decoding PGN %d %s payload(%d bytes) %s" % (self._id, self._name, len(data), data.hex()))
        for field in self._fields.values():
            if field.name == 'Reserved':
                continue
            try:
                fields.append(field.decode(data))
            except N2KDecodeEOLException:
                break
        result['pgn'] = self._id
        result['name'] = self._name
        result['fields'] = fields
        _logger.debug("End decoding PGN %d" % self._id)

        return result


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

    def __init__(self, xml, do_not_process=None):
        self._start_byte = 0
        self._end_byte = 0
        self._bit_offset = 0
        self._byte_length = 0
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
            print("Missing attribute definition", xml.tag)
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

    def descr(self):
        return "%s %s offset %d length %d bit offset %d" % (self._name, self.type(),
                                                            self._start_byte,self._byte_length, self._bit_offset)

    def decode_string(self, payload):
        try:
            return payload[self._start_byte: self._end_byte].decode()
        except UnicodeDecodeError:
            _logger.error("Cannot decode bytes as string start %d end %d bytes %s"% (
                self._start_byte, self._end_byte, payload.hex()
            ))

    def compute_decode_param(self):
        self.extract_values_param()

    def extract_values_param(self):
        self._start_byte = self.BitOffset // 8
        self._bit_offset = self.BitOffset % 8
        self._byte_length = self.BitLength // 8
        if self.BitLength % 8 != 0:
            self._byte_length += 1
        self._end_byte = self._start_byte + self._byte_length

    def decode(self, payload):
        '''
        print("Decoding field %s type %s start %d length %d offset %d bits %d" % (
            self._name, self.type(), self._start_byte, self._byte_length, self._bit_offset, self.BitLength
        ))
        '''
        if self._end_byte > len(payload):
            _logger.info("Field %s not present in PGN" % self._name)
            raise N2KDecodeEOLException
        try:
            return self._name, self.decode_value(payload)
        except Exception as e:
            _logger.error("For field %s(%s)) %s" % (self._name, self.type(), str(e)))
            raise

    def extract_uint_byte(self, b_dec):
        val2 = struct.unpack('<B', b_dec)
        # remove the leading bits
        val = val2[0]
        if self._bit_offset != 0:
            val >>= self._bit_offset
        val = val & self.bit_mask_l[self.BitLength]
        return val

    def extract_uint(self, payload):
        b_dec = payload[self._start_byte:self._end_byte]
        if self._byte_length == 1:
            value = self.extract_uint_byte(b_dec)
        elif self._byte_length == 2:
            value = struct.unpack("<H", b_dec)
            value = value[0]
        elif self._byte_length == 3:
            value = struct.unpack('<BH', b_dec)
            tmpv = value[0] + (value[1] << 8)
            _logger.debug("Decoding 3 bytes as Uint %s %X %X %X" % (str(b_dec), value[0], value[1], tmpv))
            value = tmpv
        elif self._byte_length == 4:
            value = struct.unpack('<L', b_dec)
            value = value[0]
        else:
            _logger.error("Incorrect Field length for UInt field %s type %s length %d" % (
                self._name, self.type(), self._byte_length))
            return 0
        return value

    def extract_int(self, payload):
        b_dec = payload[self._start_byte: self._end_byte]
        if self._bit_offset != 0 or self.BitLength < 8:
            _logger.error("Cannot Int with bit offset or not byte")
            return 0
        if self._byte_length == 1:
            value = struct.unpack('<b', b_dec)
        elif self._byte_length == 2:
            value = struct.unpack("<h", b_dec)
        elif self._byte_length == 4:
            value = struct.unpack('<l', b_dec)
        elif self._byte_length == 8:
            value = struct.unpack('<q', b_dec)
        else:
            _logger.error("Incorrect Field length %s" % self._name)
            return 0
        return value[0]

    def apply_scale_offset(self, value):
        try:
            value = value*self.Scale
        except AttributeError:
            pass
        try:
            value += self.Offset
        except AttributeError:
            pass
        return value

    def decode_value(self, payload):
        b_dec = payload[self._start_byte:self._end_byte]
        if self._byte_length == 1:
            return self.extract_uint_byte(b_dec)
        elif self._byte_length == 2:
            # convert the 2 bytes into an integer big endian
            val = struct.unpack('>H', b_dec)
            val = val[0]
            # mask upper bits
            val = val & self.bit_mask16[self._bit_offset]
            remaining_bits = 16 - (self._bit_offset + self.BitLength)
            if remaining_bits > 0:
                val >>= remaining_bits
            return val
        elif self._byte_length == 3 or self._byte_length == 4:
            return self.extract_uint(payload)
        else:
            _logger.error("Cannot decode bit fields over 3 bytes %s %s" % (self._name, self.type()))
            return 0


class UIntField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload):
        return self.extract_uint(payload)


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
            _logger.error("Enum %s key %d non existent" % (self._name, value))
            return "*****"

    def decode_value(self, payload):
        enum_index = self.extract_uint(payload)
        # print("Enum",b_dec,enum_index)
        return self.get_name(enum_index)


class IntField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode(self, payload):
        return self.extract_int(payload)


class DblField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload):
        value = float(self.extract_int(payload))
        return self.apply_scale_offset(value)


class UDblField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload):
        value = float(self.extract_uint(payload))
        return self.apply_scale_offset(value)


class ASCIIField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload):
        return self.decode_string(payload)


class StringField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload):
        return self.decode_string(payload)
