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
            # NMEA2000Name.fields[name] = self

        def extract_field(self, value):
            return (value >> self._bit_offset) & self._mask

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

    __fields = (
        NameField('identity_number', 'ISO Identity Number', 21, 0),
        NameField('manufacturer_code', "Manufacturer Code", 11, 21),
        NameField('device_instance_lower', "Device Instance Lower", 3, 32),
        NameField('device_instance_upper', "Device Instance Upper", 5, 35),
        NameField('device_function', "Device Function", 8, 40),
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
        if len(self.fields) == 0:
            for f in self.__fields:
                self.fields[f.name] = f
        self._bytes = data
        # _logger.debug("NMEA2000 Name bytes:%s" % data.hex())
        self._value = int.from_bytes(data, byteorder='little', signed=False)
        # _logger.debug("NMEA2000 Name value:%16X" % self._value)

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

    @staticmethod
    def create_name(**kwargs):
        pass
