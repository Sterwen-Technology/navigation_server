# -------------------------------------------------------------------------------
# Name:        NMEA2K-Name
# Purpose:     Implements the 64bits ISO Name object
#
# Author:      Laurent Carré
#
# Created:     04/09/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging
import struct

from navigation_server.generated.iso_name_pb2 import ISOName

_logger = logging.getLogger("ShipDataServer." + __name__)


class NMEA2000Name:
    """The Name of one Controller Application.

    The Name consists of 64 bit:

        1-bit Arbitrary Address Capable
        Indicate the capability to solve address conflicts.
        Set to 1 if the device is Arbitrary Address Capable, set to 0 if
        it's Single Address Capable.

        3-bit Industry Group
        One of the predefined J1939 industry groups.
        Shall be 4 for NMEA2000

        4-bit System Instance
        Instance number of a device to distinguish two or more
        devices with the same device System number in the same NMEA2000
        network.
        The first instance is assigned to the instance number 0.

        7-bit Vehicle System
        A subcomponent of a vehicle, that includes one or more J1939
        segments and may be connected or disconnected from the vehicle.
        A Vehicle System may be made of one or more functions. The Vehicle
        System depends on the Industry Group definition.

        1-bit Reserved
        This field is reserved for future use by SAE.

        8-bit Function
        One of the predefined NMEA2000 functions.

        5-bit Function Instance
        Instance number of a function to distinguish two or more devices
        with the same function number in the same J1939 network.
        The first instance is assigned to the instance number 0.

        3-bit ECU Instance
        Identify the ECU instance if multiple ECUs are involved in
        performing a single function. Normally set to 0.

        11-bit Manufacturer Code
        One of the predefined NMEA2000 manufacturer codes.

        21-bit ISO Identity Number
        A unique number which identifies the particular device in a
        manufacturer specific way.
    """

    class IndustryGroup:
        Global = 0
        OnHighway = 1
        AgriculturalAndForestry = 2
        Construction = 3
        Marine = 4
        Industrial = 5

    fields = {}

    class NameField:

        def __init__(self, name, description, bit_size, bit_offset):
            self._name = name
            self._description = description
            self._bit_size = bit_size
            self._mask = (2 ** bit_size) - 1
            self._bit_offset = bit_offset
            self._byte_size = bit_size // 8
            if bit_size % 8 != 0:
                self._byte_size += 1
            # NMEA2000Name.fields[name] = self

        def extract_field(self, value):
            return (value >> self._bit_offset) & self._mask

        def set_field(self, name_value, value):
            return name_value | ((value & self._mask) << self._bit_offset)


        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

        @property
        def byte_size(self):
            return self._byte_size

        @property
        def max(self) -> int:
            return self._mask

    __fields = (
        NameField('identity_number', 'ISO Identity Number', 21, 0),
        NameField('manufacturer_code', "Manufacturer Code", 11, 21),
        NameField('device_instance_lower', "Device Instance Lower", 3, 32),
        NameField('device_instance_upper', "Device Instance Upper", 5, 35),
        NameField('device_function', "Device Function", 8, 40),
        NameField('reserved', "Reserved", 1, 48),
        NameField('device_class', "Device Class", 7, 49),
        NameField('system_instance', "System Instance", 4, 56),
        NameField('industry_group', "Industry Group", 3, 60),
        NameField('arbitrary_address_capable', "Arbitrary Address Capable", 1, 63),
        NameField('name_value', 'Name Value', 64, 0)
    )

    def __init__(self, data):
        """
        :param value:
            64-bit value the address should be extracted from

        :param bytes:
            Array of 8 bytes containing the name object as binary representation.

        :param arbitrary_address_capable:
            1-bit Arbitrary Address Capable
            Indicate the capability to solve address conflicts.
            Set to 1 if the device is Arbitrary Address Capable, set to 0 if
            it's Single Address Capable.
        :param industry_group:
            3-bit Industry Group
            One of the predefined J1939 industry groups.
        :param vehicle_system_instance:
            4-bit Vehicle System Instance
            Instance number of a vehicle system to distinguish two or more
            device with the same Vehicle System number in the same J1939
            network.
            The first instance is assigned to the instance number 0.
        :param vehicle_system:
            7-bit Vehicle System
            A subcomponent of a vehicle, that includes one or more J1939
            segments and may be connected or disconnected from the vehicle.
            A Vehicle System may be made of one or more functions. The Vehicle
            System depends on the Industry Group definition.
        :param function:
            8-bit Function
            One of the predefined J1939 functions. The same function value
            (upper 128 only) may mean different things for different Industry
            Groups or Vehicle Systems.
        :param function_instance:
            5-bit Function Instance
            Instance number of a function to distinguish two or more devices
            with the same function number in the same J1939 network.
            The first instance is assigned to the instance number 0.
        :param ecu_instance:
            3-bit ECU Instance
            Identify the ECU instance if multiple ECUs are involved in
            performing a single function. Normally set to 0.
        :param manufacturer_code:
            11-bit Manufacturer Code
            One of the predefined J1939 manufacturer codes.
        :param identity_number:
            21-bit Identity Number
            A unique number which identifies the particular device in a
            manufacturer specific way.

        NMEA2000 XML definition
        <PGNDefn PGN="60928">
      <Name>ISO Address Claim</Name>
      <ByteLength>8</ByteLength>
      <Fields>
        <Field Name="Unique Number">
          <Description>ISO Identity Number</Description>
          <BitOffset>0</BitOffset>
          <BitLength>21</BitLength>
        </Field>
        <Field Name="Manufacturer Code">
          <BitOffset>21</BitOffset>
          <BitLength>11</BitLength>
        </Field>
        <InstanceField Name="Device Instance Lower">
          <Description>ISO ECU Instance</Description>
          <BitOffset>32</BitOffset>
          <BitLength>3</BitLength>
        </InstanceField>
        <InstanceField Name="Device Instance Upper">
          <Description>ISO Function Instance</Description>
          <BitOffset>35</BitOffset>
          <BitLength>5</BitLength>
        </InstanceField>
        <UIntField Name="Device Function">
          <Description>ISO Function</Description>
          <BitOffset>40</BitOffset>
          <BitLength>8</BitLength>
        </UIntField>
        <Field Name="Reserved">
          <BitOffset>48</BitOffset>
          <BitLength>1</BitLength>
        </Field>
        <EnumField Name="Device Class">
          <BitOffset>49</BitOffset>
          <BitLength>7</BitLength>
          <EnumValues>
            <EnumPair Value="0" Name="Reserved for 2000 Use" />
            <EnumPair Value="10" Name="System tools" />
            <EnumPair Value="20" Name="Safety systems" />
            <EnumPair Value="25" Name="Inter/Intranetwork Device" />
            <EnumPair Value="30" Name="Electrical Distribution" />
            <EnumPair Value="35" Name="Electrical Generation" />
            <EnumPair Value="40" Name="Steering and Control Surfaces" />
            <EnumPair Value="50" Name="Propulsion systems" />
            <EnumPair Value="60" Name="Navigation systems" />
            <EnumPair Value="70" Name="Communication systems" />
            <EnumPair Value="75" Name="Sensor Communication Interface" />
            <EnumPair Value="80" Name="Instrumentation/general systems" />
            <EnumPair Value="85" Name="External Environment" />
            <EnumPair Value="90" Name="Internal Environmental (HVAC) systems" />
            <EnumPair Value="100" Name="Deck, Cargo and Fishing Equipment" />
            <EnumPair Value="120" Name="Display" />
            <EnumPair Value="125" Name="Entertainment" />
          </EnumValues>
        </EnumField>
        <InstanceField Name="System Instance">
          <Description>ISO Device Class Instance</Description>
          <BitOffset>56</BitOffset>
          <BitLength>4</BitLength>
        </InstanceField>
        <EnumField Name="Industry Group">
          <BitOffset>60</BitOffset>
          <BitLength>3</BitLength>
          <EnumValues>
            <EnumPair Value="4" Name="Marine" />
          </EnumValues>
        </EnumField>
        <UIntField Name="ISO Self Configurable">
          <BitOffset>63</BitOffset>
          <BitLength>1</BitLength>
        </UIntField>
      </Fields>
    </PGNDefn>
        """
        self.init_fields()
        self._bytes = data
        # _logger.debug("NMEA2000 Name bytes:%s" % data.hex())
        self._value = int.from_bytes(data, byteorder='little', signed=False)
        # _logger.debug("NMEA2000 Name value:%16X" % self._value)

    @staticmethod
    def init_fields():
        if len(NMEA2000Name.fields) == 0:
            for f in NMEA2000Name.__fields:
                NMEA2000Name.fields[f.name] = f

    @staticmethod
    def max_fields() -> int:
        return len(NMEA2000Name.__fields)

    def __getattr__(self, item):
        try:
            return self.fields[item].extract_field(self._value)
        except KeyError:
            _logger.error("NMEA2000Name unknown field:%s " % item)
            raise AttributeError

    def bytes(self):
        """Get the Name object as 8 Byte Data"""
        return self._bytes

    def __str__(self):
        res = ""
        for f in self.fields.values():
            res += "%s = %d\n" % (f.description, f.extract_field(self._value))
        return res

    def __eq__(self, name):
        if type(name) is not NMEA2000Name:
            return False
        return self._value == name.int_value

    @property
    def int_value(self) -> int:
        return self._value

    @staticmethod
    def create_name(**kwargs):
        name = 0
        NMEA2000Name.init_fields()
        for key, value in kwargs.items():
            field = NMEA2000Name.fields[key]
            name = field.set_field(name, value)
        name_bytes = struct.pack("<Q", name)
        return NMEA2000Name(name_bytes)

    @staticmethod
    def get_field_property(field_num: int):
        '''
        Return the field definition for Group function decode
        Start at 0
        '''
        if field_num < 1 or field_num > len(NMEA2000Name.__fields):
            _logger.error("ISO Name parameter out of range: %d" % field_num)
            raise IndexError
        field_def = NMEA2000Name.__fields[field_num - 1]
        return field_def.byte_size, field_def.name

    def set_protobuf(self, res: ISOName):
        res.identity_number = self.identity_number
        res.manufacturer_code = self.manufacturer_code
        res.device_instance_lower = self.device_instance_lower
        res.device_instance_upper = self.device_instance_upper
        res.device_function = self.device_function
        res.device_class = self.device_class
        res.system_instance = self.system_instance
        res.industry_group = self.industry_group
        res.arbitrary_address_capable = bool(self.arbitrary_address_capable)


class NMEA2000MutableName(NMEA2000Name):
    '''
    Variant of ISO J1939 Name but with fields that can be changed dynamically

    '''

    def __init__(self, **kwargs):
        super().init_fields()
        self._value = 0
        self._value_dict = {}
        for key, value in kwargs.items():
            try:
                field = NMEA2000Name.fields[key]
            except KeyError:
                _logger.error("ISO Name unknown field:%s" % key)
                continue
            self._value_dict[key] = value
        self.build_value()

    def build_value(self):
        self._value = 0
        for field in self.fields.values():
            try:
                value = self._value_dict[field.name]
                self._value = field.set_field(self._value, value)
            except KeyError:
                continue
        self._bytes = self._value.to_bytes(8, byteorder='little')

    parameter_set_table = {3: 'device_instance_lower',
                           4: 'device_instance_upper',
                           8: 'system_instance'}

    def modify_parameters(self, param_list):
        result = []
        change = False
        for param in param_list:
            try:
                key = self.parameter_set_table[param[0]]
            except KeyError:
                _logger.error("ISO Name parameter %d not modifiable" % param[0])
                result.append(1)
                continue
            field = self.fields[key]
            if param[1] < 0 or param[1] > field.max:
                _logger.error("ISO Name parameter %d value %d out of range" % param)
                result.append(3)
                continue
            self._value_dict[key] = param[1]
            change = True
            result.append(0)
        if change:
            self.build_value()
        return result





