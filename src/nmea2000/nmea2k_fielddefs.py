# -------------------------------------------------------------------------------
# Name:        nmea2k_fielddefs
# Purpose:     Handle NMEA2000 messages fields
#
# Author:      Laurent Carré
#
# Created:     24/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------


import logging

from nmea2000.nmea2k_name import NMEA2000Name
from nmea2000.nmea2k_encode_decode import (DecodeSpecs, N2KDecodeResult, DecodeDefinitions, FIXED_LENGTH_NUMBER,
                                           FIXED_LENGTH_BYTES, VARIABLE_LENGTH_BYTES, REPEATED_FIELD_SET)
from nmea2000.nmea2k_bitfield_generator import BitFieldGenerator
from utilities.global_variables import MessageServerGlobals, Typedef
from utilities.global_exceptions import *

_logger = logging.getLogger("ShipDataServer." + __name__)


class Field:

    def __init__(self, xml, do_not_process=None):
        self._start_byte = 0
        self._end_byte = 0
        self._bit_offset = 0
        self._byte_length = 0
        self._index = -1
        self._variable_length = False
        self._name = xml.attrib['Name']
        self._keyword = xml.attrib.get('key')
        # if self._keyword is not None:
            #  print("Field", self._name, "Keyword", self._keyword)
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

    @property
    def keyword(self) -> str:
        return self._keyword

    @property
    def index(self) -> int:
        return self._index

    def set_index(self, index):
        self._index = index

    @property
    def decode_string(self) -> str:
        raise NotImplementedError("To be defined in subclasses")

    @property
    def decode_method(self) -> int:
        raise NotImplementedError("To be defined in subclasses")

    @property
    def nb_decode_slots(self) -> int:
        return 1

    @property
    def python_type(self):
        raise NotImplementedError("To be defined in subclasses")

    @property
    def protobuf_type(self):
        raise NotImplementedError("To be defined in subclasses")

    def descr(self):
        return "%s %s offset %d length %d bit offset %d" % (self._name, self.type(),
                                                            self._start_byte, self._byte_length, self._bit_offset)

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

    @property
    def typedef(self):
        raise NotImplementedError

    @property
    def signed(self) -> bool:
        return False

    def print_description(self, output):
        output.write("\t Field %s (%s)\n" % (self.name, self.type()))

    def decode(self, payload, index, fields):
        '''
        print("Decoding field %s type %s start %d length %d offset %d bits %d" % (
            self._name, self.type(), self._start_byte, self._byte_length, self._bit_offset, self.BitLength
        ))
        '''
        _logger.debug("Decoding field %s type %s start %d(%d) end %d (%d)" %
                      (self._name, self.type(), self._start_byte, index, self._end_byte, len(payload)))
        specs = DecodeSpecs(0, 0)
        if self._start_byte == 0:
            specs.start = index
        else:
            specs.start = self._start_byte
        if self._byte_length != 0:
            specs.end = specs.start + self._byte_length

        if specs.end > len(payload):
            if self._name != 'Spare':
                raise N2KDecodeEOLException(
                    "Field %s end %d past payload length %d " % (self._name, specs.end, len(payload)))
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
        # except Exception as e:
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
            value = value * self.Scale
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

    @property
    def scale(self):
        try:
            return self.Scale
        except AttributeError:
            return None

    @property
    def offset(self):
        try:
            return self.Offset
        except AttributeError:
            return None

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
        type_s = payload[specs.start + 1]
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
        res.value = payload[specs.start + 2:specs.end].decode()
        return res

    def encode_value(self, value, buffer, index) -> int:
        return self._value_coder.encode(value, buffer, index)

    def encode_str(self, str_value: str, buffer: bytearray, index):
        if self._variable_length:
            buffer[index: index + len(str_value)] = str_value.encode()
            return len(str_value)
        else:
            buffer[index: index + self._byte_length] = str_value.encode()[:self._byte_length]
            return self._byte_length


decode_uint_str = {1: "B", 2: "H", 3: "HB", 4: "I", 8: "Q"}
decode_int_str = {1: "b", 2: "h", 3: "hb", 4: "i", 8: "q"}


class UIntField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_value(payload, specs)

    @property
    def decode_method(self):
        return FIXED_LENGTH_NUMBER

    @property
    def decode_string(self) -> str:
        if self.is_bit_value():
            raise ValueError
        else:
            return decode_uint_str[self._byte_length]

    @property
    def nb_decode_slots(self):
        return len(decode_int_str[self._byte_length])

    @property
    def python_type(self):
        return 'int'

    @property
    def typedef(self):
        return Typedef.UINT


class InstanceField(UIntField):

    def __init__(self, xml):
        super().__init__(xml)


class EnumField(Field):

    def __init__(self, xml):
        super().__init__(xml, do_not_process=("EnumValues", "EnumPair"))
        self._global_enum_name = xml.get('Definition')
        self._global_enum = None
        if self._global_enum_name is not None:
            # now we need to look into the global enum table
            try:
                self._global_enum = MessageServerGlobals.enums.get_enum(self._global_enum_name)
                # print("EnumField", self.name, "Use global enum", self._global_enum.name)
            except KeyError:
                _logger.error("Global enum definition %s non-existent" % self._global_enum_name)
        if self._global_enum is None:
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
        else:
            self._value_pair = None
        # print(self._value_pair)

    def get_name(self, value):
        if self._global_enum is None:
            return self._value_pair[value]
        else:
            return self._global_enum(value)

    def decode_value(self, payload, specs):
        res = self.extract_value(payload, specs)
        if not res.valid:
            return res
        enum_index = res.value
        # print("Enum",b_dec,enum_index)
        if self._global_enum is None:
            res.value = self._value_pair.get(enum_index, "InvalidKey#%d" % enum_index)
        else:
            res.value = self._global_enum(enum_index)
        return res

    @property
    def decode_method(self):
        return FIXED_LENGTH_NUMBER

    @property
    def decode_string(self) -> str:
        if self.is_bit_value():
            raise ValueError
        else:
            return decode_uint_str[self._byte_length]

    @property
    def nb_decode_slots(self) -> int:
        return len(decode_uint_str[self._byte_length])

    @property
    def python_type(self):
        return 'int'

    @property
    def typedef(self):
        return Typedef.UINT

    @property
    def global_enum(self):
        return self._global_enum_name

    def get_enum_dict(self):
        return self._value_pair


class EnumIntField(EnumField):

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

    @property
    def decode_method(self):
        return FIXED_LENGTH_NUMBER

    @property
    def decode_string(self) -> str:
        if self.is_bit_value():
            raise ValueError
        else:
            return decode_int_str[self._byte_length]

    @property
    def python_type(self):
        return 'int'

    @property
    def typedef(self):
        return Typedef.INT

    @property
    def signed(self) -> bool:
        return True

    @property
    def nb_decode_slots(self):
        return len(decode_int_str[self._byte_length])


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

    @property
    def decode_method(self):
        return FIXED_LENGTH_NUMBER

    @property
    def decode_string(self) -> str:
        if self.is_bit_value():
            raise ValueError
        else:
            return decode_int_str[self._byte_length]

    @property
    def nb_decode_slots(self):
        return len(decode_int_str[self._byte_length])

    @property
    def python_type(self):
        return "float"

    @property
    def typedef(self):
        return Typedef.FLOAT

    @property
    def signed(self) -> bool:
        return True


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

    @property
    def decode_method(self):
        return FIXED_LENGTH_NUMBER

    @property
    def decode_string(self) -> str:
        if self.is_bit_value():
            raise ValueError
        else:
            return decode_uint_str[self._byte_length]

    @property
    def nb_decode_slots(self):
        return len(decode_uint_str[self._byte_length])

    @property
    def python_type(self):
        return "float"

    @property
    def typedef(self):
        return Typedef.FLOAT


class ASCIIField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_var_str(payload, specs)

    def is_bit_value(self) -> bool:
        return False

    def encode_value(self, value, buffer, index) -> int:
        return self.encode_str(value, buffer, index)

    @property
    def decode_method(self):
        return VARIABLE_LENGTH_BYTES

    @property
    def typedef(self):
        return Typedef.STRING

    @property
    def python_type(self):
        return 'str'


class StringField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        return self.extract_var_str(payload, specs)

    def is_bit_value(self) -> bool:
        return False

    def encode_value(self, value, buffer, index) -> int:
        return self.encode_str(value, buffer, index)

    @property
    def decode_method(self):
        return VARIABLE_LENGTH_BYTES

    @property
    def typedef(self):
        return Typedef.STRING

    @property
    def python_type(self):
        return 'str'


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
        elif len(value) < self._byte_length:
            # ok we fill with blank
            value = value.rjust(self._byte_length, ' ')
        buffer[index: index + self._byte_length] = value
        return self._byte_length

    @property
    def decode_method(self):
        return FIXED_LENGTH_BYTES

    @property
    def typedef(self):
        return Typedef.STRING

    @property
    def python_type(self) -> str:
        return 'str'


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

    @property
    def decode_method(self):
        return FIXED_LENGTH_NUMBER


class CommunicationStatusField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    def decode_value(self, payload, specs):
        # Dummy function for new
        res = N2KDecodeResult(self._name)
        res.actual_length = 3
        res.invalid()
        return res

    @property
    def decode_method(self):
        return FIXED_LENGTH_NUMBER


class BytesField(Field):

    def __init__(self, xml):
        super().__init__(xml)

    @property
    def decode_method(self):
        return FIXED_LENGTH_BYTES

    @property
    def typedef(self):
        return Typedef.BYTES


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

    @property
    def decode_method(self):
        return FIXED_LENGTH_BYTES

    @property
    def typedef(self):
        return Typedef.STRING

    @property
    def python_type(self):
        return 'str'


class RepeatedFieldSet (BitFieldGenerator):

    def __init__(self, xml, pgn):

        super().__init__()
        self._name = xml.attrib['Name']
        self._pgn = pgn
        self._count = xml.attrib["Count"]
        self._keyword = xml.attrib.get("key")
        self._subfields = {}
        self._field_list = []
        for field in xml.iter():
            if field.tag.endswith('Field'):
                try:
                    field_class = globals()[field.tag]
                except KeyError:
                    _logger.error("Field class %s not defined in PGN %d" % (field.tag, pgn))
                    continue
                fo = field_class(field)
                self.check_bf_add_field(fo)
        self.check_and_finalize()

    @property
    def name(self):
        return self._name

    @property
    def id(self) -> int:
        return self._pgn.id

    def search_field(self, name):
        return self._subfields[name]

    def add_field(self, fo):
        self._subfields[fo.name] = fo
        self._field_list.append(fo)

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
            _logger.debug("Start decoding set %d/%d index:%d" % (decoded_set + 1, nb_set, specs.start))
            for f in self._subfields.values():
                if f.length() != 0:
                    specs.end = specs.start + f.length()
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

    @property
    def decode_method(self) -> int:
        return REPEATED_FIELD_SET

    @property
    def keyword(self) -> str:
        return self._keyword

    @property
    def count_method(self) -> str:
        return self._pgn.search_field(self._count).keyword

    @property
    def field_list(self):
        return self._field_list

    @property
    def python_type(self):
        return 'list'

