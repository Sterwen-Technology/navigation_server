#-------------------------------------------------------------------------------
# Name:        init function for nmea2000
# Purpose:
#
# Author:      Laurent Carré
#
# Created:     25/03/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import os.path
import logging

from .nmea2k_manufacturers import Manufacturers
from .nmea2k_pgndefs import  PGNDefinitions
from navigation_server.router_common import MessageServerGlobals, N2KDefinitionError

_logger = logging.getLogger("ShipDataServer."+__name__)


def initialize_feature(options=None):

    rel_path = "./navigation_definitions"
    if not os.path.exists(rel_path):
        rel_path = os.path.join(MessageServerGlobals.home_dir, rel_path)
    if options is not None:
        manufacturer_file = options.get_option('manufacturer_xml', "Manufacturers.N2kDfn.xml")
        definition_file = options.get_option("nmea2000_xml", "PGNDefns.N2kDfn.xml")
    else:
        manufacturer_file = "Manufacturers.N2kDfn.xml"
        definition_file = "PGNDefns.N2kDfn.xml"

    def_file = os.path.join(rel_path, manufacturer_file)
    if os.path.exists(def_file):
        MessageServerGlobals.manufacturers = Manufacturers(def_file)
    else:
        _logger.error(f"Manufacturer definition file is missing => {def_file} non existent")


    def_file = os.path.join(rel_path, definition_file)
    if os.path.exists(def_file):
        MessageServerGlobals.pgn_definitions = PGNDefinitions(def_file)
    else:
        _logger.critical(f"NMEA2000 PGN definition file is missing => stop, {def_file} non existent")
        raise N2KDefinitionError("No definition file")
