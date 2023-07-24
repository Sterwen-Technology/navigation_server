#-------------------------------------------------------------------------------
# Name:        raw_log_coupler
# Purpose:     Class implement a coupler (simulator) based on raw logs
#
# Author:      Laurent Carré
#
# Created:     23/07/2023
# Copyright:   (c) Laurent Carré Sterwen Technology 2021-2023
# Licence:     Eclipse Public License 2.0
#-------------------------------------------------------------------------------
import datetime
import logging

from utilities.raw_log_reader import RawLogFile
from nmea_routing.coupler import Coupler
from nmea_routing.nmea0183 import NMEA0183Msg
from nmea_routing.generic_msg import NavGenericMsg, NULL_MSG

_logger = logging.getLogger("ShipDataServer."+__name__)


class RawLogCoupler(Coupler):

    def __init__(self, opts):
        super().__init__(opts)
        self._filename = opts.get('logfile', str, None)
        if self._filename is None:
            raise ValueError
        self._logfile = None

    def open(self):
        try:
            self._logfile = RawLogFile(self._filename)
        except IOError:
            return False
        self._logfile.prepare_read()
        return True

    def close(self):
        pass

    def _read(self):
        try:
            return NMEA0183Msg(self._logfile.read_message())
        except ValueError:
            return NavGenericMsg(NULL_MSG)

    def current_log_date(self):
        return self._logfile.get_current_log_date().isoformat()

    def move_index(self, delta_t):
        self._logfile.move_forward(delta_t)

    def move_to_date(self, target_date):
        td = datetime.datetime.fromisoformat(target_date)
        self._logfile.move_to_date(td)
