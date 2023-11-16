#-------------------------------------------------------------------------------
# Name:        NMEA2K-PGNDefs
# Purpose:     Manages all NMEA2000 PGN definitions
#
# Author:      Laurent Carré
#
# Created:     05/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
from collections import namedtuple

from utilities.xml_utilities import XMLDefinitionFile, XMLDecodeError
from nmea2000.nmea2k_name import NMEA2000Name
from nmea2000.nmea2k_manufacturers import Manufacturers
from nmea2000.nmea2k_encode_decode import (BitField, BitFieldSplitException, DecodeSpecs, N2KDecodeResult,
                                           DecodeDefinitions)


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


class N2KEncodeException(Exception):
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
    def pgn_definition(pgn, manufacturer_id=0):
        return PGNDefinitions.pgn_definitions.pgn_def(pgn, manufacturer_id)

    @staticmethod
    def print_pgndef(pgn: int, output, manufacturer_id=0):
        PGNDefinitions.pgn_definitions.pgn_def(pgn, manufacturer_id).print_description(output)

    def __init__(self, xml_file):

        super().__init__(xml_file, 'PGNDefns')
        self._pgn_defs = {}
        self._pgn_count = 0
        #  pgndefs = defs.findall('PGNDefn')
        for pgnxml in self._definitions.iterfind('PGNDefn'):
            try:
                pgn = PGNDef(pgnxml)
                _logger.debug("Processing XML for PGN %d:%s" % (pgn.id, pgn.name))
                existing_entry = self._pgn_defs.get(pgn.id, None)
            except N2KDefinitionError as e:
                _logger.error("%s PGN ignored" % e)
                continue
            if pgn.nb_fields() == 0:
                _logger.info("PGN %d:%s with no fields => ignored" % (pgn.id, pgn.name))
                continue
            if pgn.is_proprietary:
                _logger.debug("PGN %d is proprietary" % pgn.id)
                if existing_entry is None:
                    existing_entry = ProprietaryPGNSet()
                    self._pgn_defs[pgn.id] = existing_entry
                existing_entry.add_variant(pgn.manufacturer_id, pgn)
                self._pgn_count += 1
            else:
                if existing_entry is None:
                    self._pgn_defs[pgn.id] = pgn
                    self._pgn_count += 1
                else:
                    _logger.error("Duplicate PGN %d entry => New entry is ignored" % pgn.id)

    def print_summary(self):
        print("NMEA2000 PGN definitions => number of PGN:%d" % self._pgn_count)
        for pgn in self.pgns():
            print(pgn, pgn.length,"Bytes")
            for f in pgn.fields():
                print("\t", f.descr())

    def pgns(self):
        # become an iterator
        for pgn_def in self._pgn_defs.values():
            if pgn_def.is_proprietary:
                for pgn_prop in pgn_def.pgns():
                    yield pgn_prop
            else:
                yield pgn_def

    def pgn_def(self, number, manufacturer_id=0):
        if type(number) is str:
            number = int(number)
        try:
            entry = self._pgn_defs[number]
        except KeyError:
            # _logger.error("Unknown PGN %d" % number)
            raise N2KUnknownPGN("Unknown PGN %d" % number)
        if entry.is_proprietary:
            return entry.get_variant(manufacturer_id)
        else:
            return entry


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

    (NO_BITFIELD, NEW_BITFIELD, BITFIELD_IN_PROGRESS) = range(0, 3)

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
    def is_pgn_proprietary(pgn):
        range = PGNDef.find_range(pgn)
        if range.value in (PGNDef.PROP_SINGLE_FRAME_ADDRESSED, PGNDef.PROP_SINGLE_FRAME,
                           PGNDef.PROP_FAST_PACKET_ADDRESSED, PGNDef.PROP_FAST_PACKET):
            return True
        else:
            return False

    @staticmethod
    def pgn_pdu1_adjust(pgn):
        pdu_format = (pgn >> 8) & 0xFF
        if pdu_format < 240:
            # PDU1
            return pgn & 0x1FF00, pgn & 0xFF
        else:
            return pgn, 0xFF

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
        # check of we decode it
        in_scope = pgnxml.find('Scope')
        if in_scope is not None:
            if in_scope.text == 'Ignored':
                _logger.info("PGN %d ignored from the XML file" % self._id)
                raise N2KDefinitionError("Marked as Ignored")
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
        self._proprietary = self.is_pgn_proprietary(self._id)
        self._manufacturer_id = None
        self._fields = {}
        self._fast_packet = False
        self._bitfield_in_create = None
        self._bitfield_no = 1
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
        self._field_list = []

        if fields is None:
            _logger.info("PGN %s has no Fields" % self._id_str)
            return

        _logger.debug("Starting fields analysis for PGN %d %s" % (self._id, self._name))
        for field in fields.iter():
            if field.tag.endswith('Field'):
                try:
                    field_class = globals()[field.tag]
                except KeyError:
                    _logger.error("Field class %s not defined" % field.tag)
                    continue
                fo = field_class(field)
                bf_state = self.check_bitfield(fo)
                if bf_state == self.NO_BITFIELD:
                    self._fields[fo.name] = fo
                    self._field_list.append(fo)
                elif bf_state == self.NEW_BITFIELD:
                    self._fields[self._bitfield_in_create.name] = self._bitfield_in_create
                    self._field_list.append(self._bitfield_in_create)

            elif field.tag == "RepeatedFieldSet":
                fo = RepeatedFieldSet(field, self)
                self._fields[fo.name] = fo
                self._field_list.append(fo)
                break
        if self._bitfield_in_create is not None:
            self._bitfield_in_create.finalize()
        if self._proprietary:
            # look for the manufacturer
            try:
                mfg_field = self.search_field('Manufacturer Code')
            except KeyError:
                raise N2KDefinitionError("PDN%d:%s - Missing 'Manufacturer Code' field" % (self._id, self._name))
            try:
                mfg_name = mfg_field.description
            except AttributeError:
                raise N2KDefinitionError("PGN %d:%s - Missing Manufacturer name in Description" % (self._id, self._name))
            # now retrieve the manufacturer id from the name
            try:
                self._manufacturer_id = Manufacturers.get_from_key(mfg_name).code
            except KeyError:
                raise N2KDefinitionError("PGN %d:%s - Unknown Manufacturer name %s" % (self._id, self._name, mfg_name))

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

    def nb_fields(self) -> int:
        return len(self._field_list)

    def search_field(self, name):
        # need to perform a full search
        for f in self._field_list:
            if isinstance(f, (BitField, RepeatedFieldSet)):
                try:
                    return f.search_field(name)
                except KeyError:
                    continue
            elif f.name == name:
                return f
        raise KeyError

    @property
    def pdu_format(self):
        return self._pdu_format

    @property
    def is_proprietary(self) -> bool:
        return self._proprietary

    @property
    def manufacturer_id(self) -> int:
        if self._manufacturer_id is not None:
            return self._manufacturer_id
        else:
            raise ValueError

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

        for field in self._field_list:
            # print(field.name, field.type())
            try:
                inner_result = field.decode(data, index, fields)
                # print("result",inner_result.name, inner_result.valid, inner_result.value)
            except N2KMissingEnumKeyException as e:
                if self.trace_enum_error:
                    _logger.info(str(e))
                continue
            except N2KDecodeEOLException as e_eol:
                _logger.error("EOL error in PGN %s : %s" % (self._id_str, e_eol))
                break
            except N2KDecodeException as e:
                _logger.error("Decoding error in PGN %s: %s" % (self._id_str, str(e)))
                _logger.error("PGN %d %s payload(%d bytes %s" % (self._id, self._name, len(data), data.hex()))
                continue
            if type(field) != BitField:
                # in that case fields have been updated during decode
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

    def encode_payload(self, fields: dict) -> bytes:
        '''
        This method takes the dictionary (field name, value) and encode the payload
        '''

        if self._variable_length:
            buffer_length = 272
        else:
            buffer_length = self.length
        # print("Start encoding PGN %s" % self._id, "buffer length", buffer_length)
        buffer = bytearray(buffer_length)

        index = 0
        for f in self._field_list:
            try:
                value = fields[f.name]
            except KeyError:
                value = f.no_value()

            index += f.encode_value(value, buffer, index)
            if index > buffer_length:
                raise N2KDecodeException
            # print("Encoded field", f.name, len(buffer[:index]), "Index:", index)
        return buffer[:index]

    def check_bitfield(self, field) -> int:
        if field.is_bit_value():
            if self._bitfield_in_create is not None:
                try:
                    self._bitfield_in_create.add_field(field)
                    return self.BITFIELD_IN_PROGRESS
                except BitFieldSplitException:
                    self._bitfield_in_create.finalize()
                    self._bitfield_in_create = BitField(field, self._bitfield_no)
                    self._bitfield_no += 1
                    return self.NEW_BITFIELD
            else:
                self._bitfield_in_create = BitField(field, self._bitfield_no)
                self._bitfield_no += 1
                return self.NEW_BITFIELD
        else:
            if self._bitfield_in_create is not None:
                self._bitfield_in_create.finalize()
                self._bitfield_in_create = None
            return self.NO_BITFIELD


class Field:

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
        if 0 < self._byte_length <= 4:
            self._value_coder = DecodeDefinitions.uint_table[self._byte_length]
        else:
            self._value_coder = None

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

    def is_bit_value(self) -> bool:
        return self._bit_offset != 0 or self.BitLength % 8 != 0

    @property
    def bit_length(self):
        return self.BitLength

    @property
    def rel_bit_offset(self):
        return self._bit_offset

    @property
    def abs_bit_offset(self):
        return self.BitOffset

    @property
    def description(self):
        return self.Description

    @property
    def start_byte(self):
        return self._start_byte

    def is_enum(self) -> bool:
        return issubclass(type(self), EnumField)

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

        if specs.end > len(payload):
            if self._name != 'Spare':
                raise N2KDecodeEOLException("Field %s end %d past payload length %d " % (self._name, specs.end, len(payload)))
            else:
                res = N2KDecodeResult(self._name)
                res.invalid()
                return res

        try:
            res = self.decode_value(payload, specs)
        except Exception as e:
            _logger.error("Decode error %s in Field %s length %d start %d end %d total len %d" %
                          (e, self._name, self._byte_length, specs.start, specs.end, len(payload)))
            raise N2KDecodeException("Error in field %s type %s: %s" % (self._name, self.type(), e))
        if res is None:
            raise N2KDecodeException("Error in field %s type %s" % (self._name, self.type()))

        if res.valid:
            validity = "valid"
        else:
            validity = "invalid"
        _logger.debug("Result %s=%s %s" % (res.name, str(res.value), validity))
        return res
        #except Exception as e:
            # _logger.error("For field %s(%s)) %s" % (self._name, self.type(), str(e)))
            # raise N2KDecodeException("For field %s(%s)) %s" % (self._name, self.type(), str(e)))

    def extract_value(self, payload, specs):
        b_dec = payload[specs.start:specs.end]
        res = N2KDecodeResult(self._name)
        res.actual_length = self._byte_length
        try:
            res.value = self._value_coder.decode(b_dec)
        except ValueError:
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

    def convert_to_int(self, value: float) -> int:
        try:
            value -= self.Offset
        except AttributeError:
            pass
        try:
            value = value / self.Scale
        except AttributeError:
            pass
        return round(value)

    def no_value(self):
        if self._byte_length <= 4:
            return DecodeDefinitions.uint_invalid[self._byte_length]
        else:
            raise N2KDecodeException("No default value")

    def decode_value(self, payload, specs):
        # print(self._name,"[%d:%d]" % (specs.start, specs.end), self._byte_length, self._bit_offset, self.BitLength)
        return self.extract_value(payload, specs)

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

    def encode_value(self, value, buffer, index) -> int:
        return self._value_coder.encode(value, buffer, index)

    '''
    def encode_uint(self, value: int, buffer: bytearray, index) -> int:
        if self._byte_length == 1:
            buffer[index] = value & 0xFF
            return 1
        elif self._byte_length == 2:
            struct.pack_into('<H', buffer, index, value & 0xFFFF)
            return 2
        elif self._byte_length == 3:
            b = struct.pack('<I', value & 0xFFFFFF)
            buffer[index:] = b[:3]
            return 3
        elif self._byte_length == 4:
            struct.pack_into('<I', buffer, index, value)
            return 4
        elif self._byte_length == 8:
            struct.pack_into('<Q', buffer, index, value)
            return 8
        else:
            raise N2KEncodeException("Cannot encode uint l=%d" % self._byte_length)

    def encode_int(self, value: int, buffer: bytearray, index):
        if self._byte_length == 2:
            struct.pack_into('<i', buffer, index, value & 0xFFFF)
            return 2
        if self._byte_length == 4:
            struct.pack_into('<l', buffer, index, value)
        else:
            raise N2KEncodeException("Cannot encode uint l=%d" % self._byte_length)
    
    '''

    def encode_str(self, str_value: str, buffer: bytearray, index):
        if self._variable_length:
            buffer[index: index + len(str_value)] = str_value.encode()
            return len(str_value)
        else:
            buffer[index: index + self._byte_length] = str_value.encode()[:self._byte_length]
            return self._byte_length


class UIntField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_value(payload, specs)


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
        return self._value_pair[value]

    def decode_value(self, payload, specs):
        res = self.extract_value(payload, specs)
        if not res.valid:
            return res
        enum_index = res.value
        # print("Enum",b_dec,enum_index)
        res.value = self._value_pair.get(enum_index, "InvalidKey#%d" % enum_index)
        return res


class EnumIntField (EnumField):

    def decode_value(self, payload, specs):
        res = self.extract_value(payload, specs)
        if not res.valid:
            return res
        enum_index = res.value
        res.value = self._value_pair.get(enum_index, res.value)
        return res


class IntField(Field):

    def __init__(self, xml):
        super().__init__(xml)
        self._value_coder = DecodeDefinitions.int_table[self.length()]

    def decode_value(self, payload, specs):
        return self.extract_value(payload, specs)

    def is_bit_value(self) -> bool:
        return False


class DblField(Field):

    def __init__(self, xml):
        super().__init__(xml)
        self._value_coder = DecodeDefinitions.int_table[self.length()]

    def decode_value(self, payload, specs):
        res = self.extract_value(payload, specs)
        # print("Dbl result %X" % res.value, "Valid", res.valid)
        if res.valid:
            res.value = self.apply_scale_offset(float(res.value))
        return res

    def is_bit_value(self) -> bool:
        return False

    def encode_value(self, value, buffer, index) -> int:
        val_int = self.convert_to_int(value)
        return super().encode_value(val_int, buffer, index)


class UDblField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        res = self.extract_value(payload, specs)
        if res.valid:
            res.value = self.apply_scale_offset(float(res.value))
        return res

    def is_bit_value(self) -> bool:
        return False

    def encode_value(self, value, buffer, index) -> int:
        val_int = self.convert_to_int(value)
        return super().encode_value(val_int, buffer, index)


class ASCIIField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_var_str(payload, specs)

    def is_bit_value(self) -> bool:
        return False

    def encode_value(self, value, buffer, index) -> int:
        return self.encode_str(value, buffer, index)


class StringField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_var_str(payload, specs)

    def is_bit_value(self) -> bool:
        return False

    def encode_value(self, value, buffer, index) -> int:
        return self.encode_str(value, buffer, index)


class FixLengthStringField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        res = N2KDecodeResult(self._name)
        try:
            str_val = payload[specs.start: specs.end].decode()
        except UnicodeError:
            res.invalid()
            return res
        str_val = str_val.strip('@\x20\x00')
        res.value = str_val
        # print("FixLengthString", payload[specs.start: specs.end],"=>", str_val)
        return res

    def encode_value(self, value, buffer, index) -> int:
        if len(value) > self._byte_length:
            value = value[:self._byte_length]
        elif len(value) <  self._byte_length:
            # ok we fill with blank
            value = value.rjust(self._byte_length, ' ')
        buffer[index: index+self._byte_length] = value
        return self._byte_length


class NameField(Field):
    '''
    This class is here to decode 64bits long ISO Name
    See class NMEA2000Name for details
    '''

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        b_dec = payload[specs.start: specs.end]

        res = N2KDecodeResult(self._name)
        if len(b_dec) != 8:
            _logger.error("ISO Name field must be 8 bytes")
            res.invalid()
            return
        res.value = NMEA2000Name(b_dec)
        res.actual_length = 8
        return res

    def encode_value(self, value: NMEA2000Name, buffer, index) -> int:
        buffer[index:] = value.bytes()
        return 8


class CommunicationStatusField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        # Dummy function for new
        res = N2KDecodeResult(self._name)
        res.actual_length = 3
        res.invalid()
        return res


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

    def search_field(self, name):
        return self._subfields[name]

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
        # if we have some invalidated characters at the end
        null_start = payload[specs.start:specs.end].find(0xff)
        if null_start > 0:
            specs.end = null_start
        res.value = payload[specs.start:specs.end].decode()
        # print(self._name, specs.start, specs.end, self._byte_length,":", res.value)
        return res

    def encode_value(self, value, buffer, index) -> int:
        return self.encode_str(value, buffer, index)


class ProprietaryPGNSet:

    def __init__(self):
        self._variants = {}

    def add_variant(self, manufacturer_id: int, pgn_def: PGNDef):
        self._variants[manufacturer_id] = pgn_def

    def get_variant(self, manufacturer_id) -> PGNDef:
            return self._variants[manufacturer_id]

    @property
    def is_proprietary(self) -> bool:
        return True

    def pgns(self):
        for p in self._variants.values():
            yield p
