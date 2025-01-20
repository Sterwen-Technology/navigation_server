#-------------------------------------------------------------------------------
# Name:        nmea0183_filters
# Purpose:     Implementation of filters for NMEA0183 messages
#
# Author:      Laurent Carré
#
# Created:     26/02/2024
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2025
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from router_core import NMEAFilter
from router_common import N0183_MSG
from router_core.nmea0183_msg import NMEA0183Msg

_logger = logging.getLogger('ShipDataServer.' + __name__)


class NMEA0183Filter(NMEAFilter):

    def __init__(self, opts):
        super().__init__(opts)
        self._talker = opts.get('talker', str, None)
        if self._talker is not None:
            self._talker = self._talker.encode()
        self._formatter = opts.get('formatter', str, None)
        if self._formatter is not None:
            self._formatter = self._formatter.encode()

    def valid(self) -> bool:
        if self._talker is not None or self._formatter is not None:
            return super().valid()
        else:
            return False

    def process_nmea0183(self, msg: NMEA0183Msg) -> bool:

        if self._talker is None or self._talker == msg.talker():
            talker = True
        else:
            talker = False
        # _logger.debug("Filter formatter %s with %s" % (self._formatter, msg.formatter()))
        if self._formatter is None or self._formatter == msg.formatter():
            formatter = True
        else:
            formatter = False
        result = talker and formatter
        if result:
            _logger.debug("Processing NMEA0183 filter %s with message %s ==>> OK" % (self._name, msg))
        return result

    def message_type(self):
        return N0183_MSG
