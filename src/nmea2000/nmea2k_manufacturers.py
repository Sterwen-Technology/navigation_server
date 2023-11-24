#-------------------------------------------------------------------------------
# Name:        NMEA2K-Manufacturers
# Purpose:     Manages all NMEA2000 Manufacturers codes
#
# Author:      Laurent Carré
#
# Created:     06/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from utilities.xml_utilities import XMLDefinitionFile

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class Manufacturer:

    def __init__(self, name: str, code: int, key=None):
        self._name = name
        self._code = code
        if key is not None:
            self._key = key
        else:
            self._key = name

    @property
    def name(self) -> str :
        return self._name

    @property
    def code(self) -> int :
        return self._code

    @property
    def key(self):
        return self._key


class Manufacturers(XMLDefinitionFile):

    def __init__(self, xml_file):

        super().__init__(xml_file)
        self._manufacturer_by_code = {}
        self._manufacturer_by_key = {}
        for mfg_def in self.get_definitions('Manufacturers').iterfind('Manufacturer'):
            name = mfg_def.find('Name').text
            code = int(mfg_def.find('Code').text)
            key = mfg_def.find('Key')
            if key is not None:
                key = key.text
            else:
                inds = -1
                for sep in [',', ' ']:
                    inds = name.find(sep)
                    if inds > 0:
                        break
                if inds <= 0:
                    key = name
                else:
                    key = name[:inds]
            mfg = Manufacturer(name, code, key)
            self._manufacturer_by_code[code] = mfg
            self._manufacturer_by_key[key] = mfg

    def print_manufacturers(self):
        for mfg in self._manufacturer_by_code.values():
            print(mfg.name, '|', mfg.key, '|', mfg.code)

    def by_code(self, code: int) -> Manufacturer:
        if code == 0:
            return "Mfg Code Error"
        else:
            return self._manufacturer_by_code[code]

    def by_key(self, key: str) -> Manufacturer:
        return self._manufacturer_by_key[key]
