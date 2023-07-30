#-------------------------------------------------------------------------------
# Name:        NMEA0183 DEFS
# Purpose:     Manages all NMEA0183 definitions
#
# Author:      Laurent Carré
#
# Created:     29/07/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from utilities.xml_utilities import XMLDefinitionFile, XMLDecodeError

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class NMEA0183Definitions(XMLDefinitionFile):

    def __init__(self, xml_file):

        super().__init__(xml_file, "N0183Defns")

        for def_xml in self._definitions.iterfind("N0183Defn"):

