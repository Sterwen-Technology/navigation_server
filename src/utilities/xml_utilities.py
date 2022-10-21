# Name:        xml_utilities
# Purpose:     Set of functions and classes implementing recurring functions
#               to handle xml data
#
# Author:      Laurent Carré
#
# Created:    06/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging
import xml.etree.ElementTree as ET

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class XMLDecodeError(Exception):
    pass


class XMLDefinitionFile:

    def __init__(self, xml_file, definitions_tag):

        try:
            self._tree = ET.parse(xml_file)
        except ET.ParseError as e:
            _logger.error("Error parsing XML file %s: %s" % (xml_file, str(e)))
            raise

        self._root = self._tree.getroot()
        # print(self._root.tag)
        self._definitions = self._root.find(definitions_tag)
        if self._definitions is None:
            raise XMLDecodeError("Missing definitions tag %s" % definitions_tag)
