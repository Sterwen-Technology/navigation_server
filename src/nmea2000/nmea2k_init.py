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


from nmea2000_datamodel import Manufacturers
from nmea2000_datamodel import PGNDefinitions
from router_common import MessageServerGlobals


def initialize_feature(options):
    MessageServerGlobals.manufacturers = Manufacturers(options.get_option('manufacturer_xml',
                                                                          './def/Manufacturers.N2kDfn.xml'))
    MessageServerGlobals.pgn_definitions = PGNDefinitions(options.get_option("nmea2000_xml",
                                                                             './def/PGNDefns.N2kDfn.xml'))