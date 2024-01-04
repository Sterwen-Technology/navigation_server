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

from nmea2000.nmea2000_msg import NMEA2000Msg, NMEA2000Object
from nmea2000.nmea2k_name import NMEA2000Name
from generated.nmea2000_classes_gen import Pgn126996Class, Pgn126998Class, Pgn126993Class

_logger = logging.getLogger("ShipDataServer." + __name__)


class AddressClaim(NMEA2000Object):

    parameter_table = []

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

        elif pgn > 0:
            # the object is created internally
            _logger.debug("New Group Function command=%d for PGN %d" % (function, pgn))
            self._pgn = pgn
            self._function = function
        else:
            raise ValueError

    @property
    def function(self) -> int:
        return self._function

    @property
    def function_pgn(self) -> int:
        return self._function_pgn


class CommandGroupFunction(GroupFunction):

    header_struct = struct.Struct("<BB")

    def __init__(self, message=None, pgn=0):

        super().__init__(message, function=1, pgn=pgn)
        if message is not None:
            # decode the rest of the message
            v = self.header_struct.unpack_from(message.payload, 4)
            self._priority = (v[0] >> 4) & 0xf
            self._nb_param = v[1]


class RequestGroupFunction(GroupFunction):

    def __init__(self,message=None, pgn=0):
        super().__init__(message, function=0, pgn=pgn)


class AcknowledgeGroupFunction(GroupFunction):

    def __init__(self,message=None, pgn=0):
        super().__init__(message, function=2, pgn=pgn)


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









