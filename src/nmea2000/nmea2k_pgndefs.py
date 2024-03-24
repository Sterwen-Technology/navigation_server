#-------------------------------------------------------------------------------
# Name:        NMEA2K-PGNDefs
# Purpose:     Manages all NMEA2000 PGN definitions
#
# Author:      Laurent Carré
#
# Created:     05/12/2021
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging


from router_common import XMLDefinitionFile
from router_common import MessageServerGlobals
from router_common import N2KUnknownPGN, N2KDefinitionError

from .nmea2k_enumsdefs import EnumSet
from .nmea2k_pgn_definition import PGNDef


_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class PGNDefinitions(XMLDefinitionFile):

    def __init__(self, xml_file):

        super().__init__(xml_file)
        # first look for global enums
        # Tbd
        MessageServerGlobals.enums = EnumSet(self.get_definitions('GlobalEnums'))
        self._pgn_defs = {}
        self._pgn_count = 0
        self._to_be_generated = []
        #  pgndefs = defs.findall('PGNDefn')
        for pgnxml in self.get_definitions('PGNDefns').iterfind('PGNDefn'):
            try:
                pgn = PGNDef(pgnxml)
                _logger.debug("Processing XML for PGN %d:%s" % (pgn.id, pgn.name))
                existing_entry = self._pgn_defs.get(pgn.id, None)
                if pgn.to_be_generated:
                    self._to_be_generated.append(pgn)
            except N2KDefinitionError as e:
                # _logger.error("%s PGN ignored" % e)
                continue
            if pgn.nb_fields() == 0:
                _logger.info("PGN %d:%s with no fields => ignored" % (pgn.id, pgn.name))
                continue
            if pgn.is_proprietary:
                _logger.debug("PGN %d is proprietary" % pgn.id)
                if existing_entry is None:
                    existing_entry = ProprietaryPGNSet(pgn.id)
                    self._pgn_defs[pgn.id] = existing_entry
                existing_entry.add_variant(pgn.manufacturer_id, pgn)
                self._pgn_count += 1
            else:
                if existing_entry is None:
                    self._pgn_defs[pgn.id] = pgn
                    self._pgn_count += 1
                else:
                    _logger.error("Duplicate PGN %d entry => New entry is ignored" % pgn.id)

    def print_summary(self):
        print("NMEA2000 PGN definitions => number of PGN:%d" % self._pgn_count)
        for pgn in self.pgns():
            print(pgn, pgn.length,"Bytes")
            for f in pgn.fields():
                print("\t", f.descr())

    def pgns(self):
        # become an iterator
        for pgn_def in self._pgn_defs.values():
            if pgn_def.is_proprietary:
                for pgn_prop in pgn_def.pgns():
                    yield pgn_prop
            else:
                yield pgn_def

    def pgn_definition(self, number, manufacturer_id=0):
        if type(number) is str:
            number = int(number)
        try:
            entry = self._pgn_defs[number]
        except KeyError:
            # _logger.error("Unknown PGN %d" % number)
            raise N2KUnknownPGN("Unknown PGN %d" % number)
        if entry.is_proprietary:
            return entry.get_variant(manufacturer_id)
        else:
            return entry

    def is_proprietary_entry(self, number: int) -> bool:
        try:
            return self._pgn_defs[number].is_proprietary
        except KeyError:
            raise N2KUnknownPGN("Unknown PGN %d" % number)

    def generation_iter(self):
        for pgn in self._to_be_generated:
            yield pgn


class ProprietaryPGNSet:

    def __init__(self, pgn):
        self._variants = {}
        self._default = None
        self._pgn = pgn

    def add_variant(self, manufacturer_id: int, pgn_def: PGNDef):
        self._variants[manufacturer_id] = pgn_def
        if self._default is None:
            self._default = pgn_def

    def get_variant(self, manufacturer_id) -> PGNDef:
        if manufacturer_id == 0:
            return self._default
        else:
            try:
                return self._variants[manufacturer_id]
            except KeyError:
                raise N2KUnknownPGN("PGN %d => Unknown variant for manufacturer %d " % (self._pgn, manufacturer_id))

    @property
    def is_proprietary(self) -> bool:
        return True

    def pgns(self) -> PGNDef:
        for p in self._variants.values():
            yield p
