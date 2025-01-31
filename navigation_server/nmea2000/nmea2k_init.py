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

from navigation_server.nmea2000_datamodel import Manufacturers, PGNDefinitions
from navigation_server.router_common import MessageServerGlobals, N2KDefinitionError

_logger = logging.getLogger("ShipDataServer."+__name__)


def initialize_feature(options):
    rel_path = "./def"
    if not os.path.exists(rel_path):
        rel_path = os.path.join(MessageServerGlobals.home_dir, rel_path)
    default_file = os.path.join(rel_path, "Manufacturers.N2kDfn.xml")
    if os.path.exists(default_file):
        MessageServerGlobals.manufacturers = Manufacturers(options.get_option('manufacturer_xml', default_file))
    else:
        _logger.error("Manufacturer definition file is missing")

    default_file = os.path.join(rel_path, "PGNDefns.N2kDfn.xml")
    if os.path.exists(default_file):
        MessageServerGlobals.pgn_definitions = PGNDefinitions(options.get_option("nmea2000_xml", default_file))
    else:
        _logger.critical("NMEA2000 PGN definition file is missing => stop")
        raise N2KDefinitionError("No definition file")
