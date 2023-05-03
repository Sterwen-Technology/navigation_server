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
import struct
from collections import namedtuple

from utilities.xml_utilities import XMLDefinitionFile, XMLDecodeError
from nmea2000.nmea2k_manufacturers import Manufacturers


_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class N2KDecodeException(Exception):
    pass


class N2KDecodeEOLException(N2KDecodeException):
    pass


class N2KMissingEnumKeyException(N2KDecodeException):
    pass


class N2KUnknownPGN(Exception):
    pass


class N2KDefinitionError(Exception):
    pass


class PGNDefinitions(XMLDefinitionFile):

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

    @staticmethod
    def print_pgndef(pgn: int, output):
        PGNDefinitions.pgn_definitions.pgn_def(pgn).print_description(output)

    def __init__(self, xml_file):

        super().__init__(xml_file, 'PGNDefns')
        self._pgn_defs = {}
        #  pgndefs = defs.findall('PGNDefn')
        for pgnxml in self._definitions.iterfind('PGNDefn'):
            try:
                pgn = PGNDef(pgnxml)
                self._pgn_defs[pgn.id] = pgn
            except N2KDefinitionError as e:
                _logger.error("%s PGN ignored" % e)

    def print_summary(self):
        print("NMEA2000 PGN definitions => number of PGN:%d" % len(self._pgn_defs))
        for pgn in self._pgn_defs.values():
            print(pgn, pgn.length,"Bytes")
            for f in pgn.fields():
                print("\t", f.descr())

    def pgns(self):
        return self._pgn_defs.values()

    def pgn_def(self, number):
        if type(number) == str:
            number = int(number)
        try:
            return self._pgn_defs[number]
        except KeyError:
            # _logger.error("Unknown PGN %d" % number)
            raise N2KUnknownPGN("Unknown PGN %d" % number)


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


PGNRange = namedtuple('PGNRange', ['start', 'to', 'pdu', 'value', 'description'])


class PGNDef:

    trace_enum_error = False
    trace_decode_warning = False
    (PDU1, PDU2) = range(1, 3)
    (CAN_J1939, STD_SINGLE_FRAME_ADDRESSED, PROP_SINGLE_FRAME_ADDRESSED, STD_SINGLE_FRAME, PROP_SINGLE_FRAME,
     STD_FAST_PACKET_ADDRESSED, PROP_FAST_PACKET_ADDRESSED, STD_MIXED, PROP_FAST_PACKET) = range(0, 9)

    pgn_range = [
        PGNRange(0, 0xE7FF, PDU1, CAN_J1939, 'CAN J1939 PGN'),
        PGNRange(0xE800, 0xEEFF, PDU1, STD_SINGLE_FRAME_ADDRESSED, 'Standard single-frame addressed'),
        PGNRange(0xEF00, 0xEFFF, PDU1, PROP_SINGLE_FRAME_ADDRESSED, 'Proprietary single-frame addressed'),
        PGNRange(0xF000, 0xFEFF, PDU2, STD_SINGLE_FRAME, 'Standard single-frame non-addressed'),
        PGNRange(0xFF00, 0xFFFF, PDU2, PROP_SINGLE_FRAME, 'Proprietary single-frame non-addressed'),
        PGNRange(0x10000, 0x1EE00, PDU1, STD_FAST_PACKET_ADDRESSED, "Standard fast packet addressed"),
        PGNRange(0x1EF00, 0x1EFFF, PDU1, PROP_FAST_PACKET_ADDRESSED, 'Proprietary fast packet addressed'),
        PGNRange(0x1F000, 0x1FEFF, PDU2, STD_MIXED, 'Standard mixed (fast/single) packet non addressed'),
        PGNRange(0x1FF00, 0x1FFFF, PDU2, PROP_FAST_PACKET, 'Proprietary fast packet non-addressed')
    ]

    pgn_service = [59392, 59904, 60928, 65240, 126208, 126464, 126993, 126996]

    @staticmethod
    def set_trace(enum_error: bool, warning: bool):
        PGNDef.trace_enum_error = enum_error
        PGNDef.trace_decode_warning = warning

    @staticmethod
    def find_range(pgn) -> PGNRange:
        if pgn <= PGNDef.pgn_range[4].to:
            for r in PGNDef.pgn_range[:5]:
                if pgn <= r.to:
                    return r
        else:
            for r in PGNDef.pgn_range[5:]:
                if pgn <= r.to:
                    return r
        raise N2KDefinitionError("Invalid PGN %d" % pgn)

    @staticmethod
    def pgn_pdu1_adjust(pgn):
        pdu_format = (pgn >> 8) & 0xFF
        if pdu_format < 240:
            # PDU1
            return pgn & 0x1FF00, pgn & 0xFF
        else:
            return pgn, 0

    @staticmethod
    def fast_packet_check(pgn) -> bool:
        if pgn <= PGNDef.pgn_range[4].to:
            return False
        r = PGNDef.find_range(pgn)
        if r.value != PGNDef.STD_MIXED:
            return True
        pgn_def = PGNDefinitions.pgn_definitions.pgn_def(pgn)
        return pgn_def.fast_packet()

    @staticmethod
    def pgn_for_controller(pgn: int) -> bool:
        if pgn <= PGNDef.pgn_range[0].to:
            return True
        elif pgn in PGNDef.pgn_service:
            return True
        return False

    def __init__(self, pgnxml):
        self._id_str = pgnxml.attrib['PGN']
        self._xml = pgnxml
        self._id = int(self._id_str)
        # now determine the type of PGN we have
        self._pdu_format = (self._id >> 8) & 0xFF
        if self._pdu_format < 240:
            self.pdu_type = self.PDU1
            if self._id & 0xFF != 0:
                _logger.error("Invalid PGN with PDU type 1 PGN%X" % self._id)
                raise N2KDefinitionError("Invalid PGN %d" % self._id)
        else:
            self.pdu_type = self.PDU2
        self._range = self.find_range(self._id)
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
            if self._byte_length <= 0 or self._byte_length > 8:
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

    def pgn_data(self):
        data = [
            self._id,
            self._name,
            self._byte_length,
            self._range.description,
            self._fast_packet,
            len(self._fields)
        ]
        return data

    def decode_pgn_data(self, data: bytes):
        '''
        if len(data) != self._byte_length:
            raise N2KDecodeException("PGN %s decode error expected %d bytes got %d" %
                                     (self._id_str, self._byte_length, len(data)))
        '''

        result = {}
        fields: dict = {}
        _logger.debug("start decoding PGN %d %s payload(%d bytes %s" % (self._id, self._name, len(data), data.hex()))
        index = 0

        for field in self._fields.values():
            # print(field.name, field.type())
            try:
                inner_result = field.decode(data, index, fields)
                # print("result",inner_result.name, inner_result.valid, inner_result.value)
            except N2KMissingEnumKeyException as e:
                if self.trace_enum_error:
                    _logger.info(str(e))
                continue
            except N2KDecodeEOLException:
                _logger.error("EOL error in PGN %s" % self._id_str)
                break
            except N2KDecodeException as e:
                _logger.error("Decoding error in PGN %s: %s" % (self._id_str, str(e)))
                _logger.error("PGN %d %s payload(%d bytes %s" % (self._id, self._name, len(data), data.hex()))
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

    def print_description(self, output):
        output.write("PGN %d: %s\n" % (self._id, self._name))
        for f in self._fields.values():
            f.print_description(output)


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

    bit_mask16_u = [
        0x1FF,
        0x3FF,
        0x7FF,
        0xFFF,
        0x1FFF,
        0x3FFF,
        0x7FFF,
        0xFFFF
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

    def print_description(self, output):
        output.write("\t Field %s (%s)\n" % (self.name, self.type()))

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

        try:
            res = self.decode_value(payload, specs)
        except Exception as e:
            raise N2KDecodeException("Error in field %s type %s: %s" % (self._name, self.type(), e))
        if res is None:
            raise N2KDecodeException("Error in field %s type %s" % (self._name, self.type()))

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
        # print(self._name, "[%s]" % b_dec.hex(), self._byte_length, self._bit_offset, self.BitLength)
        res = N2KDecodeResult(self._name)
        res.actual_length = 1
        val2 = struct.unpack('<B', b_dec)
        # remove the leading bits
        val = val2[0]
        # print("Byte decode",self._name,"byte:",b_dec,"Offset",self._bit_offset,"length",self.BitLength,":%X"%val)
        if self._bit_offset != 0:
            val >>= self._bit_offset
        res.value = val & self.bit_mask_l[self.BitLength]
        if self._bit_offset + self.BitLength < 8:
            res.no_increment()
        # print(self._name, "=%d (%X)" % (res.value, res.value))
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
        if self._bit_offset != 0 or self.BitLength % 8 != 0:
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
        # print(self._name,"[%d:%d]" % (specs.start, specs.end), self._byte_length, self._bit_offset, self.BitLength)
        b_dec = payload[specs.start:specs.end]
        if self._byte_length == 1:
            return self.extract_uint_byte(b_dec)
        elif self._byte_length == 2:
            # convert the 2 bytes into an integer big endian
            res = N2KDecodeResult(self._name)
            if (self.BitLength + self._bit_offset) % 8 == 0:
                res.actual_length = 2
            else:
                res.actual_length = 1
            val = struct.unpack('<H', b_dec)
            val = val[0]
            # mask upper bits
            if self._bit_offset > 0:
                val >>= self._bit_offset
                remaining_bits = 16 - (self._bit_offset + self.BitLength)
                if remaining_bits > 0:
                    val = val & self.bit_mask16[16 - remaining_bits]
            else:
                val = val & self.bit_mask16_u[self.BitLength - 9]
            res.value = val
            # print(self._name, "=%d (%X)" % (val, val))
            # validity check to be finalized
            # correction on 02/05/2023 bitmask index (-9) instead of -8
            if val == self.bit_mask16_u[self.BitLength - 9]:
                res.invalid()
            return res
        elif self._byte_length == 3:
            res = N2KDecodeResult(self._name)

            if (self.BitLength + self._bit_offset) % 8 == 0:
                res.actual_length = 3
            else:
                res.actual_length = 2
            # first decode the first word
            val = struct.unpack('<H', payload[specs.start:specs.start+2])
            val = val[0]
            ad_byte = struct.unpack('<B', payload[specs.start+2:specs.start+3])
            ad_byte = ad_byte[0]
            remaining_bits = 24 - self.BitLength
            val <<= remaining_bits
            ad_byte &= self.bit_mask_l[remaining_bits]
            val += ad_byte
            # print(self._name, "=%d (%X)" % (val, val))
            res.value = val
            return res
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
        res.value = self._value_pair.get(enum_index, "InvalidKey#%d" % enum_index)
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
            _logger.error("PGN %d missing %s field for count reference" % (self._pgn.id, self._count))
            nb_set = 0
        if nb_set < 1:
            _logger.debug("Field set %s empty in PGN %d" % (self._name, self._pgn.id))
            res.invalid()
            res.actual_length = 0
            return res
        payload_l = len(payload)
        _logger.debug("Start decoding Repeating fields at %d number of sets %d" % (index, nb_set))
        specs = DecodeSpecs(index, 0)
        result_fields: list = []
        decoded_set = 0
        while decoded_set < nb_set:
            _logger.debug("Start decoding set %d/%d index:%d" % (decoded_set+1, nb_set, specs.start))
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
                if l_res.increment:
                    specs.start += l_res.actual_length
                    res.actual_length += l_res.actual_length
            decoded_set += 1

        res.value = result_fields
        _logger.debug("End decoding Repeated value %s" % self._name)
        return res

    def print_description(self, output):
        output.write("Repeated field set %s" % self.name)
        for f in self._subfields.values():
            f.print_description(output)

    def type(self):
        return self.__class__.__name__


class ASCIIFixField(Field):

    def __init__(self, xml):
        super().__init__(xml, do_not_process=['SubString'])
        # print(self._name, self._bit_offset, self._byte_length, self.BitOffset, self.BitLength)
        self._subfields = []

    def decode_value(self, payload, specs):
        res = N2KDecodeResult(self._name)
        res.value = payload[specs.start:specs.end].decode()
        # print(self._name, specs.start, specs.end, self._byte_length,":", res.value)
        return res



