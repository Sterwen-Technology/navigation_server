#-------------------------------------------------------------------------------
# Name:        serial_gps
# Purpose:     Serial NMEA port specialization for GPS
#
# Author:      Laurent Carré
#
# Created:     24/03/2026
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2026
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------

import logging

from .serial_nmeaport import NMEASerialPort

_logger = logging.getLogger("ShipDataServer"+"."+__name__)


class SerialGPS(NMEASerialPort):

    def __init__(self, opts):
        super().__init__(opts)
        self._direction = self.READ_ONLY
        self._source = opts.get('talker', str, None)
        self._formatters_str = opts.getlist('formatters', str)
        if self._source is not None:
            if len(self._source) != 2:
                raise ValueError("Invalid format for source")
            self._source = bytes(self._source, 'utf-8')
        if self._formatters_str is not None:
            self._formatters = set(fmt for fmt in self._formatters_str)
        else:
            self._formatters = None


    def _read(self):
        msg = super()._read()
        if self._formatters is not None:
            while True:
                if msg.formatter().decode() not in self._formatters:
                    msg = super()._read()
                    continue
                else:
                    break
        if self._source is not None:
            msg.replace_talker(self._source)
        return msg


