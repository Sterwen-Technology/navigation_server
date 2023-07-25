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
        self._state = self.OPEN
        self._logfile.prepare_read()
        self._state = self.CONNECTED
        return True

    def close(self):
        pass

    def _read(self):
        try:
            return NMEA0183Msg(self._logfile.read_message())
        except ValueError:
            return NavGenericMsg(NULL_MSG)

    def log_file_characteristics(self) -> dict:
        if self._state is self.NOT_READY:
            return None

        return {'start_date': self._logfile.start_date(),
                'end_date': self._logfile.end_date(),
                'nb_records': self._logfile.nb_records(),
                'duration': self._logfile.duration(),
                'filename': self._logfile.filename()
                }

    def current_log_date(self):
        if self._state == self.ACTIVE:
            return {'current_date': self._logfile.get_current_log_date()}

    def move_index(self, args):
        if self._state == self.ACTIVE:
            delta_t = args.get('delta', None)
            if delta_t is not None:
                self._logfile.move_forward(delta_t)

    def move_to_date(self, args):
        if self._state == self.ACTIVE:
            target_date = args.get('target_date', None)
            if target_date is not None:
                td = datetime.datetime.fromisoformat(target_date)
                self._logfile.move_to_date(td)
