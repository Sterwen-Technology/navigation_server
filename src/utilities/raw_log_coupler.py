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
import threading
import queue

from utilities.raw_log_reader import RawLogFile
from nmea_routing.coupler import Coupler
from nmea_routing.nmea0183 import NMEA0183Msg
from nmea_routing.nmea2000_msg import FastPacketHandler, fromProprietaryNmea
from nmea_routing.generic_msg import NavGenericMsg, NULL_MSG

_logger = logging.getLogger("ShipDataServer."+__name__)


class AsynchLogReader(threading.Thread):

    def __init__(self, out_queue, process_message):
        super().__init__()
        self._logfile = None
        self._out_queue = out_queue
        self._stop_flag = False
        self._process_message = process_message

    def open(self, logfile):
        self._logfile = logfile

    def stop(self):
        self._stop_flag = True

    def run(self):

        while not self._stop_flag:
            try:
                msg0183 = NMEA0183Msg(self._logfile.read_message())
            except ValueError:
                self._out_queue.put(NavGenericMsg(NULL_MSG))
                break
            try:
                msg = self._process_message(msg0183)
            except ValueError:
                continue
            self._out_queue.put(msg)


class RawLogCoupler(Coupler):

    def __init__(self, opts):
        super().__init__(opts)
        self._filename = opts.get('logfile', str, None)
        self._direction = self.READ_ONLY
        if self._filename is None:
            raise ValueError
        self._logfile = None

        # need to initialize NMEA2000 decoding
        self._fast_packet_handler = FastPacketHandler(self)
        self._in_queue = queue.SimpleQueue(10)
        if self._mode == self.NMEA0183:
            self._reader = AsynchLogReader(self._in_queue, self.process_nmea0183())
        else:
            self._reader = AsynchLogReader(self._in_queue, self.process_n2k)

    def open(self):
        try:
            self._logfile = RawLogFile(self._filename)
        except IOError:
            return False
        self._reader.open(self._logfile)
        self._state = self.OPEN
        self._logfile.prepare_read()
        self._state = self.CONNECTED
        return True

    def close(self):
        self._reader.stop()
        self._reader.join()

    def stop(self):
        super().stop()
        self.close()

    def _read(self):
        return self._in_queue.get()

    def process_nmea0183(self, msg):
        return msg

    def process_n2k(self, msg0183):
        if msg0183.proprietary():
            return fromProprietaryNmea(msg0183)
        elif msg0183.address() == b'MXPGN':
            msg = self.mxpgn_decode(msg0183)
            # print(msg.dump())
            return msg
        else:
            return msg0183

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
