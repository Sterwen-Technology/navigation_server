# -------------------------------------------------------------------------------
# Name:        NMEA2K-Eumsdefs
# Purpose:     Handle definitions of NMEA2000 Global enums values and unit values
#
# Author:      Laurent Carré
#
# Created:     21/11/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
# -------------------------------------------------------------------------------

import logging

from router_common.xml_utilities import XMLDefinitionFile, XMLDecodeError

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
                # print("Enum",value,"=", name)
                self._enum_pair[value] = name

    def get_name(self, value: int):
        return self._enum_pair[value]

    @property
    def name(self):
        return self._name

    @property
    def bit_length(self) -> int:
        return self._bit_length


class UnitSet:

    def __init__(self, xml_root):

        self._units = {}
        for unit_xml in xml_root.iterfind('Unit'):
            try:
                unit = NMEA2000Unit(unit_xml)
            except ValueError:
                continue
            self._units[unit.name] = unit

    def get_unit(self, name):
        try:
            return self._units[name]
        except KeyError:
            _logger.error(f"No unit {name}")
            raise


class NMEA2000Unit:

    def __init__(self, xml):

        self._name = xml.get('Name')
        self._symbol = xml.get('symbol')
        q = xml.find('Quantity')
        if q is not None:
            self._quantity = q.text
        else:
            self._quantity = "Unknown"
        precision = xml.find('Precision')
        if precision is not None:
            self._precision = f"%.{precision.text}f"
        else:
            self._precision = None
        print(f"New unit {self._name} ({self._symbol}) for {self._quantity} Precision {self._precision}")
        scale = xml.find('Scale')
        if scale is not None:
            self._scale = float(scale.text)
        else:
            self._scale = 1.0
        offset = xml.find('Offset')
        if offset is not None:
            self._offset = float(offset.text)
        else:
            self._offset = 0.0

        # now look if we have DisplayUnits
        du_set = xml.find('DisplayUnits')
        if du_set is not None:
            self._display_units = {}
            for du_xml in du_set.iterfind('DisplayUnit'):
                try:
                    du = NMEA2000Unit(du_xml)
                except ValueError:
                    continue
                self._display_units[du.name] = du
        else:
            self._display_units = None

    @property
    def name(self):
        return self._name

    @property
    def symbol(self):
        return self._symbol

    @property
    def scale(self) -> float:
        return self._scale

    def offset(self) -> float:
        return self._offset


