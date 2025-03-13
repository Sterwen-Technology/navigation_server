# -------------------------------------------------------------------------------
# Name:        nmea2k_pgn_definition
# Purpose:     Handle NMEA2000 PGN messages structure
#
# Author:      Laurent Carré
#
# Created:     24/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
from collections import namedtuple

from navigation_server.router_common import (N2KDecodeException, N2KDefinitionError, N2KDecodeEOLException,
                                             N2KMissingEnumKeyException,MessageServerGlobals, build_subclass_dict)

from .nmea2k_fielddefs import RepeatedFieldSet, Field
from .nmea2k_encode_decode import BitField
from .nmea2k_bitfield_generator import BitFieldGenerator

_logger = logging.getLogger("ShipDataServer." + __name__)


PGNRange = namedtuple('PGNRange', ['start', 'to', 'pdu', 'value', 'description'])


class PGNDef (BitFieldGenerator):

    trace_enum_error = False
    trace_decode_warning = False
    field_classes = build_subclass_dict(Field)
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

    pgn_service = [59392, 59904, 60928, 65240, 126208, 126464, 126993, 126996, 126998]

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
        pgn_def = MessageServerGlobals.pgn_definitions.pgn_definition(pgn)
        return pgn_def.fast_packet()

    @staticmethod
    def pgn_for_controller(pgn: int) -> bool:
        if pgn <= PGNDef.pgn_range[0].to:
            return True
        elif pgn in PGNDef.pgn_service:
            return True
        return False

    def __init__(self, pgnxml):

        BitFieldGenerator.__init__(self)
        self._id_str = pgnxml.attrib['PGN']
        self._xml = pgnxml
        self._id = int(self._id_str)
        self._generate = False
        self._name = pgnxml.find('Name').text
        # check of we decode it
        in_scope = pgnxml.find('Scope')
        if in_scope is not None:
            if in_scope.text == 'Ignored':
                _logger.info("PGN %d (%s) ignored from the XML file" % (self._id, self._name))
                raise N2KDefinitionError("Marked as Ignored")
            elif in_scope.text == 'Generate':
                self._generate = True
        flags = pgnxml.find("Flags")
        if flags is not None:
            self._flags = flags.text.split(',')
        else:
            self._flags = None
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

        self._proprietary = self.is_pgn_proprietary(self._id)
        self._manufacturer_id = None
        self._fields = {}

        bl = pgnxml.find('ByteLength')
        if bl is not None:
            self._byte_length = int(bl.text)
            if self._byte_length <= 0:
                self._variable_length = True
            else:
                self._variable_length = False
        else:
            self._byte_length = 0
            self._variable_length = True

        # determination of fast packet
        if self._id <= PGNDef.pgn_range[4].to:
            self._fast_packet = False
        else:
            r = PGNDef.find_range(self._id)
            if r.value != PGNDef.STD_MIXED:
                self._fast_packet = True
            else:
                # mixed bag
                if self._variable_length or self._byte_length > 8:
                    self._fast_packet = True
                else:
                    self._fast_packet = False

        fields = pgnxml.find('Fields')
        self._field_list = []

        if fields is None:
            _logger.info("PGN %s has no Fields" % self._id_str)
            return

        _logger.debug("Starting fields analysis for PGN %d %s" % (self._id, self._name))

        field_index = 0
        for field in fields.iter():
            if field.tag.endswith('Field'):
                try:
                    # field_class = globals()[field.tag]
                    field_class = self.field_classes[field.tag]
                except KeyError:
                    _logger.error("PGN %d Field class %s not defined for %s" % (self._id, field.tag, field.get('Name')))
                    continue
                try:
                    fo = field_class(self, field)
                except Exception as err:
                    _logger.error(f"Error during analysis of PGN {self._id} field {field.get('Name')}: {err}")
                    raise N2KDefinitionError(f"Cannot process definition for PGN{self._id}")

                fo.set_index(field_index)
                field_index += 1
                self.check_bf_add_field(fo)

            elif field.tag == "RepeatedFieldSet":
                fo = RepeatedFieldSet(field, self)
                self._fields[fo.name] = fo
                self._field_list.append(fo)
                # now adjust the counter properties
                count_field = fo.count_field
                count_field.set_repeated_field(fo)
                break
        self.check_and_finalize()
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
                self._manufacturer_id = MessageServerGlobals.manufacturers.by_key(mfg_name).code
            except KeyError:
                raise N2KDefinitionError("PGN %d:%s - Unknown Manufacturer name %s" % (self._id, self._name, mfg_name))

    def __str__(self):
        return "%s %s" % (self._id_str, self._name)

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def length(self) -> int:
        return self._byte_length

    def fast_packet(self) -> bool:
        return self._fast_packet

    def fields(self):
        return self._fields.values()

    def nb_fields(self) -> int:
        return len(self._field_list)

    def field_iter(self):
        # iterator respecting the order of declaration
        for f in self._field_list:
            yield f

    @property
    def field_list(self):
        return self._field_list

    def search_field(self, name) -> Field:
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

    def add_field(self, field):
        self._fields[field.name] = field
        self._field_list.append(field)

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

    @property
    def to_be_generated(self) -> bool:
        return self._generate

    def has_flag(self, flag: str) -> bool:
        if self._flags is None:
            return False
        return flag in self._flags

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




