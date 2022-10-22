#-------------------------------------------------------------------------------
# Name:        nmea_filter
# Purpose:     classes to filter our NMEA messages based on various rules
#
# Author:      Laurent Carré
#
# Created:     06/10/2022
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2022
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------


import logging
import yaml


_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class FilterSet:

    def __init__(self, filename: str):

        try:
            fp = open(filename, 'r')
        except IOError as e:
            _logger.error()