# -------------------------------------------------------------------------------
# Name:        NMEA2K-CAN messages classes
# Purpose:     Classes to implement ISO and CAN services messages 59904, 60928, 65240, 126992, 126993, 126996
#
# Author:      Laurent Carré
#
# Created:     18/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import struct
from collections import namedtuple

from router_core.nmea2000_msg import NMEA2000Msg, NMEA2000Object
from nmea2000.nmea2k_name import NMEA2000Name
from nmea2000.generated_base import extract_var_str
from generated.nmea2000_classes_iso_gen import Pgn126996Class, Pgn126998Class, Pgn126993Class

_logger = logging.getLogger("ShipDataServer." + __name__)

GroupParameter = namedtuple('GroupParameter', ['number', 'value'])


class AddressClaim(NMEA2000Object):

    @staticmethod
    def decode_parameter(param_number, buffer, index):
        param_len, param_name = NMEA2000Name.get_field_property(param_number)
        if param_len == 1:
            value = buffer[index]
        elif param_len == 2:
            v = struct.unpack_from("<H", buffer, index)
            value = v[0]
        elif param_len == 3:
            v = struct.unpack_from("<HB", buffer, index)
            value = v[0] + (v[1] << 16)
        else:
            raise ValueError
        _logger.debug("AddressClaim parameter %d name %s value %d" % (param_number, param_name, value))
        return value, index + param_len

    @staticmethod
    def decode_command_parameters(nb_param: int, buffer: bytearray, index: int):
        _logger.debug("Group Function on 60928 nb_param %d param %s" % (nb_param, buffer))
        param_processed = 0
        result = []
        while param_processed < nb_param:
            param_num = buffer[index]
            if param_num < 1 or param_num > NMEA2000Name.max_fields():
                _logger.error("Group Function on PGN 60928 parameter number out of range %d" % param_num)
                break
            index += 1
            try:
                value, index = AddressClaim.decode_parameter(param_num, buffer, index)
            except ValueError:
                _logger.error("Group Function on PGN 60928 parameter %d error" % param_num)
                break
            result.append((param_num, value))
            param_processed += 1
        return result

    @staticmethod
    def execute_command_parameters(target_obj, parameters: list, ack):
        result = target_obj.modify_parameters(parameters)
        for res in result:
            ack.add_parameter(res)

    def __init__(self, sa=0, name=None, da=255, message=None):
        super().__init__(60928)
        if message is None:
            self._sa = sa
            self._da = da
            self._name = name
            self._prio = 6
        else:
            self.from_message(message)

    def encode_payload(self) -> bytes:
        return self._name.bytes()

    def update(self):
        self._name = self._fields["System ISO Name"]

    @property
    def name(self) -> NMEA2000Name:
        return self._name


class ISORequest(NMEA2000Object):

    def __init__(self, sa=0, da=255, request_pgn=60928):
        super().__init__(59904)
        self._sa = sa
        self._da = da
        self._req_pgn = request_pgn

    def encode_payload(self) -> bytes:
        return bytes([
            self._req_pgn & 0xFF, (self._req_pgn >> 8) & 0xFF, (self._req_pgn >> 16) & 0xFF
        ])

    def update(self):
        try:
            self._req_pgn = self._fields['PGN']
        except KeyError:
            _logger.error("ISORequest error decoding NMEA2000 message missing PGN: %s" % self._fields)

    @property
    def request_pgn(self):
        return self._req_pgn


class ProductInformation(Pgn126996Class):

    def __init__(self, message=None):
        super().__init__(message=message)
        self._da = 255
        self._priority = 6

    def set_product_information(self, model_id: str, software_version: str, model_version: str, serial_code: str):
        def build_fix_str(val):
            nb_space = 32 - len(val)
            if nb_space < 0:
                raise ValueError
            return val + str(nb_space*' ')

        self._model_id = model_id
        self._software_version = software_version
        self._model_version = model_version
        self._model_serial_code = serial_code


class ConfigurationInformation(Pgn126998Class):

    @staticmethod
    def decode_command_parameters(nb_param: int, buffer: bytearray, index: int):
        _logger.debug("Group Function on 126998 nb_param %d param %s" % (nb_param, buffer))
        param_processed = 0
        result = []
        while param_processed < nb_param:
            param_num = buffer[index]
            index += 1
            if param_num == 1 or param_num == 2:
                str_value, param_len = extract_var_str(buffer, index)
                _logger.debug("Group Function for 126998 param %d value %s" % (param_num, str_value))
                result.append((param_num, str_value))
                index += param_len
            else:
                _logger.error("Group Function for 126998 Parameter Error: %d" % param_num)
            param_processed += 1
        return result

    @staticmethod
    def execute_command_parameters(target_obj, parameters: list, ack):
        for param in parameters:
            if param[0] == 1:
                target_obj.installation_1 = param[1]
                res = 0
            elif param[0] == 2:
                target_obj.installation_2 = param[1]
                res = 0
            else:
                res = 1
            ack.add_parameter(res)

    def __init__(self, message=None):
        super().__init__(message=message)
        self._da = 255
        self._priority = 6


class Heartbeat(Pgn126993Class):

    def __init__(self, message=None):
        super().__init__(message=message)


class CommandedAddress(NMEA2000Object):

    def __init__(self, sa=0, da=0, name=None, commanded_address=0, message=None):
        super().__init__(65240)
        if message is None:
            self._sa = sa
            self._da = da
            self._name = name
            self._commanded_address = commanded_address
        else:
            self.from_message(message)

    def update(self):
        self._name = self._fields["System ISO Name"]
        self._commanded_address = self._fields["New Source Address"]

    @property
    def name(self):
        return self._name

    @property
    def commanded_address(self):
        return self._commanded_address


def create_group_function(message: NMEA2000Msg):
    function = message.payload[0]
    return group_function_table[function](message)


class GroupFunction(NMEA2000Object):
    '''
    That PGN need very specific handling as the content is highly variable
    This is the abstract superclass
    '''

    function_str = struct.Struct("<BHB")

    def __init__(self, message: NMEA2000Msg = None, function=0, pgn=0):

        super().__init__(126208)
        if message is not None:
            # the object is created from an incoming message
            self._sa = message.sa
            v = self.function_str.unpack_from(message.payload, 0)
            self._function = v[0]
            self._function_pgn = v[1] + (v[2] << 16)
            _logger.debug("Group Function [%d] on PGN %d" % (self._function, self._function_pgn))
            try:
                self._pgn_class = pgn_function_table[self._function_pgn]
            except KeyError:
                self._pgn_class = None

        elif pgn > 0:
            # the object is created internally
            _logger.debug("New Group Function command=%d for PGN %d" % (function, pgn))
            self._function_pgn = pgn
            self._function = function

        else:
            raise ValueError

    @property
    def function(self) -> int:
        return self._function

    @property
    def function_pgn(self) -> int:
        return self._function_pgn

    @property
    def pgn_class(self):
        return self._pgn_class


class CommandGroupFunction(GroupFunction):

    header_struct = struct.Struct("<BB")

    def __init__(self, message=None, pgn=0):

        super().__init__(message, function=1, pgn=pgn)
        if message is not None:
            # decode the rest of the message
            v = self.header_struct.unpack_from(message.payload, 4)
            self._priority = v[0] & 0xf
            self._nb_param = v[1]
            if self._pgn_class is not None:
                self._params = self._pgn_class.decode_command_parameters(self._nb_param, message.payload, 6)
            else:
                self._params = None

    @property
    def parameters(self):
        return self._params


class RequestGroupFunction(GroupFunction):

    def __init__(self,message=None, pgn=0):
        super().__init__(message, function=0, pgn=pgn)


class AcknowledgeGroupFunction(GroupFunction):

    header_struct = struct.Struct("<BB")
    full_header_struct = struct.Struct("<BHBBB")

    def __init__(self, message=None, pgn=0, pgn_error_code=0):
        super().__init__(message, function=2, pgn=pgn)
        if message is not None:
            v = self.header_struct.unpack_from(message.payload, 4)
            self._pgn_error_code = (v[0] >> 4) & 0xF
            self._transmission_error_code = v[0] & 0xF
            self._nb_param = v[1]
            self._params = []
            self.unpack_params(message[6:])
        else:
            self._pgn_error_code = pgn_error_code
            self._transmission_error_code = 0
            self._nb_param = 0
            self._prio = 3
            self._params = []

    def add_parameter(self, value):
        self._nb_param += 1
        self._params.append(value)

    def unpack_params(self, buffer):
        p_idx = 0
        b_idx = 0
        while p_idx < self._nb_param:
            v = buffer[b_idx]
            if p_idx % 2 == 0:
                self._params.append((v >> 4) & 0xF)
            else:
                self._params.append(v & 0xF)
                b_idx += 1
            p_idx += 1

    def pack_params(self, buffer, index):
        p_idx = 0
        v = 0
        while p_idx < self._nb_param:
            if p_idx % 2 == 0:
                v = self._params[p_idx] << 4
            else:
                v |= self._params[p_idx]
                buffer[index] = v
                index += 1
            p_idx += 1

    def encode_payload(self) -> bytearray:
        param_size = (self._nb_param // 2) + (self._nb_param % 2)
        buffer = bytearray(6 + param_size)
        pgn_l = self._function_pgn & 0xFFFF
        pgn_h = (self._function_pgn >> 16) & 0xFF
        err_code = (self._pgn_error_code << 4) | self._transmission_error_code
        self.full_header_struct.pack_into(buffer, 0, 2, pgn_l, pgn_h, err_code, self._nb_param)
        self.pack_params(buffer, 6)
        return buffer


class ReadFieldsGroupFunction(GroupFunction):

    def __init__(self, message):
        super().__init__(message)


class WriteFieldsGroupFunction(GroupFunction):

    def __init__(self, message):
        super().__init__(message)


group_function_table = {
    0: RequestGroupFunction,
    1: CommandGroupFunction,
    2: AcknowledgeGroupFunction,
    3: ReadFieldsGroupFunction,
    5: WriteFieldsGroupFunction
}


pgn_function_table = {
    60928: AddressClaim,
    126996: ProductInformation,
    126998: ConfigurationInformation
}






