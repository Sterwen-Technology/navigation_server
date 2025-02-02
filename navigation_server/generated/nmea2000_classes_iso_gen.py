#   Python code generated by NMEA message router application (c) Sterwen Technology 2023
#   generated on 2025-02-02:18:46
#   do not modify code


import struct

from navigation_server.router_common import N2KInvalidMessageException, get_global_enum
from navigation_server.nmea2000_datamodel import *
from navigation_server.generated.nmea2000_pb2 import nmea2000_decoded_pb

from navigation_server.generated.nmea2000_classes_iso_gen_pb2 import *


class Pgn126993Class(NMEA2000DecodedMsg):

    _pgn = 126993
    _name = 'Heartbeat'
    _proprietary = False

    @staticmethod
    def protobuf_class():
        return Pgn126993ClassPb

    _struct_str_0 = struct.Struct('<HBBI')
    _struct_str_0_size = _struct_str_0.size
    __slots__ = ('_interval', '_sequence', '_ctrl1_state', '_ctrl2_state', '_equipment_status')

    _static_size = 8

    @classmethod
    def size(cls):
        return cls._static_size

    @staticmethod
    def variable_size() -> bool:
        return False

    _json_format = (
        FloatFormatter('_interval', 'Interval', '{:.2f}'),
        GenericFormatter('_sequence', 'Sequence', 0xff),
        GenericFormatter('_ctrl1_state', 'Controller 1 state', 0x3),
        GenericFormatter('_ctrl2_state', 'Controller 2 state', 0x3),
        GenericFormatter('_equipment_status', 'Equipment Status', 0x3)
        )

    def json_format(self):
        return self._json_format

    def __init__(self, message=None, protobuf=None):
        super().__init__(message, protobuf)

    @property
    def pgn(self) -> int:
        return self._pgn

    @property
    def name(self) -> str:
        return self._name

    @property
    def proprietary(self) -> bool:
        return self._proprietary

    @property
    def interval(self) -> float:
        return self._interval

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def ctrl1_state(self) -> int:
        return self._ctrl1_state

    @property
    def ctrl2_state(self) -> int:
        return self._ctrl2_state

    @property
    def equipment_status(self) -> int:
        return self._equipment_status

    @interval.setter
    def interval(self, value: float):
        self._interval = value

    @sequence.setter
    def sequence(self, value: int):
        self._sequence = value

    @ctrl1_state.setter
    def ctrl1_state(self, value: int):
        self._ctrl1_state = value

    @ctrl2_state.setter
    def ctrl2_state(self, value: int):
        self._ctrl2_state = value

    @equipment_status.setter
    def equipment_status(self, value: int):
        self._equipment_status = value

    def decode_payload(self, payload, start_byte=0):
        val = self._struct_str_0.unpack_from(payload, start_byte)
        self._interval = check_convert_float(val[0], 0xffff, 0.001)
        self._sequence = val[1]
        self._ctrl1_state = val[2] & 0x3
        self._ctrl2_state = (val[2] >> 2) & 0x3
        self._equipment_status = (val[2] >> 4) & 0x3
        start_byte += 8
        return self

    def encode_payload(self) -> bytearray:
        buf_size = self.__class__.size()
        buffer = bytearray(buf_size)
        start_byte = 0
        v0 = convert_to_int(self._interval, 0xffff, 0.001)
        v1 = (self._ctrl1_state & 0x3) << 0
        v1 |= (self._ctrl2_state & 0x3) << 2
        v1 |= (self._equipment_status & 0x3) << 4
        v1 |= 0x3 << 6
        v2 = 0xffffffff
        self._struct_str_0.pack_into(buffer, 0 + start_byte, v0, self._sequence, v1, v2)
        return buffer

    def from_protobuf(self, message: Pgn126993ClassPb):
        self._interval = message.interval
        self._sequence = message.sequence
        self._ctrl1_state = message.ctrl1_state
        self._ctrl2_state = message.ctrl2_state
        self._equipment_status = message.equipment_status

    def as_protobuf(self) -> Pgn126993ClassPb:
        message = Pgn126993ClassPb()
        message.interval = self._interval
        message.sequence = self._sequence
        message.ctrl1_state = self._ctrl1_state
        message.ctrl2_state = self._ctrl2_state
        message.equipment_status = self._equipment_status
        return message

    def set_protobuf(self, message: Pgn126993ClassPb):
        message.interval = self._interval
        message.sequence = self._sequence
        message.ctrl1_state = self._ctrl1_state
        message.ctrl2_state = self._ctrl2_state
        message.equipment_status = self._equipment_status

    def unpack_protobuf(self, protobuf: nmea2000_decoded_pb):
        payload = Pgn126993ClassPb()
        protobuf.payload.Unpack(payload)
        self.from_protobuf(payload)

    def __str__(self):
        return f'PGN{self._pgn}({self._name}) [interval={self._interval}, sequence={self._sequence}, ctrl1_state={self._ctrl1_state}, ctrl2_state={self._ctrl2_state}, equipment_status={self._equipment_status}]'


class Pgn126996Class(NMEA2000DecodedMsg):

    _pgn = 126996
    _name = 'Product Information'
    _proprietary = False

    @staticmethod
    def protobuf_class():
        return Pgn126996ClassPb

    _struct_str_0 = struct.Struct('<HH')
    _struct_str_0_size = _struct_str_0.size
    _struct_str_1 = struct.Struct('<BB')
    _struct_str_1_size = _struct_str_1.size
    __slots__ = ('_nmea2000_version', '_product_code', '_model_id', '_software_version', '_model_version', '_model_serial_code', '_certification_level', '_load_equivalency')

    _static_size = 134

    @classmethod
    def size(cls):
        return cls._static_size

    @staticmethod
    def variable_size() -> bool:
        return False

    _json_format = (
        GenericFormatter('_nmea2000_version', 'NMEA 2000 Version', 0xffff),
        GenericFormatter('_product_code', 'Product Code', 0xffff),
        TextFormatter('_model_id', 'Model ID'),
        TextFormatter('_software_version', 'Software Version Code'),
        TextFormatter('_model_version', 'Model Version'),
        TextFormatter('_model_serial_code', 'Model Serial Code'),
        GenericFormatter('_certification_level', 'Certification Level', 0xff),
        GenericFormatter('_load_equivalency', 'Load Equivalency', 0xff)
        )

    def json_format(self):
        return self._json_format

    def __init__(self, message=None, protobuf=None):
        super().__init__(message, protobuf)

    @property
    def pgn(self) -> int:
        return self._pgn

    @property
    def name(self) -> str:
        return self._name

    @property
    def proprietary(self) -> bool:
        return self._proprietary

    @property
    def nmea2000_version(self) -> int:
        return self._nmea2000_version

    @property
    def product_code(self) -> int:
        return self._product_code

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def software_version(self) -> str:
        return self._software_version

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def model_serial_code(self) -> str:
        return self._model_serial_code

    @property
    def certification_level(self) -> int:
        return self._certification_level

    @property
    def load_equivalency(self) -> int:
        return self._load_equivalency

    @nmea2000_version.setter
    def nmea2000_version(self, value: int):
        self._nmea2000_version = value

    @product_code.setter
    def product_code(self, value: int):
        self._product_code = value

    @model_id.setter
    def model_id(self, value: str):
        self._model_id = value

    @software_version.setter
    def software_version(self, value: str):
        self._software_version = value

    @model_version.setter
    def model_version(self, value: str):
        self._model_version = value

    @model_serial_code.setter
    def model_serial_code(self, value: str):
        self._model_serial_code = value

    @certification_level.setter
    def certification_level(self, value: int):
        self._certification_level = value

    @load_equivalency.setter
    def load_equivalency(self, value: int):
        self._load_equivalency = value

    def decode_payload(self, payload, start_byte=0):
        val = self._struct_str_0.unpack_from(payload, start_byte)
        self._nmea2000_version = val[0]
        self._product_code = val[1]
        start_byte += 4
        self._model_id = clean_string(payload[start_byte: start_byte + 32])
        start_byte += 32
        self._software_version = clean_string(payload[start_byte: start_byte + 32])
        start_byte += 32
        self._model_version = clean_string(payload[start_byte: start_byte + 32])
        start_byte += 32
        self._model_serial_code = clean_string(payload[start_byte: start_byte + 32])
        start_byte += 32
        val = self._struct_str_1.unpack_from(payload, start_byte)
        self._certification_level = val[0]
        self._load_equivalency = val[1]
        start_byte += 2
        return self

    def encode_payload(self) -> bytearray:
        buf_size = self.__class__.size()
        buffer = bytearray(buf_size)
        start_byte = 0
        self._struct_str_0.pack_into(buffer, 0 + start_byte, self._nmea2000_version, self._product_code)
        insert_string(buffer, 4 + start_byte, 32, self._model_id)
        insert_string(buffer, 36 + start_byte, 32, self._software_version)
        insert_string(buffer, 68 + start_byte, 32, self._model_version)
        insert_string(buffer, 100 + start_byte, 32, self._model_serial_code)
        self._struct_str_1.pack_into(buffer, 132 + start_byte, self._certification_level, self._load_equivalency)
        return buffer

    def from_protobuf(self, message: Pgn126996ClassPb):
        self._nmea2000_version = message.nmea2000_version
        self._product_code = message.product_code
        self._model_id = message.model_id
        self._software_version = message.software_version
        self._model_version = message.model_version
        self._model_serial_code = message.model_serial_code
        self._certification_level = message.certification_level
        self._load_equivalency = message.load_equivalency

    def as_protobuf(self) -> Pgn126996ClassPb:
        message = Pgn126996ClassPb()
        message.nmea2000_version = self._nmea2000_version
        message.product_code = self._product_code
        message.model_id = self._model_id
        message.software_version = self._software_version
        message.model_version = self._model_version
        message.model_serial_code = self._model_serial_code
        message.certification_level = self._certification_level
        message.load_equivalency = self._load_equivalency
        return message

    def set_protobuf(self, message: Pgn126996ClassPb):
        message.nmea2000_version = self._nmea2000_version
        message.product_code = self._product_code
        message.model_id = self._model_id
        message.software_version = self._software_version
        message.model_version = self._model_version
        message.model_serial_code = self._model_serial_code
        message.certification_level = self._certification_level
        message.load_equivalency = self._load_equivalency

    def unpack_protobuf(self, protobuf: nmea2000_decoded_pb):
        payload = Pgn126996ClassPb()
        protobuf.payload.Unpack(payload)
        self.from_protobuf(payload)

    def __str__(self):
        return f'PGN{self._pgn}({self._name}) [nmea2000_version={self._nmea2000_version}, product_code={self._product_code}, model_id={self._model_id}, software_version={self._software_version}, model_version={self._model_version}, model_serial_code={self._model_serial_code}, certification_level={self._certification_level}, load_equivalency={self._load_equivalency}]'


class Pgn126998Class(NMEA2000DecodedMsg):

    _pgn = 126998
    _name = 'Configuration Information'
    _proprietary = False

    @staticmethod
    def protobuf_class():
        return Pgn126998ClassPb

    __slots__ = ('_installation_1', '_installation_2', '_manufacturer_info')


    @staticmethod
    def variable_size() -> bool:
        return True

    _json_format = (
        TextFormatter('_installation_1', 'Installation Description #1'),
        TextFormatter('_installation_2', 'Installation Description #2'),
        TextFormatter('_manufacturer_info', 'Manufacturer Info')
        )

    def json_format(self):
        return self._json_format

    def __init__(self, message=None, protobuf=None):
        super().__init__(message, protobuf)

    @property
    def pgn(self) -> int:
        return self._pgn

    @property
    def name(self) -> str:
        return self._name

    @property
    def proprietary(self) -> bool:
        return self._proprietary

    @property
    def installation_1(self) -> str:
        return self._installation_1

    @property
    def installation_2(self) -> str:
        return self._installation_2

    @property
    def manufacturer_info(self) -> str:
        return self._manufacturer_info

    @installation_1.setter
    def installation_1(self, value: str):
        self._installation_1 = value

    @installation_2.setter
    def installation_2(self, value: str):
        self._installation_2 = value

    @manufacturer_info.setter
    def manufacturer_info(self, value: str):
        self._manufacturer_info = value

    def decode_payload(self, payload, start_byte=0):
        dec_str, dec_str_len = extract_var_str(payload, start_byte)
        self._installation_1 = dec_str
        start_byte += dec_str_len
        dec_str, dec_str_len = extract_var_str(payload, start_byte)
        self._installation_2 = dec_str
        start_byte += dec_str_len
        dec_str, dec_str_len = extract_var_str(payload, start_byte)
        self._manufacturer_info = dec_str
        start_byte += dec_str_len
        return self, start_byte

    def encode_payload(self) -> bytearray:
        buf_size = self.DEFAULT_BUFFER_SIZE
        buffer = bytearray(buf_size)
        start_byte = 0
        inserted_len = insert_var_str(buffer, start_byte, self._installation_1)
        start_byte += inserted_len
        inserted_len = insert_var_str(buffer, start_byte, self._installation_2)
        start_byte += inserted_len
        inserted_len = insert_var_str(buffer, start_byte, self._manufacturer_info)
        start_byte += inserted_len
        return buffer[:start_byte]

    def from_protobuf(self, message: Pgn126998ClassPb):
        self._installation_1 = message.installation_1
        self._installation_2 = message.installation_2
        self._manufacturer_info = message.manufacturer_info

    def as_protobuf(self) -> Pgn126998ClassPb:
        message = Pgn126998ClassPb()
        message.installation_1 = self._installation_1
        message.installation_2 = self._installation_2
        message.manufacturer_info = self._manufacturer_info
        return message

    def set_protobuf(self, message: Pgn126998ClassPb):
        message.installation_1 = self._installation_1
        message.installation_2 = self._installation_2
        message.manufacturer_info = self._manufacturer_info

    def unpack_protobuf(self, protobuf: nmea2000_decoded_pb):
        payload = Pgn126998ClassPb()
        protobuf.payload.Unpack(payload)
        self.from_protobuf(payload)

    def __str__(self):
        return f'PGN{self._pgn}({self._name}) [installation_1={self._installation_1}, installation_2={self._installation_2}, manufacturer_info={self._manufacturer_info}]'


#####################################################################
#         Generated class dictionary
#####################################################################
nmea2k_generated_classes = {
        126993: Pgn126993Class,
        126996: Pgn126996Class,
        126998: Pgn126998Class
        }
# end of generated file
