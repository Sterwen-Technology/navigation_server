# -------------------------------------------------------------------------------
# Name:        NMEA2K-Eumsdefs
# Purpose:     Handle definitions of NMEA2000 Global enums values
#
# Author:      Laurent Carré
#
# Created:     21/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from utilities.xml_utilities import XMLDefinitionFile, XMLDecodeError

_logger = logging.getLogger("ShipDataServer." + __name__)


class EnumSet:

    def __init__(self, xml_root):

        self._enum_defs = {}
        for enum_xml in xml_root.iterfind('Enum'):
            try:
                enum = NMEA2000Enum(enum_xml)

            except ValueError:
                continue
            self._enum_defs[enum.name] = enum

    def get_enum(self, name: str):
        return self._enum_defs[name]


class NMEA2000Enum:

    def __init__(self, enum_xml):
        self._name = enum_xml.get('Name')
        self._enum_pair = {}
        self._bit_length = 0
        for attrib in enum_xml.iter():
            if attrib.tag == 'BitLength':
                self._bit_length = int(attrib.text)
            if attrib.tag == 'EnumPair':
                value = int(attrib.get('Value'))
                name = attrib.get('Name')
                print("Enum",value,"=", name)
                self._enum_pair[value] = name

    def get_name(self, value: int):
        return self._enum_pair[value]

    @property
    def name(self):
        return self._name


